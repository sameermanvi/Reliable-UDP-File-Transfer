"""Proactive OpenFlow 1.3 routes with port-status-driven path recovery.

Run with osken-manager --ofp-tcp-listen-port 6653 controller/failover.py.
RUDP_MODE selects static or failover; RUDP_EVENT_LOG selects the JSONL log.
"""

import datetime
import json
import os
from pathlib import Path
import sys
import time

try:
    from os_ken.lib import hub
    from os_ken.base import app_manager
    from os_ken.controller import ofp_event
    from os_ken.controller.handler import (
        CONFIG_DISPATCHER, DEAD_DISPATCHER, MAIN_DISPATCHER, set_ev_cls,
    )
    from os_ken.ofproto import ofproto_v1_3
    AppBase = app_manager.OSKenApp
except ImportError:
    from ryu.lib import hub
    from ryu.base import app_manager
    from ryu.controller import ofp_event
    from ryu.controller.handler import (
        CONFIG_DISPATCHER, DEAD_DISPATCHER, MAIN_DISPATCHER, set_ev_cls,
    )
    from ryu.ofproto import ofproto_v1_3
    AppBase = app_manager.RyuApp

# The manager may load this file by path without adding the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller.routing import PathPolicy, SWITCHES, forwarding_rules
from controller.probes import ProbeTracker, ENDPOINTS, ETHERTYPE


COOKIE = 0x5255445000000001


