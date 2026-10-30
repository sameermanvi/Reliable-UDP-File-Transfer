"""OpenFlow 1.3 diamond: port-status failover, with barrier-confirmed readiness.

OS-Ken is the maintained Ryu fork and uses the same event-driven controller API.
RUDP_MODE=static pins the upper branch; failover chooses an available branch.
"""
import json
import os
import time

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from os_ken.ofproto import ofproto_v1_3

BRANCHES = {'upper': ((1, 2), (2, 1), (2, 2), (4, 1)),
            'lower': ((1, 3), (3, 1), (3, 2), (4, 2))}


class FailoverController(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = os.environ.get('RUDP_MODE', 'failover')
        if self.mode not in ('static', 'failover'):
            raise ValueError('RUDP_MODE must be static or failover')
        self.switches, self.ports, self.pending = {}, {}, set()
        self.discovered = set()
        self.path = None
        self.generation = 0
        self.cause = 'startup'
        self.failed = False
        filename = os.environ.get('RUDP_EVENT_LOG')
        self.log = open(filename, 'a', buffering=1) if filename else None

    def record(self, event, **fields):
        line = json.dumps(dict(event=event, monotonic_ns=time.monotonic_ns(), **fields))
        self.logger.info(line)
        if self.log:
            self.log.write(line + '\n')

    @staticmethod
    def up(dp, port):
        return not (port.state & dp.ofproto.OFPPS_LINK_DOWN or port.config & dp.ofproto.OFPPC_PORT_DOWN)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def connect(self, event):
        dp = event.msg.datapath
        if dp.id not in (1, 2, 3, 4):
            return
        self.switches[dp.id] = dp
        self.discovered.discard(dp.id)
        p, of = dp.ofproto_parser, dp.ofproto
        dp.send_msg(p.OFPFlowMod(datapath=dp, command=of.OFPFC_DELETE,
                                out_port=of.OFPP_ANY, out_group=of.OFPG_ANY,
                                table_id=of.OFPTT_ALL, match=p.OFPMatch()))
        dp.send_msg(p.OFPPortDescStatsRequest(dp, 0))

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def descriptions(self, event):
        msg, dp = event.msg, event.msg.datapath
        for port in msg.body:
            self.ports[dp.id, port.port_no] = self.up(dp, port)
        if not msg.flags & dp.ofproto.OFPMPF_REPLY_MORE:
            self.discovered.add(dp.id)
            if self.discovered == {1, 2, 3, 4}:
                self.install('startup', force=True)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status(self, event):
        msg, dp = event.msg, event.msg.datapath
        key = dp.id, msg.desc.port_no
        up = msg.reason != dp.ofproto.OFPPR_DELETE and self.up(dp, msg.desc)
        if self.ports.get(key) == up:
            return
        self.ports[key] = up
        cause = 'link_up' if up else 'link_down'
        self.record(cause, dpid=dp.id, port=msg.desc.port_no)
        if self.discovered == {1, 2, 3, 4}:
            self.install(cause)

    @set_ev_cls(ofp_event.EventOFPStateChange, DEAD_DISPATCHER)
    def disconnect(self, event):
        dp = event.datapath
        if self.switches.get(dp.id) is dp:
            del self.switches[dp.id]
            self.discovered.discard(dp.id)
            self.install('switch_down', force=True)

    def install(self, cause, force=False):
        available = [name for name, ports in BRANCHES.items()
                     if all(dpid in self.switches and self.ports.get((dpid, port), False)
                            for dpid, port in ports + ((1, 1), (4, 3)))]
        path = 'upper' if self.mode == 'static' else (self.path if self.path in available else next(iter(available), None))
        if path == self.path and not force:
            return
        self.path, self.cause = path, cause
        self.generation += 1
        self.pending.clear()
        self.failed = False
        first = {'upper': 2, 'lower': 3, None: None}[path]
        last = {'upper': 1, 'lower': 2, None: None}[path]
        pairs = {1: ((1, first), (2, 1), (3, 1)), 2: ((1, 2), (2, 1)),
                 3: ((1, 2), (2, 1)), 4: ((1, 3), (2, 3), (3, last))}
        for dpid, dp in self.switches.items():
            p, of = dp.ofproto_parser, dp.ofproto
            for source, destination in pairs[dpid]:
                for ether_type in (0x0800, 0x0806):
                    actions = [p.OFPActionOutput(destination)] if destination else []
                    dp.send_msg(p.OFPFlowMod(datapath=dp, priority=100,
                                match=p.OFPMatch(in_port=source, eth_type=ether_type),
                                instructions=[p.OFPInstructionActions(of.OFPIT_APPLY_ACTIONS, actions)]))
            barrier = p.OFPBarrierRequest(dp)
            dp.set_xid(barrier)
            self.pending.add((dpid, barrier.xid))
            dp.send_msg(barrier)

    @set_ev_cls(ofp_event.EventOFPBarrierReply, MAIN_DISPATCHER)
    def ready(self, event):
        key = event.msg.datapath.id, event.msg.xid
        if key not in self.pending:
            return
        self.pending.remove(key)
        if not self.pending and not self.failed:
            self.record('route_ready' if self.path else 'route_unavailable',
                        path=self.path, cause=self.cause, generation=self.generation)

    @set_ev_cls(ofp_event.EventOFPErrorMsg, [CONFIG_DISPATCHER, MAIN_DISPATCHER])
    def error(self, event):
        self.failed = True
        self.record('openflow_error', dpid=event.msg.datapath.id,
                    error_type=event.msg.type, code=event.msg.code)
