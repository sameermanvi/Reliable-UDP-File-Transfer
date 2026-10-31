"""Exercise the real controller handlers against a recording OpenFlow adapter.

This verifies dispatch and message construction; it is not a Mininet runtime test.
"""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller.probes import ETHERTYPE
from test_controller import connected_policy


def controller_module():
    modules = {name: types.ModuleType(name) for name in (
        'os_ken', 'os_ken.lib', 'os_ken.base', 'os_ken.controller',
        'os_ken.controller.handler', 'os_ken.ofproto')}
    class Base:
        def __init__(self, *args, **kwargs): self.logger = MagicMock()
        def close(self): pass
    modules['os_ken.lib'].hub = MagicMock()
    modules['os_ken.base'].app_manager = types.SimpleNamespace(OSKenApp=Base)
    modules['os_ken.controller'].ofp_event = MagicMock()
    handler = modules['os_ken.controller.handler']
    handler.CONFIG_DISPATCHER = 'config'; handler.DEAD_DISPATCHER = 'dead'; handler.MAIN_DISPATCHER = 'main'
    handler.set_ev_cls = lambda *args: lambda function: function
    modules['os_ken.ofproto'].ofproto_v1_3 = types.SimpleNamespace(OFP_VERSION=4)
    spec = importlib.util.spec_from_file_location('tested_failover', Path(__file__).resolve().parents[1]/'controller/failover.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules): spec.loader.exec_module(module)
    return module


class OpenFlowTests(unittest.TestCase):
    def setUp(self):
        self.module = controller_module()
        with patch.dict('os.environ', {'RUDP_MODE':'failover', 'RUDP_INITIAL_PATH':'upper', 'RUDP_EVENT_LOG':''}):
            self.controller = self.module.FailoverController()
        self.controller._event = MagicMock()

    def test_features_installs_probe_transit_and_edge_punts(self):
        for dpid in (1, 2, 3, 4):
            parser = MagicMock(); parser.OFPMatch.side_effect = lambda **kwargs: kwargs
            ofp = types.SimpleNamespace(OFPFC_DELETE=3, OFPTT_ALL=255, OFPP_ANY=0xffffffff,
                                       OFPG_ANY=0xffffffff, OFPP_CONTROLLER=0xfffffffd,
                                       OFPCML_NO_BUFFER=65535, OFPIT_APPLY_ACTIONS=4)
            dp = types.SimpleNamespace(id=dpid, ofproto_parser=parser, ofproto=ofp, send_msg=MagicMock())
            self.controller.features(types.SimpleNamespace(msg=types.SimpleNamespace(datapath=dp)))
            probes = [c.kwargs for c in parser.OFPFlowMod.call_args_list if c.kwargs.get('priority') == 200]
            self.assertEqual(len(probes), 2)
            self.assertTrue(all(c['match']['eth_type'] == ETHERTYPE for c in probes))
            outputs = [c.args[0] for c in parser.OFPActionOutput.call_args_list]
            self.assertEqual(outputs, [2, 1] if dpid in (2, 3) else [ofp.OFPP_CONTROLLER]*2)

    def test_soft_hold_down_never_blocks_hard_failure(self):
        c = self.controller; c.policy = connected_policy(); c.started = True; c.path = 'upper'
        c.policy.health = {'upper': .5, 'lower': .01}
        c.last_route_change_ns = 10_000_000_000
        with patch.object(self.module.time, 'clock_gettime_ns', return_value=11_000_000_000):
            c._reconcile('health_update')
            self.assertEqual(c.path, 'upper')
            c.policy.ports[(1, 2)] = False
            c._reconcile('link_down')
            self.assertEqual(c.path, 'lower')

    def test_old_barrier_never_marks_new_generation_ready(self):
        c = self.controller; c.generation = 2; c.pending = {(1, 10): 1}; c.path = 'lower'
        c.barrier_reply(types.SimpleNamespace(msg=types.SimpleNamespace(datapath=types.SimpleNamespace(id=1), xid=10)))
        c._event.assert_not_called()
        c.pending = {(1, 11): 2}
        c.barrier_reply(types.SimpleNamespace(msg=types.SimpleNamespace(datapath=types.SimpleNamespace(id=1), xid=11)))
        self.assertEqual(c._event.call_args.args[0], 'route_ready')


if __name__ == '__main__':
    unittest.main(verbosity=2)
