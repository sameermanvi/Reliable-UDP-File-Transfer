"""Real C transfer execution and a delay/loss UDP observation relay."""
import hashlib
import heapq
import json
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import tempfile
import time
import zlib

ROOT = Path(__file__).resolve().parents[2]


def run_live(options, emit, stop_event, loss_control, payload=None):
    def publish(event, **fields):
        emit(dict(event=event, source='relay', monotonic_ns=time.clock_gettime_ns(time.CLOCK_MONOTONIC), **fields))
    with tempfile.TemporaryDirectory(prefix='rudp-viz-') as folder:
        folder = Path(folder)
        source, output = folder/'input.bin', folder/'output.bin'
        source.write_bytes(payload if payload is not None else os.urandom(options.get("packets", 32)*1024))
        scheduled = set(options.get("drop_sequences", ()))
        reserve = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        reserve.bind(('127.0.0.1', 0))
        port = reserve.getsockname()[1]
        reserve.close()
        relay = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        relay.bind(('127.0.0.1', 0))
        loss_path = folder/'drops.jsonl'
        loss_path.touch()
        logs, handles, processes = {'loss': loss_path.open()}, [], []
        try:
            for role in ('receiver', 'sender'):
                path = folder/(role+'.jsonl')
                logs[role] = None
                handles.append((folder/(role+'.log')).open('w+'))
                env = dict(os.environ, RUDP_PROGRESS_LOG=str(path), RUDP_VIZ_RING="1", RUDP_VIZ_DROP_LOG=str(loss_path))
                if role == 'receiver':
                    command = [str(ROOT/'server'), str(port), str(output)]
                else:
                    command = [str(ROOT/'client'), '--host', '127.0.0.1', '--port',
                               str(relay.getsockname()[1]), '--file', str(source),
                               '--sack' if options['sack'] else '--no-sack',
                               '--adaptive-rto' if options['adaptive_rto'] else '--fixed-rto',
                               '--cc' if options['cc'] else '--no-cc',
                               '--drop-rate', str(0 if scheduled else options['drop_rate'])]
                processes.append(subprocess.Popen(command, env=env, stdout=handles[-1], stderr=subprocess.STDOUT))
                if role == 'receiver':
                    deadline = time.monotonic()+3
                    while 'Listening' not in (folder/'receiver.log').read_text():
                        if processes[0].poll() is not None or time.monotonic()>deadline:
                            raise RuntimeError('Receiver startup failed')
                        time.sleep(.01)
            sender = None
            pending, serial = [], 0
            deadline = time.monotonic()+100
            while not stop_event.is_set():
                now = time.monotonic()
                for role, handle in logs.items():
                    if handle is None:
                        path = folder/(role+'.jsonl')
                        if not path.exists():
                            continue
                        handle = logs[role] = path.open()
                    position = handle.tell()
                    while line := handle.readline():
                        if not line.endswith('\n'):
                            handle.seek(position)
                            break
                        record = json.loads(line)
                        record['source'] = role
                        emit(record)
                        position = handle.tell()
                while pending and pending[0][0] <= now:
                    _, _, wire, peer = heapq.heappop(pending)
                    relay.sendto(wire, peer)
                ready, _, _ = select.select([relay], [], [], .005)
                if ready:
                    wire, peer = relay.recvfrom(65535)
                    reverse = peer[1] == port
                    if not reverse:
                        sender = peer
                    destination = sender if reverse else ('127.0.0.1', port)
                    if len(wire) >= 24:
                        magic, version, kind, length, transfer, sequence, crc = struct.unpack('!IBBHQII', wire[:24])
                        flags = {2:4, 6:4, 8:1, 9:5, 10:2}.get(kind, 0)
                        fields = dict(header_hex=wire[:24].hex(), magic=f'{magic:08x}', version=version, wire_type=kind, flags=flags,
                                      transfer_id=f'{transfer:016x}', sequence=sequence,
                                      length=length, crc32=f'{crc:08x}',
                                      direction='ack' if reverse else 'data')
                        if kind == 10 and len(wire) >= 32:
                            fields['sack_base'], fields['sack_mask'] = struct.unpack('!II', wire[24:32])
                        publish('frame', **fields)
                        if kind == 3 and sequence in scheduled:
                            scheduled.remove(sequence)
                            publish('dropped_gap', sequence=sequence, reason='guided_first_attempt')
                            continue
                        if kind == 3 and loss_control.is_set():
                            loss_control.clear()
                            publish('dropped_gap', sequence=sequence, reason='operator_injection')
                            continue
                    if destination:
                        serial += 1
                        heapq.heappush(pending, (now+.015, serial, wire, destination))
                if processes[1].poll() is not None and processes[0].poll() is not None:
                    break
                if now > deadline:
                    raise RuntimeError('Transfer timed out')
            if stop_event.is_set():
                return
            for role, handle in logs.items():
                if handle is None:
                    continue
                for line in handle:
                    if line.endswith('\n'):
                        emit(dict(json.loads(line), source=role))
            codes = [p.wait(timeout=1) for p in processes]
            original = source.read_bytes()
            received = output.read_bytes() if output.exists() else b''
            match = output.exists() and hashlib.sha256(original).digest() == hashlib.sha256(received).digest()
            def fields(name):
                import re
                return dict(re.findall(r'(\w+)=([^\s]+)', (folder/name).read_text()))
            sent, accepted = fields('sender.log'), fields('receiver.log')
            expected_crc = f'{zlib.crc32(original):08x}'
            crc_match = sent.get('crc32') == accepted.get('crc32') == expected_crc
            publish('verification', sha256_match=match, crc32_match=crc_match, file_bytes=len(original),
                    seconds=float(sent.get('seconds', 0)), goodput_mbps=float(sent.get('goodput_mbps', 0)),
                    data_sends=int(sent.get('data_sends', 0)), retransmits=int(sent.get('retransmits', 0)),
                    duplicates=int(accepted.get('duplicates', 0)), out_of_order=int(accepted.get('out_of_order', 0)), source_sha256=hashlib.sha256(original).hexdigest(),
                    output_sha256=hashlib.sha256(received).hexdigest() if output.exists() else None,
                    crc32=f'{zlib.crc32(original):08x}', sender_exit=codes[1], receiver_exit=codes[0])
            if codes != [0, 0] or not match or not crc_match:
                raise RuntimeError('Transfer failed: ' + (folder/'sender.log').read_text() + (folder/'receiver.log').read_text())
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            for handle in [*logs.values(), *handles]:
                if handle is not None:
                    handle.close()
            relay.close()
