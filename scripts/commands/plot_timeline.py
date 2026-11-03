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
    lines = svg_start(width, height, title)
    cue = "Higher means faster delivery." if metric == "goodput_mbps" else "Lower means less retry overhead."
    lines.append(f'<text x="20" y="49">{cue} Bar = mean across completed transfers. Black line = observed range.</text>')
    maximum = max((float(r[metric]) for r in rows if str(r['success']).lower() == 'true'), default=1) or 1
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
        lines.append(f'<text x="{590+max(values)*scale:.2f}" y="{y+13}">{mean:.3f}</text>')
    lines.append('</svg>')
    output.write_text('\n'.join(lines))


def timeline(progress, controller, output):
    app = events(progress)
    network = events(controller) if controller else []
    combined = app + network
    if not combined:
        raise ValueError("No events to plot")
    start = min(e['monotonic_ns'] for e in combined)
    duration = max((e['monotonic_ns']-start)/1e9 for e in combined) or 1
    lines = svg_start(1200, 1120, "Transfer timeline · " + progress.parent.name)
    lines.append('<text x="20" y="52">Shared monotonic clock · application measurements · time in seconds from first recorded event</text>')
    advances = sorted((e for e in app if e['event']=='ack_progress'), key=lambda e:e['monotonic_ns'])
    observations = []
    outage_file = progress.parent/'outages-0.json'
    outages = json.loads(outage_file.read_text()) if outage_file.exists() else []
    for route in network:
        if route.get('event')!='route_ready' or route.get('cause') not in ('link_down','switch_down'):
            continue
        previous_route = max((e['monotonic_ns'] for e in network
                              if e['event']=='route_ready' and e['monotonic_ns']<route['monotonic_ns']), default=start)
        cuts = [e for e in network if e['event'] in ('link_down','switch_down')
                and previous_route <= e['monotonic_ns'] <= route['monotonic_ns']]
        if not cuts:
            continue
        cut = min(cuts, key=lambda e:e['monotonic_ns'])
        measured = next((o for o in outages if o.get('route_ready_monotonic_ns')==route['monotonic_ns']), None)
        if measured and measured.get('link_down_monotonic_ns'):
            cut = dict(event='link_down', monotonic_ns=measured['link_down_monotonic_ns'])
        baseline = max((e['base'] for e in advances if e['monotonic_ns']<=route['monotonic_ns']),default=0)
        useful = next((e for e in advances if e['monotonic_ns']>route['monotonic_ns'] and e['base']>baseline),None)
        if useful:
            observations.append((cut,route,useful))
    markers = []
    if observations:
        cut,route,useful = observations[0]
        total = (useful['monotonic_ns']-cut['monotonic_ns'])/1e6
        install = (route['monotonic_ns']-cut['monotonic_ns'])/1e6
        progress_ms = (useful['monotonic_ns']-route['monotonic_ns'])/1e6
        lines.append(f'<text x="20" y="82" class="title">Observed recovery {total:.3f} ms</text>')
        lines.append(f'<text x="20" y="106">Link down → barrier-confirmed route {install:.3f} ms · route → useful ACK {progress_ms:.3f} ms</text>')
        markers = [(cut,'1  LINK DOWN','#dc2626'), (route,'2  ROUTE READY','#15803d'),(useful,'3  USEFUL ACK','#0369a1')]
    else:
        lines.append('<text x="20" y="82" class="title">Recovery N/A — no complete link-down → route-ready → useful-ACK sequence</text>')
        markers = [(e,'LINK DOWN','#dc2626') for e in network if e['event']=='link_down'][:3]
    if observations:
        # Magnify only the outage. The panels below retain the full transfer clock.
        lines.append('<text x="540" y="131" class="title">Recovery interval, enlarged</text>')
        middle = 540 + 500 * install / total
        lines.append(f'<path d="M540,153 H{middle:.2f}" stroke="#15803d" stroke-width="9"/>')
        lines.append(f'<path d="M{middle:.2f},153 H1040" stroke="#0369a1" stroke-width="9"/>')
        lines.append('<text x="540" y="179">Green = installing the route · blue = waiting for useful ACK progress</text>')
    for i,(event,label,color) in enumerate(markers):
        when=(event['monotonic_ns']-start)/1e9
        lines.append(f'<text x="20" y="{132+i*22}" style="fill:{color}">{escape(label)}  t = {when:.6f} s</text>')
    def x(stamp):
        return 125 + 1000*((stamp-start)/1e9)/duration
    panels = [('ack_progress','bytes','Contiguous acknowledged file bytes'),
              ('rto_update','value','UDP retransmission timeout (ms)'),
              ('cwnd_change','value','UDP congestion window (packets)'),
              ('retransmit','sequence','Retransmitted DATA sequence number')]
    for index,(kind,field,title) in enumerate(panels):
        top=240+index*195
        selected=[e for e in app if e['event']==kind]
        maximum=max((e[field] for e in selected),default=1) or 1
        lines.append(f'<text x="20" y="{top-18}" class="title">{escape(title)}</text>')
        for tick in range(3):
            value=maximum*tick/2
            py=top+120-120*tick/2
            lines.append(f'<path d="M125,{py} H1125" stroke="#e2e8f0"/>')
            lines.append(f'<text x="112" y="{py+4}" text-anchor="end">{value:,.1f}</text>')
        lines.append(f'<path d="M125,{top} V{top+120} H1125" fill="none" stroke="#64748b"/>')
        points=[(x(e['monotonic_ns']),top+120-120*e[field]/maximum) for e in selected]
        if not selected:
            lines.append(f'<text x="150" y="{top+50}">No recorded samples</text>')
        elif kind!='retransmit':
            coords=' '.join(f'{px:.2f},{py:.2f}' for px,py in points)
            lines.append(f'<polyline points="{coords}" fill="none" stroke="#2563eb" stroke-width="2"/>')
        else:
            for e,(px,py) in zip(selected,points):
                color='#dc2626' if e.get('reason')=='timeout' else '#d97706'
                lines.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3" fill="{color}"/>')
        for event,label,color in markers:
            px=x(event['monotonic_ns'])
            lines.append(f'<path d="M{px:.2f},{top} V{top+120}" stroke="{color}" stroke-dasharray="4 3"/>')
        for tick in range(6):
            lines.append(f'<text x="{125+200*tick}" y="{top+143}" text-anchor="middle">{duration*tick/5:.2f}</text>')
        lines.append(f'<text x="1125" y="{top+165}" text-anchor="end">Elapsed monotonic time (s)</text>')
    lines.append('<text x="20" y="1060">An upward ACK line means more of the file is confirmed. A flat stretch means the contiguous prefix has stopped advancing.</text>')
    lines.append('<text x="20" y="1084">Blue lines: measured application state · retry dots: amber fast gap / red timeout · congestion window belongs to this UDP implementation.</text>')
    lines.append('</svg>')
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
