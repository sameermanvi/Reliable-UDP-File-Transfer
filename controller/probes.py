"""Topology-specific Ethernet probes; pure tracking logic is independently testable."""
import os
import struct

ETHERTYPE = 0x88B5  # Local experimental Ethernet type, never forwarded to hosts.
HEADER = bytes.fromhex('020000000002020000000001') + struct.pack('!H', ETHERTYPE)
MAGIC = b'RUDPPRB1'
# source switch, output port, expected receiving switch, input port
ENDPOINTS = {
    ('upper', 'forward'): (1, 2, 4, 1),
    ('upper', 'reverse'): (4, 1, 1, 2),
    ('lower', 'forward'): (1, 3, 4, 2),
    ('lower', 'reverse'): (4, 2, 1, 3),
}


class ProbeTracker:
    def __init__(self, timeout_ns=500_000_000, freshness_ns=2_000_000_000):
        self.session = os.urandom(8)
        self.sequence = 0
        self.pending = {}
        self.samples = {}
        self.timeout_ns = timeout_ns
        self.freshness_ns = freshness_ns

    def send(self, path, direction, now):
        self.sequence += 1
        sequence = self.sequence
        self.pending[sequence] = (path, direction, now)
        frame = HEADER + MAGIC + self.session + struct.pack('!Q', sequence)
        return frame.ljust(60, b'\0')

    def _sample(self, path, direction, now, success, delay_ms=None):
        key = path, direction
        old = self.samples.get(key)
        loss = 0 if success else 1
        latency = delay_ms if success else (old['delay_ms'] if old else self.timeout_ns / 1e6)
        self.samples[key] = dict(loss=.75 * old['loss'] + .25 * loss if old else loss,
                                 delay_ms=.75 * old['delay_ms'] + .25 * latency if old else latency,
                                 count=old['count'] + 1 if old else 1, updated_ns=now)
        return dict(path=path, direction=direction, success=success, delay_ms=delay_ms)

    def receive(self, frame, dpid, port, now):
        if len(frame) < 38 or frame[:22] != HEADER + MAGIC or frame[22:30] != self.session:
            return None
        sequence = struct.unpack('!Q', frame[30:38])[0]
        pending = self.pending.get(sequence)
        if pending is None:
            return None
        path, direction, sent = pending
        if ENDPOINTS[(path, direction)][2:] != (dpid, port) or now < sent:
            return None
        if now - sent >= self.timeout_ns:
            return None  # Monitor records it as loss; late copies cannot count twice.
        del self.pending[sequence]
        return self._sample(path, direction, now, True, (now - sent) / 1e6)

    def expire(self, now):
        expired = []
        for sequence, (path, direction, sent) in list(self.pending.items()):
            if now - sent >= self.timeout_ns:
                del self.pending[sequence]
                expired.append(self._sample(path, direction, now, False))
        return expired

    def scores(self, now):
        scores = {}
        for path in ('upper', 'lower'):
            samples = [self.samples.get((path, direction)) for direction in ('forward', 'reverse')]
            if all(s and s['count'] >= 4 and now - s['updated_ns'] <= self.freshness_ns for s in samples):
                # A bounded latency penalty breaks loss ties; score is NOT a loss rate.
                scores[path] = max(s['loss'] + min(s['delay_ms'], 500) / 1000 for s in samples)
        return scores

    def invalidate_port(self, dpid, port):
        from controller.routing import PATH_PORTS
        for path, ports in PATH_PORTS.items():
            if (dpid, port) in ports:
                for direction in ('forward', 'reverse'):
                    self.samples.pop((path, direction), None)
                for seq, entry in list(self.pending.items()):
                    if entry[0] == path:
                        del self.pending[seq]

    def invalidate_switch(self, dpid):
        from controller.routing import PATH_PORTS
        for ports in PATH_PORTS.values():
            for switch, port in ports:
                if switch == dpid:
                    self.invalidate_port(switch, port)

    def samples_as_json(self):
        return {f"{path}/{direction}": sample for (path, direction), sample in self.samples.items()}
