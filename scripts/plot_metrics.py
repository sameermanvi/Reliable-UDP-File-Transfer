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
        groups[(row["scenario"], row["mode"])].append(row)
    result = []
    for (scenario, mode), group in groups.items():
        successful = [row for row in group if truth(row["success"])]
        summary = dict(scenario=scenario, mode=mode, observations=len(group),
                       trials=len({row["run_id"] for row in group}),
                       successful=len(successful),
                       expected_outcomes=sum(truth(row["expectation_met"]) for row in group))
        for metric in ("goodput_mbps", "seconds", "retransmits",
                       "route_install_seconds", "progress_recovery_seconds", "ack_gap_seconds"):
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
    labels = [f"{item['scenario']}\n{item['mode']}" for item in summaries]
    colors = ["#2563eb" if item["mode"] == "failover" else "#64748b" for item in summaries]
    for metric, ylabel, title in (
        ("goodput_mbps", "Payload goodput (Mb/s)", "Goodput of successful transfers"),
        ("retransmits", "DATA retransmissions", "Retransmissions of successful transfers"),
        ("progress_recovery_seconds", "Seconds after failure request", "Application progress recovery"),
    ):
        fig, ax = plt.subplots(figsize=(max(7, len(summaries) * 1.2), 4.5))
        for index, item in enumerate(summaries):
            measurement = item[metric]
            if measurement:
                mean = measurement["mean"]
                ax.bar(index, mean, color=colors[index], width=.65)
                ax.errorbar(index, mean,
                            yerr=[[mean - measurement["minimum"]],
                                  [measurement["maximum"] - mean]],
                            color="#111827", capsize=4, fmt="none")
            else:
                ax.text(index, .03, "N/A", transform=ax.get_xaxis_transform(), ha="center")
        ax.set_xticks(range(len(labels)), labels)
        ax.set_ylabel(ylabel)
        ax.set_title(title + " (mean and min–max)")
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", alpha=.2)
        ax.set_axisbelow(True)
        fig.tight_layout()
        fig.savefig(output / f"{metric}.svg")
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(max(7, len(summaries) * 1.2), 4.5))
    rates = [100 * item["successful"] / item["observations"] for item in summaries]
    ax.bar(range(len(labels)), rates, color=colors)
    for index, item in enumerate(summaries):
        ax.text(index, rates[index] + 2, f"{item['successful']}/{item['observations']}", ha="center")
    ax.set_xticks(range(len(labels)), labels)
    ax.set_ylim(0, 115)
    ax.set_ylabel("Successful flows (%)")
    ax.set_title("Completion across all trials, including failed runs")
    fig.tight_layout()
    fig.savefig(output / "completion.svg")
    plt.close(fig)


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
             "| Scenario | Mode | Trials | Successful flows | Expected outcomes | Mean goodput (Mb/s) | Mean recovery (s) |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for item in summaries:
        def average(key):
            return f"{item[key]['mean']:.4f}" if item[key] else "N/A"
        lines.append(f"| {item['scenario']} | {item['mode']} | {item['trials']} | "
                     f"{item['successful']}/{item['observations']} | "
                     f"{item['expected_outcomes']}/{item['observations']} | "
                     f"{average('goodput_mbps')} | {average('progress_recovery_seconds')} |")
    (args.output / "summary.md").write_text("\n".join(lines) + "\n")
    if not args.no_plots:
        make_plots(summaries, args.output)
    print(args.output / "summary.md")


if __name__ == "__main__":
    main()
