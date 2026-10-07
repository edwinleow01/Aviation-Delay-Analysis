"""Static matplotlib charts for the report.

Each chart makes one point: the title states the finding, highlighted marks
carry the colour, everything else is neutral grey.
"""

from __future__ import annotations

import textwrap

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

HIGHLIGHT = "#2a78d6"
NEUTRAL = "#c3c2b7"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e0"
SURFACE = "#fcfcfb"

# Single-hue sequential ramp (light -> dark blue) for magnitude.
SEQUENTIAL = LinearSegmentedColormap.from_list(
    "seq_blue", ["#f3f7fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
)


def apply_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "figure.dpi": 110,
            "savefig.dpi": 200,
            "font.size": 10,
            "axes.edgecolor": GRID,
            "axes.labelcolor": TEXT_SECONDARY,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.titlecolor": TEXT,
            "axes.titlelocation": "left",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "xtick.color": TEXT_SECONDARY,
            "ytick.color": TEXT_SECONDARY,
            "legend.frameon": False,
        }
    )


def _titles(fig, ax, title: str, subtitle: str | None, width: int = 95) -> None:
    lines = textwrap.wrap(subtitle, width) if subtitle else []
    ax.set_title(title, pad=10 + 14 * len(lines))
    if lines:
        ax.annotate("\n".join(lines), (0, 1), xycoords="axes fraction", xytext=(0, 6), textcoords="offset points",
                    color=TEXT_SECONDARY, fontsize=9.5, va="bottom")


def ranked_bars(
    df: pd.DataFrame,
    value: str,
    title: str,
    subtitle: str | None = None,
    xlabel: str = "",
    highlight: list[str] | None = None,
    reference: float | None = None,
    reference_label: str = "Network average",
    fmt: str = "{:.1f}",
    top_n: int | None = 15,
):
    """Horizontal ranked bars, largest on top. ``highlight`` = index labels to colour."""
    data = df[value].sort_values(ascending=False)
    if top_n:
        data = data.head(top_n)
    data = data.iloc[::-1]  # barh draws bottom-up
    labels = [str(i) for i in data.index]
    highlight = {str(h) for h in (highlight or [])}
    colors = [HIGHLIGHT if lab in highlight else NEUTRAL for lab in labels]

    fig, ax = plt.subplots(figsize=(8, 0.32 * len(data) + 1.6))
    ax.barh(labels, data.values, color=colors, height=0.68, edgecolor=SURFACE, linewidth=1)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    if reference is not None:
        ax.axvline(reference, color=TEXT_SECONDARY, linewidth=1, linestyle=(0, (4, 3)))
        ax.set_ylim(-0.6, len(data) + 0.2)  # headroom row for the reference label
        ax.text(reference, len(data) - 0.45, f" {reference_label}", color=TEXT_SECONDARY, fontsize=8.5, va="bottom")
    for y, (lab, v) in enumerate(zip(labels, data.values)):
        if lab in highlight:
            ax.text(v, y, " " + fmt.format(v), va="center", color=TEXT, fontsize=9)
    ax.set_xlabel(xlabel)
    _titles(fig, ax, title, subtitle)
    fig.tight_layout()
    return fig


def heatmap(
    grid_df: pd.DataFrame,
    title: str,
    subtitle: str | None = None,
    xlabel: str = "",
    ylabel: str = "",
    colorbar_label: str = "",
    fmt: str = "{:.1f}",
    annotate: bool = False,
):
    """Sequential-colour heatmap; NaN cells (too few flights) are left blank."""
    fig, ax = plt.subplots(figsize=(10, 0.42 * len(grid_df) + 1.8))
    im = ax.imshow(grid_df.values, aspect="auto", cmap=SEQUENTIAL)
    ax.set_xticks(range(grid_df.shape[1]), [str(c) for c in grid_df.columns])
    ax.set_yticks(range(grid_df.shape[0]), [str(r) for r in grid_df.index])
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    if annotate:
        vmax = pd.Series(grid_df.values.ravel()).max()
        for i in range(grid_df.shape[0]):
            for j in range(grid_df.shape[1]):
                v = grid_df.values[i, j]
                if pd.notna(v):
                    ax.text(j, i, fmt.format(v), ha="center", va="center", fontsize=7.5,
                            color="white" if v > 0.6 * vmax else TEXT)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.outline.set_visible(False)
    cb.set_label(colorbar_label, color=TEXT_SECONDARY)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    _titles(fig, ax, title, subtitle)
    fig.tight_layout()
    return fig


def profile_line(
    series: pd.Series,
    title: str,
    subtitle: str | None = None,
    xlabel: str = "",
    ylabel: str = "",
    reference: float | None = None,
    reference_label: str = "Network average",
):
    """Single-series line (e.g. carrier-delay minutes by scheduled departure hour)."""
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.plot(series.index, series.values, color=HIGHLIGHT, linewidth=2, marker="o", markersize=4)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    if reference is not None:
        ax.axhline(reference, color=TEXT_SECONDARY, linewidth=1, linestyle=(0, (4, 3)))
        ax.text(series.index.min(), reference, f"{reference_label}\n", color=TEXT_SECONDARY, fontsize=8.5, va="bottom")
    ax.set_xticks(list(series.index))
    ax.set_ylim(bottom=0)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    _titles(fig, ax, title, subtitle)
    fig.tight_layout()
    return fig
