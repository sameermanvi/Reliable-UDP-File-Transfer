
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
from controller.probe_schedule import AdaptiveProbeSchedule


COOKIE = 0x5255445000000001
MULTIPATH_COOKIE = 0x5255445000000010


class FailoverController(AppBase):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.policy = PathPolicy(
            os.environ.get("RUDP_MODE", "failover"),
            os.environ.get("RUDP_INITIAL_PATH", "upper"),
        )

        self.datapaths = {}
        self.discovered = set()
        self.started = False
        self.path = None
        self.generation = 0
        self.pending = {}
        self.failed_generation = False
        self.cause = "startup"

        event_path = os.environ.get("RUDP_EVENT_LOG")
        self.event_file = (
            open(event_path, "a", buffering=1) if event_path else None
        )

        self._event("controller_started", mode=self.policy.mode)

        self.probes = ProbeTracker()

        self.probe_schedules = {
            key: AdaptiveProbeSchedule() for key in ENDPOINTS
        }

        # Each path/direction has its own next-probe deadline.
        self.next_probe_ns = {key: 0 for key in ENDPOINTS}

        self.last_route_change_ns = 0
        self.monitor = hub.spawn(self._monitor)

    def _refresh_health(self, now):
        self.policy.health = self.probes.scores(now)

        # Adapt each direction's schedule according to its own path's health.
        # A degraded upper path should not automatically accelerate the lower
        # path's probes.
        for (path, direction), schedule in self.probe_schedules.items():
            path_score = self.policy.health.get(path)
            degraded = path_score is None or path_score > 0.10
            schedule.set_degraded(degraded, now)

    def _monitor(self):
        while True:
            now = time.clock_gettime_ns(time.CLOCK_MONOTONIC)

            # Record timed-out probes and make their next probe eligible now.
            for observation in self.probes.expire(now):
                self._event("probe_result", **observation)

                key = (
                    observation["path"],
                    observation["direction"],
                )

                self.probe_schedules[key].record_result(False, now)
                self.next_probe_ns[key] = now

            self._refresh_health(now)

            if self.started:
                self._event(
                    "path_health",
                    scores=self.policy.health,
                    source="bidirectional_ethernet_probes",
                    samples=self.probes.samples_as_json(),
                    hysteresis=0.02,
                    hold_down_seconds=2,
                )

                self._reconcile("health_update")

                # Send only the probes whose individual deadlines have arrived.
                for (
                    (path, direction),
                    (source, out_port, _, _),
                ) in ENDPOINTS.items():

                    if not self.policy.available(path):
                        continue

                    dp = self.datapaths.get(source)

                    if dp is None:
                        continue

                    key = (path, direction)

                    if now < self.next_probe_ns[key]:
                        continue

                    frame = self.probes.send(path, direction, now)

                    dp.send_msg(dp.ofproto_parser.OFPPacketOut(
                        datapath=dp,
                        buffer_id=dp.ofproto.OFP_NO_BUFFER,
                        in_port=dp.ofproto.OFPP_CONTROLLER,
                        actions=[
                            dp.ofproto_parser.OFPActionOutput(out_port)
                        ],
                        data=frame,
                    ))

                    interval_ns = int(
                        self.probe_schedules[key].interval_seconds(now)
                        * 1_000_000_000
                    )

                    self.next_probe_ns[key] = now + interval_ns

            # Wake at the next probe deadline or pending-probe timeout.
            # Cap sleep at 250 ms so health and controller state are refreshed.
            deadlines = []

            if self.started:
                for (
                    (path, direction),
                    (source, _, _, _),
                ) in ENDPOINTS.items():

                    if not self.policy.available(path):
                        continue

                    if source not in self.datapaths:
                        continue

                    deadline = self.next_probe_ns[(path, direction)]

                    if deadline > now:
                        deadlines.append(deadline)

                for _, _, sent_ns in self.probes.pending.values():
                    timeout_deadline = sent_ns + self.probes.timeout_ns

                    if timeout_deadline > now:
                        deadlines.append(timeout_deadline)

            if deadlines:
                sleep_ns = max(1_000_000, min(deadlines) - now)
                interval = min(sleep_ns / 1_000_000_000, 0.25)
            else:
                interval = 0.25

            hub.sleep(interval)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def probe_received(self, event):
        msg = event.msg
        now = time.clock_gettime_ns(time.CLOCK_MONOTONIC)

        observation = self.probes.receive(
            bytes(msg.data),
            msg.datapath.id,
            msg.match.get("in_port"),
            now,
        )

        if observation:
            self._event("probe_result", **observation)

            key = (
                observation["path"],
                observation["direction"],
            )

            schedule = self.probe_schedules[key]
            schedule.record_result(True, now)

            # If the new result calls for faster probing, bring the deadline
            # forward. Never delay a probe that is already due.
            interval_ns = int(
                schedule.interval_seconds(now) * 1_000_000_000
            )

            proposed_deadline = now + interval_ns

            self.next_probe_ns[key] = min(
                self.next_probe_ns[key],
                proposed_deadline,
            )

            self._refresh_health(now)

    def _event(self, event, **fields):
        record = dict(
            event=event,
            monotonic_ns=time.clock_gettime_ns(time.CLOCK_MONOTONIC),
            wall_time=datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            **fields,
        )

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

        # Clear stale flows on reconnect, then keep table-miss as drop.
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp,
            command=ofp.OFPFC_DELETE,
            table_id=ofp.OFPTT_ALL,
            out_port=ofp.OFPP_ANY,
            out_group=ofp.OFPG_ANY,
            match=parser.OFPMatch(),
        ))

        dp.send_msg(parser.OFPFlowMod(
            datapath=dp,
            cookie=COOKIE,
            priority=0,
            match=parser.OFPMatch(),
            instructions=[],
        ))

        # Probe rules are independent of the selected application path.
        probe_ports = (1, 2) if dp.id in (2, 3, 4) else (2, 3)

        for in_port in probe_ports:
            out_port = (
                3 - in_port if dp.id in (2, 3)
                else ofp.OFPP_CONTROLLER
            )

            action = parser.OFPActionOutput(
                out_port,
                ofp.OFPCML_NO_BUFFER,
            )

            dp.send_msg(parser.OFPFlowMod(
                datapath=dp,
                cookie=COOKIE,
                priority=200,
                match=parser.OFPMatch(
                    in_port=in_port,
                    eth_type=ETHERTYPE,
                ),
                instructions=[
                    parser.OFPInstructionActions(
                        ofp.OFPIT_APPLY_ACTIONS,
                        [action],
                    )
                ],
            ))

        dp.send_msg(parser.OFPPortDescStatsRequest(dp, 0))
        self._event("switch_connected", dpid=dp.id)

    @staticmethod
    def _port_up(dp, port):
        ofp = dp.ofproto

        return not (
            port.state & ofp.OFPPS_LINK_DOWN
            or port.config & ofp.OFPPC_PORT_DOWN
        )

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def port_description(self, event):
        msg, dp = event.msg, event.msg.datapath

        if dp.id not in self.datapaths:
            return

        for port in msg.body:
            self.policy.ports[(dp.id, port.port_no)] = (
                self._port_up(dp, port)
            )

        if msg.flags & dp.ofproto.OFPMPF_REPLY_MORE:
            return

        self.discovered.add(dp.id)

        self._reconcile(
            "startup" if not self.started else "switch_up",
            force=True,
        )

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status(self, event):
        msg, dp = event.msg, event.msg.datapath

        if dp.id not in self.datapaths:
            return

        key = (dp.id, msg.desc.port_no)

        up = (
            msg.reason != dp.ofproto.OFPPR_DELETE
            and self._port_up(dp, msg.desc)
        )

        previous = self.policy.ports.get(key)
        self.policy.ports[key] = up

        if previous == up:
            return

        cause = "link_up" if up else "link_down"

        self.probes.invalidate_port(dp.id, msg.desc.port_no)

        self._refresh_health(
            time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        )

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
            if (
                self.pending
                or now - self.last_route_change_ns < 2_000_000_000
            ):
                self._event(
                    "route_decision",
                    selected=self.path,
                    candidate=path,
                    reason="hold_down_or_barrier",
                    health=self.policy.health,
                )
                return

        self.last_route_change_ns = now

        self._event(
            "route_decision",
            previous=self.path,
            selected=path,
            reason=cause,
            health=self.policy.health,
        )

        self.path = path
        self.generation += 1
        self.cause = cause
        self.pending.clear()
        self.failed_generation = False

        self._event(
            "route_installing",
            path=path,
            cause=cause,
            generation=self.generation,
            health=self.policy.health,
        )

        rules = forwarding_rules(path)

        # Install the selected route and remove stale multipath rules.
        for dpid, dp in sorted(self.datapaths.items()):
            parser, ofp = dp.ofproto_parser, dp.ofproto

            for rule in rules[dpid]:
                actions = (
                    [] if rule.out_port is None
                    else [parser.OFPActionOutput(rule.out_port)]
                )

                instructions = [
                    parser.OFPInstructionActions(
                        ofp.OFPIT_APPLY_ACTIONS,
                        actions,
                    )
                ]

                dp.send_msg(parser.OFPFlowMod(
                    datapath=dp,
                    cookie=COOKIE,
                    priority=100,
                    match=parser.OFPMatch(
                        in_port=rule.in_port,
                        eth_type=rule.eth_type,
                    ),
                    instructions=instructions,
                ))

            # Remove this controller's previous DSCP-specific rules.
            dp.send_msg(parser.OFPFlowMod(
                datapath=dp,
                cookie=MULTIPATH_COOKIE,
                cookie_mask=0xffffffffffffffff,
                table_id=0,
                command=ofp.OFPFC_DELETE,
                out_port=ofp.OFPP_ANY,
                out_group=ofp.OFPG_ANY,
                match=parser.OFPMatch(),
            ))

            # DATA uses DSCP 8 for upper and DSCP 16 for lower.
            multipath_paths = {
                "upper": (
                    8,
                    ((1, 1, 2), (2, 1, 2), (4, 1, 3)),
                ),
                "lower": (
                    16,
                    ((1, 1, 3), (3, 1, 2), (4, 2, 3)),
                ),
            }

            for path_name, (dscp, entries) in multipath_paths.items():
                details = self.policy.availability_details(path_name)

                self._event(
                    "multipath_path_check",
                    dpid=dpid,
                    path=path_name,
                    dscp=dscp,
                    available=details["available"],
                    missing_switches=details["missing_switches"],
                    unavailable_ports=details["unavailable_ports"],
                )

                if not details["available"]:
                    continue

                for switch_id, ingress, output in entries:
                    if switch_id != dpid:
                        continue

                    instructions = [
                        parser.OFPInstructionActions(
                            ofp.OFPIT_APPLY_ACTIONS,
                            [parser.OFPActionOutput(output)],
                        )
                    ]

                    dp.send_msg(parser.OFPFlowMod(
                        datapath=dp,
                        cookie=MULTIPATH_COOKIE,
                        priority=150,
                        match=parser.OFPMatch(
                            in_port=ingress,
                            eth_type=0x0800,
                            ip_dscp=dscp,
                        ),
                        instructions=instructions,
                    ))

            barrier = parser.OFPBarrierRequest(dp)
            dp.set_xid(barrier)

            self.pending[(dpid, barrier.xid)] = self.generation
            dp.send_msg(barrier)

    @set_ev_cls(ofp_event.EventOFPBarrierReply, MAIN_DISPATCHER)
    def barrier_reply(self, event):
        key = (event.msg.datapath.id, event.msg.xid)
        generation = self.pending.pop(key, None)

        if (
            generation != self.generation
            or self.pending
            or self.failed_generation
        ):
            return

        self._event(
            "route_ready" if self.path else "route_unavailable",
            path=self.path,
            cause=self.cause,
            generation=self.generation,
        )

    @set_ev_cls(
        ofp_event.EventOFPErrorMsg,
        [CONFIG_DISPATCHER, MAIN_DISPATCHER],
    )
    def openflow_error(self, event):
        msg = event.msg
        self.failed_generation = True

        self._event(
            "openflow_error",
            dpid=msg.datapath.id,
            error_type=msg.type,
            code=msg.code,
            xid=msg.xid,
        )

    def close(self):
        hub.kill(self.monitor)

        if self.event_file:
            self.event_file.close()

        super().close()
