#!/usr/bin/env python3
"""Dependency-free SVG evidence: ablation charts and joined application/SDN timeline."""
import argparse
from collections import defaultdict
import csv
from html import escape
import json
from pathlib import Path
import statistics


def events(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def svg_start(width, height, title):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="white"/>',
            '<style>text{font:12px sans-serif;fill:#1e293b} .title{font-size:18px;font-weight:bold}</style>',
            f'<text x="20" y="28" class="title">{escape(title)}</text>']


def bar_plot(rows, output, metric, title):
    groups = defaultdict(list)
    for row in rows:
        key = f"{row['delay_ms']}ms one-way | {row['scenario']} | {row['rto']} / {row['sack']} / CC {row['cc']}"
        groups[key].append(row)
    width, height = 1100, 90 + 32 * len(groups)
    lines = svg_start(width, height, title + ' (mean; range whiskers)')
    maximum = max(float(r[metric]) for r in rows) or 1
    for index, (label, group) in enumerate(groups.items()):
        values = [float(r[metric]) for r in group if str(r['success']).lower() == 'true']
        y = 65 + index * 32
        lines.append(f'<text x="15" y="{y+12}">{escape(label)}</text>')
        if not values:
            lines.append(f'<text x="600" y="{y+12}">FAILED</text>')
            continue
        mean = statistics.mean(values)
        scale = 420 / maximum
        lines.append(f'<rect x="580" y="{y}" width="{mean*scale:.2f}" height="18" fill="#2563eb"/>')
        lines.append(f'<path d="M{580+min(values)*scale:.2f},{y+9} H{580+max(values)*scale:.2f}" stroke="#111827" stroke-width="2"/>')
        lines.append(f'<text x="{590+mean*scale:.2f}" y="{y+13}">{mean:.3f}</text>')
    lines.append('</svg>')
    output.write_text('\n'.join(lines))


def timeline(progress, controller, output):
    app = events(progress)
    network = events(controller) if controller else []
    all_events = app + network
    start = min(e['monotonic_ns'] for e in all_events)
    duration = max((e['monotonic_ns'] - start) / 1e9 for e in all_events) or 1
    width, height = 1100, 820
    lines = svg_start(width, height, 'Application recovery and SDN control on one monotonic clock')
    def x(stamp):
        return 100 + 950 * ((stamp - start) / 1e9) / duration
    panels = [('ack_progress', 'bytes', 'Contiguous acknowledged bytes'),
              ('rto_update', 'value', 'RTO (ms)'), ('cwnd_change', 'value', 'Congestion window (packets)'),
              ('retransmit', 'sequence', 'Retransmitted sequence')]
    for panel, (kind, field, title) in enumerate(panels):
        top = 80 + panel * 180
        selected = [e for e in app if e['event'] == kind]
        maximum = max((e[field] for e in selected), default=1) or 1
        lines.append(f'<text x="20" y="{top-12}">{title}; max={maximum:.1f}</text>')
        lines.append(f'<path d="M100,{top} V{top+125} H1050" fill="none" stroke="#94a3b8"/>')
        points = [(x(e['monotonic_ns']), top + 125 - 120 * e[field] / maximum) for e in selected]
        if kind != 'retransmit':
            coordinates = ' '.join(f'{px:.2f},{py:.2f}' for px, py in points)
            lines.append(f'<polyline points="{coordinates}" fill="none" stroke="#2563eb" stroke-width="2"/>')
        else:
            for e, (px, py) in zip(selected, points):
                color = '#ef4444' if e['reason'] == 'timeout' else '#d97706'
                lines.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3" fill="{color}"/>')
        for e in network:
            if e['event'] in ('link_down', 'route_ready'):
                px = x(e['monotonic_ns'])
                color = '#dc2626' if e['event'] == 'link_down' else '#16a34a'
                lines.append(f'<path d="M{px:.2f},{top} V{top+125}" stroke="{color}" stroke-dasharray="4 3"/>')
        if panel == 0:
            advances = [e for e in app if e['event'] == 'ack_progress']
            for route in network:
                if route.get('event') != 'route_ready' or route.get('cause') not in ('link_down', 'switch_down'):
                    continue
                baseline = max((e['base'] for e in advances if e['monotonic_ns'] <= route['monotonic_ns']), default=0)
                useful = next((e for e in advances if e['monotonic_ns'] > route['monotonic_ns'] and e['base'] > baseline), None)
                if useful:
                    px = x(useful['monotonic_ns'])
                    py = top+125-120*useful['bytes']/maximum
                    lines.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="6" fill="#7c3aed"/>')
                    lines.append(f'<text x="{min(px+8,850):.2f}" y="{top+18}">first useful ACK after route_ready</text>')
        for tick in range(6):
            lines.append(f'<text x="{100+190*tick}" y="{top+145}">{duration*tick/5:.2f}s</text>')
    lines.append('<text x="20" y="805">Blue: application state. Red dashed: link_down. Green dashed: route_ready. Orange dots: fast retry; red dots: timeout.</text></svg>')
    output.write_text('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metrics', type=Path)
    parser.add_argument('--progress', type=Path)
    parser.add_argument('--controller', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.metrics:
        with args.metrics.open() as stream:
            rows = list(csv.DictReader(stream))
        for metric, title in [('goodput_mbps', 'Payload goodput (Mb/s)'),
                              ('retransmits', 'DATA retransmissions'),
                              ('retransmit_fraction', 'Retransmission overhead: retries / all DATA sends')]:
            bar_plot(rows, args.output / f'{metric}.svg', metric, title)
    if args.progress:
        timeline(args.progress, args.controller, args.output / 'timeline.svg')
    if not args.metrics and not args.progress:
        parser.error('provide --metrics or --progress')


if __name__ == '__main__':
    main()
