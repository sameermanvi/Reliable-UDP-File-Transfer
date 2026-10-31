#!/usr/bin/env python3
"""Summarize all trials and plot successful transfers without hiding failures."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import statistics


def truth(value):
    return str(value).lower() == "true"


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        label = row["mode"]
        if "rto" in row:
            label += f"/{row['rto']}/{row['sack']}/cc={row['cc']}/loss={row['loss_percent']}/fail={row['fail_after']}/flap={row['flap_period']}"
        if "initial_path" in row:
            label += f"/start={row['initial_path']}/cut={row['failure_path']}/reorder={row.get('reorder_percent', 0)}/degrade={row.get('degrade_loss_percent', 0)}"
        if "delay_ms" in row:
            label += f"/delay={row['delay_ms']}ms"
        groups[(row["scenario"], label)].append(row)
    result = []
    for (scenario, mode), group in groups.items():
        successful = [row for row in group if truth(row["success"])]
        summary = dict(scenario=scenario, mode=mode, observations=len(group),
                       trials=len({row["run_id"] for row in group}),
                       successful=len(successful),
                       censored=sum(str(row.get("recovery_status", "")).startswith("censored") for row in group),
                       expected_outcomes=sum(truth(row["expectation_met"]) for row in group))
        for metric in ("goodput_mbps", "seconds", "retransmits",
                       "route_install_seconds", "progress_recovery_seconds", "ack_gap_seconds", "retransmit_fraction", "link_down_to_progress_seconds", "route_to_progress_seconds"):
            values = [float(row[metric]) for row in successful
                      if row.get(metric) not in (None, "", "None")]
            summary[metric] = (dict(mean=statistics.mean(values), minimum=min(values),
                                    maximum=max(values), count=len(values)) if values else None)
        result.append(summary)
    return result


def make_plots(summaries, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "svg.fonttype": "none"})
    labels = [f"{item['scenario']} | {item['mode']}" for item in summaries]
    colors = ["#2563eb" if item["mode"].startswith("failover") else "#64748b" for item in summaries]
    for metric, xlabel, title in (
        ("goodput_mbps", "Payload goodput (Mb/s)", "Goodput of successful transfers"),
        ("retransmits", "Extra DATA sends", "Retransmissions of successful transfers"),
        ("retransmit_fraction", "Retries / all DATA sends", "Retransmission overhead"),
        ("progress_recovery_seconds", "Seconds after failure request", "Application recovery from injection"),
        ("link_down_to_progress_seconds", "Seconds after controller link_down", "Application recovery after observed failure"),
    ):
        fig, ax = plt.subplots(figsize=(14, max(4, len(summaries) * .35)))
        for index, item in enumerate(summaries):
            measurement = item[metric]
            if measurement:
                mean = measurement["mean"]
                ax.barh(index, mean, color=colors[index], height=.65)
                ax.errorbar(mean, index, xerr=[[mean-measurement["minimum"]],
                            [measurement["maximum"]-mean]], color="#111827", capsize=3, fmt="none")
            else:
                ax.text(.01, index, "N/A", transform=ax.get_yaxis_transform(), va="center")
        ax.set_yticks(range(len(labels)), labels, fontsize=7)
        ax.invert_yaxis(); ax.set_xlabel(xlabel)
        ax.set_title(title + " (mean and min–max; N/A is not zero)")
        ax.set_xlim(left=0); ax.grid(axis="x", alpha=.2); ax.set_axisbelow(True)
        fig.tight_layout(); fig.savefig(output / f"{metric}.svg"); plt.close(fig)
    fig, ax = plt.subplots(figsize=(14, max(4, len(summaries) * .35)))
    rates = [100 * item["successful"] / item["observations"] for item in summaries]
    ax.barh(range(len(labels)), rates, color=colors)
    for index, item in enumerate(summaries):
        ax.text(rates[index]+1, index, f"{item['successful']}/{item['observations']}", va="center")
    ax.set_yticks(range(len(labels)), labels, fontsize=7); ax.invert_yaxis()
    ax.set_xlim(0, 115); ax.set_xlabel("Successful flows (%)")
    ax.set_title("Completion across all trials, including failed runs")
    fig.tight_layout(); fig.savefig(output / "completion.svg"); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metrics", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-plots", action="store_true", help="write tables without Matplotlib")
    args = parser.parse_args()
    with args.metrics.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        parser.error("metrics file contains no trials")
    summaries = summarize(rows)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    lines = ["# Experiment summary", "", "All rows are retained. Rates include failures; numeric "
             "performance summaries use successful transfers only. N/A is not zero. "
             "Multiple flows in one trial share a network and are not independent trials.", "",
             "| Scenario | Mode | Trials | Successful flows | Expected outcomes | Mean goodput (Mb/s) | Mean recovery (s) | Censored |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for item in summaries:
        def average(key):
            return f"{item[key]['mean']:.4f}" if item[key] else "N/A"
        lines.append(f"| {item['scenario']} | {item['mode']} | {item['trials']} | "
                     f"{item['successful']}/{item['observations']} | "
                     f"{item['expected_outcomes']}/{item['observations']} | "
                     f"{average('goodput_mbps')} | {average('progress_recovery_seconds')} | {item['censored']} |")
    (args.output / "summary.md").write_text("\n".join(lines) + "\n")
    if not args.no_plots:
        make_plots(summaries, args.output)
    print(args.output / "summary.md")


if __name__ == "__main__":
    main()