class FailoverController(AppBase):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy = PathPolicy(os.environ.get("RUDP_MODE", "failover"), os.environ.get("RUDP_INITIAL_PATH", "upper"))
        self.datapaths = {}
        self.discovered = set()
        self.started = False
        self.path = None
        self.generation = 0
        self.pending = {}
        self.failed_generation = False
        self.cause = "startup"
        event_path = os.environ.get("RUDP_EVENT_LOG")
        self.event_file = open(event_path, "a", buffering=1) if event_path else None
        self._event("controller_started", mode=self.policy.mode)
        self.probes = ProbeTracker()
        self.last_route_change_ns = 0
        self.monitor = hub.spawn(self._monitor)

    def _refresh_health(self, now):
        self.policy.health = self.probes.scores(now)

    def _monitor(self):
        while True:
            now = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
            for observation in self.probes.expire(now):
                self._event("probe_result", **observation)
            self._refresh_health(now)
            if self.started:
                self._event("path_health", scores=self.policy.health,
                            source="bidirectional_ethernet_probes", samples=self.probes.samples_as_json(),
                            hysteresis=.02, hold_down_seconds=2)
                self._reconcile("health_update")
                for (path, direction), (source, out_port, _, _) in ENDPOINTS.items():
                    if not self.policy.available(path):
                        continue
                    dp = self.datapaths.get(source)
                    if dp is None:
                        continue
                    frame = self.probes.send(path, direction, now)
                    dp.send_msg(dp.ofproto_parser.OFPPacketOut(
                        datapath=dp, buffer_id=dp.ofproto.OFP_NO_BUFFER,
                        in_port=dp.ofproto.OFPP_CONTROLLER,
                        actions=[dp.ofproto_parser.OFPActionOutput(out_port)], data=frame))
            hub.sleep(.25)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def probe_received(self, event):
        msg = event.msg
        now = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        observation = self.probes.receive(bytes(msg.data), msg.datapath.id, msg.match.get("in_port"), now)
        if observation:
            self._event("probe_result", **observation)
            self._refresh_health(now)

    def _event(self, event, **fields):
        record = dict(event=event, monotonic_ns=time.clock_gettime_ns(time.CLOCK_MONOTONIC),
                      wall_time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      **fields)
        line = json.dumps(record, sort_keys=True)
        self.logger.info(line)
        if self.event_file:
            self.event_file.write(line + "\n")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def features(self, event):
        dp = event.msg.datapath
        if dp.id not in SWITCHES:
            self._event("unexpected_switch", dpid=dp.id)
            return
        self.probes.invalidate_switch(dp.id)
        self.datapaths[dp.id] = dp
        self.policy.connected.add(dp.id)
        self.discovered.discard(dp.id)
        parser, ofp = dp.ofproto_parser, dp.ofproto
        # This is a dedicated lab controller. Clear stale flows on reconnect,
        # then keep table-miss as drop rather than learning/flooding the loop.
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp, command=ofp.OFPFC_DELETE, table_id=ofp.OFPTT_ALL,
            out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY,
            match=parser.OFPMatch()))
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp, cookie=COOKIE, priority=0,
            match=parser.OFPMatch(), instructions=[]))
        # Probe rules are independent of the chosen application path. Transit
        # crosses the branch; edge ingress punts to the controller, never hosts.
        probe_ports = (1, 2) if dp.id in (2, 3, 4) else (2, 3)
        for in_port in probe_ports:
            out_port = 3 - in_port if dp.id in (2, 3) else ofp.OFPP_CONTROLLER
            action = parser.OFPActionOutput(out_port, ofp.OFPCML_NO_BUFFER)
            dp.send_msg(parser.OFPFlowMod(
                datapath=dp, cookie=COOKIE, priority=200,
                match=parser.OFPMatch(in_port=in_port, eth_type=ETHERTYPE),
                instructions=[parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, [action])]))
        dp.send_msg(parser.OFPPortDescStatsRequest(dp, 0))
        self._event("switch_connected", dpid=dp.id)

    @staticmethod
    def _port_up(dp, port):
        ofp = dp.ofproto
        return not (port.state & ofp.OFPPS_LINK_DOWN
                    or port.config & ofp.OFPPC_PORT_DOWN)

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def port_description(self, event):
        msg, dp = event.msg, event.msg.datapath
        if dp.id not in self.datapaths:
            return
        for port in msg.body:
            self.policy.ports[(dp.id, port.port_no)] = self._port_up(dp, port)
        if msg.flags & dp.ofproto.OFPMPF_REPLY_MORE:
            return
        self.discovered.add(dp.id)
        self._reconcile("startup" if not self.started else "switch_up", force=True)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status(self, event):
        msg, dp = event.msg, event.msg.datapath
        if dp.id not in self.datapaths:
            return
        key = (dp.id, msg.desc.port_no)
        up = msg.reason != dp.ofproto.OFPPR_DELETE and self._port_up(dp, msg.desc)
        previous = self.policy.ports.get(key)
        self.policy.ports[key] = up
        if previous == up:
            return
        cause = "link_up" if up else "link_down"
        self.probes.invalidate_port(dp.id, msg.desc.port_no)
        self._refresh_health(time.clock_gettime_ns(time.CLOCK_MONOTONIC))
        self._event(cause, dpid=dp.id, port=msg.desc.port_no)
        self._reconcile(cause)

    @set_ev_cls(ofp_event.EventOFPStateChange, DEAD_DISPATCHER)
    def disconnected(self, event):
        dp = event.datapath
        if self.datapaths.get(dp.id) is not dp:
            return
        self.probes.invalidate_switch(dp.id)
        del self.datapaths[dp.id]
        self.policy.connected.discard(dp.id)
        self.discovered.discard(dp.id)
        self._event("switch_down", dpid=dp.id)
        self._reconcile("switch_down", force=True)

    def _reconcile(self, cause, force=False):
        if not self.started:
            if self.discovered != SWITCHES:
                return
            self.started = True
        path = self.policy.choose(self.path)
        if not force and path == self.path:
            return
        now = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        if cause == "health_update" and path != self.path:
            if self.pending or now - self.last_route_change_ns < 2_000_000_000:
                self._event("route_decision", selected=self.path, candidate=path, reason="hold_down_or_barrier",
                            health=self.policy.health)
                return
        self.last_route_change_ns = now
        self._event("route_decision", previous=self.path, selected=path, reason=cause,
                    health=self.policy.health)
        self.path = path
        self.generation += 1
        self.cause = cause
        self.pending.clear()
        self.failed_generation = False
        self._event("route_installing", path=path, cause=cause,
                    generation=self.generation, health=self.policy.health)
        rules = forwarding_rules(path)
        # Each ADD replaces the previous identical match/priority atomically
        # within a switch. During an update, asymmetrical forward/reverse paths
        # still reach their host: branch ingress never sends into another branch.
        for dpid, dp in sorted(self.datapaths.items()):
            parser, ofp = dp.ofproto_parser, dp.ofproto
            for rule in rules[dpid]:
                actions = ([] if rule.out_port is None else
                           [parser.OFPActionOutput(rule.out_port)])
                instructions = [parser.OFPInstructionActions(
                    ofp.OFPIT_APPLY_ACTIONS, actions)]
                dp.send_msg(parser.OFPFlowMod(
                    datapath=dp, cookie=COOKIE, priority=100,
                    match=parser.OFPMatch(in_port=rule.in_port,
                                          eth_type=rule.eth_type),
                    instructions=instructions))
            barrier = parser.OFPBarrierRequest(dp)
            dp.set_xid(barrier)
            self.pending[(dpid, barrier.xid)] = self.generation
            dp.send_msg(barrier)

    @set_ev_cls(ofp_event.EventOFPBarrierReply, MAIN_DISPATCHER)
    def barrier_reply(self, event):
        key = (event.msg.datapath.id, event.msg.xid)
        generation = self.pending.pop(key, None)
        if generation != self.generation or self.pending or self.failed_generation:
            return
        self._event("route_ready" if self.path else "route_unavailable",
                    path=self.path, cause=self.cause, generation=self.generation)

    @set_ev_cls(ofp_event.EventOFPErrorMsg, [CONFIG_DISPATCHER, MAIN_DISPATCHER])
    def openflow_error(self, event):
        msg = event.msg
        self.failed_generation = True
        self._event("openflow_error", dpid=msg.datapath.id,
                    error_type=msg.type, code=msg.code, xid=msg.xid)

    def close(self):
        hub.kill(self.monitor)
        if self.event_file:
            self.event_file.close()
        super().close()
