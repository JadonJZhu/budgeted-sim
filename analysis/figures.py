"""Figures for the write-up. Usage: python analysis/figures.py"""
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fit.data import HERE, scenes  # noqa: E402
from sim.models import Real, budget  # noqa: E402
from sim.physics import GATE_Y, HEIGHT, WIDTH, simulate  # noqa: E402

OUT = os.path.join(HERE, "writeup", "figures")
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#d9d8d4"
SERIES = {"budget": "#2a78d6", "full": "#eb6834", "crowding": "#1baf7a", "how": "#eda100"}
LABELS = {"budget": "Budget (ours)", "full": "Full CSM", "crowding": "Crowding noise", "how": "How only"}
A_COL, B_COL, GRAY = "#1baf7a", "#2a78d6", "#8c8b88"

plt.rcParams.update({"font.size": 8, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "font.family": "DejaVu Sans"})


def table(ax, title):
    ax.set_xlim(-75, WIDTH)
    ax.set_ylim(0, HEIGHT)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.add_patch(plt.Rectangle((0, 0), WIDTH, HEIGHT, fc="#fafaf8", ec=MUTED, lw=0.6))
    ax.add_patch(plt.Rectangle((0, 0), WIDTH, 25, fc="#222"))
    ax.add_patch(plt.Rectangle((0, HEIGHT - 25), WIDTH, 25, fc="#222"))
    ax.add_patch(plt.Rectangle((0, 25), 25, GATE_Y[0] - 25, fc="#222"))
    ax.add_patch(plt.Rectangle((0, GATE_Y[1]), 25, HEIGHT - 25 - GATE_Y[1], fc="#222"))
    ax.add_patch(plt.Rectangle((0, GATE_Y[0]), 25, GATE_Y[1] - GATE_Y[0], fc="#e34948"))
    ax.set_title(title, fontsize=8, color=INK, loc="left")


def draw_run(ax, run, names, upto, highlight):
    for n in names:
        if n not in run.paths:
            continue
        p = run.paths[n][:upto]
        p = p[(p[:, 0] > -45) & (p[:, 0] < WIDTH + 40)]
        if len(p) == 0:
            continue
        col = A_COL if n == "A" else B_COL if n == "B" else (INK if n in highlight else GRAY)
        lw = 1.6 if n in ("A", "B") or n in highlight else 0.6
        ax.plot(p[:, 0], p[:, 1], color=col, lw=lw, solid_capstyle="round", zorder=2)
        ax.add_patch(plt.Circle(p[-1], 30, fc=col, ec="white", lw=0.8, alpha=0.9, zorder=3))
        if n in ("A", "B") or n in highlight:
            ax.text(*p[-1], n, ha="center", va="center", fontsize=6.5, color="white",
                    weight="bold", zorder=4)


def fig_nine_ball():
    """The 9-ball whether-only video: what happened, and two imagined replays without A."""
    scene = scenes()["9ball_w_only_1"]
    real = Real(scene)
    names = real.names
    upto = real.run.exit_step + 30
    full = simulate(scene, leave_out=("A",), record=True, full_length=True)
    b2 = budget(real, 2, "a_targets")
    rep = {m: (real.paths[m], real.vels[m]) for m in names if m not in b2 and m != "A"}
    bud = simulate(scene, leave_out=("A",), replay=rep, record=True, full_length=True)
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.15))
    table(axes[0], "Real video\nB goes in")
    draw_run(axes[0], real.run, names, upto, {"E", "F"})
    table(axes[1], "Without A, full simulation\nE and F block B: B misses")
    draw_run(axes[1], full, names, upto, {"E", "F"})
    table(axes[2], "Without A, budget of 2 (B and E)\nF follows its real path: B goes in")
    draw_run(axes[2], bud, names, upto, {"E", "F"})
    fig.tight_layout(pad=0.3, w_pad=0.6)
    save(fig, "nine_ball")


def fig_error_by_balls():
    ev = json.load(open(os.path.join(HERE, "results", "evaluation.json")))
    fig, ax = plt.subplots(figsize=(3.3, 2.1))
    xs = [2, 3, 6, 9, 12]
    for name in ("full", "how", "crowding", "budget"):
        e = ev["group"][name]["error_by_balls"]
        y = [e[str(x)] for x in xs]
        ax.plot(xs, y, color=SERIES[name], lw=2 if name == "budget" else 1.3,
                marker="o", ms=3.5, mec="white", mew=0.6, label=LABELS[name], zorder=3)
    ax.set_xticks(xs)
    ax.set_xlabel("Balls in the video")
    ax.set_ylabel("Mean absolute error\n(points, held-out videos)")
    ax.set_ylim(0, 40)
    ax.grid(axis="y", color=GRID, lw=0.5)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, fontsize=6.5, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.22))
    fig.tight_layout(pad=0.3)
    save(fig, "error_by_balls")


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    fig.savefig(os.path.join(OUT, name + ".pdf"))
    fig.savefig(os.path.join(OUT, name + ".png"), dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    fig_nine_ball()
    fig_error_by_balls()
