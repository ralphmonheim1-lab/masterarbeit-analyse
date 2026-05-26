"""Gemeinsames Layout fuer Heating-Jahresdiagramme ohne Overlay-Logik."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

from .figures import get_figure_size_inches
from .runtime import annotate_timestamp
from .time_windows import MONTH_BOUNDARIES, MONTH_NAMES, MONTH_START_HOURS, build_energy_time_axis_config

PLOT_BG = "#fbfbfb"
GRID_COLOR = "#b8b8b8"
SPINE_COLOR = "#2e2e2e"
TEXT_COLOR = "#1f1f1f"
HEATING_LINE_COLORS = ["#d62828", "#2563eb", "#2a9d8f", "#f77f00", "#7c3aed", "#0081a7"]
HEATING_SINGLE_LINE_COLOR = "#ff0000"


def add_heating_year_timeline_axis(figure, axis_config, timeline_bottom=0.145):
    """Zeichnet den Plot-Template-Jahreszeitstrahl unterhalb des Hauptdiagramms."""
    timeline_ax = figure.add_axes([0.08, timeline_bottom, 0.84, 0.12])
    timeline_ax.set_facecolor("white")
    timeline_ax.set_xlim(axis_config["x_lim"])
    timeline_ax.set_ylim(0, 1)
    timeline_ax.axis("off")

    line_y = 0.55
    arrow = FancyArrowPatch(
        (0.0, line_y),
        (1.02, line_y),
        transform=timeline_ax.transAxes,
        arrowstyle="->",
        mutation_scale=14,
        linewidth=1.3,
        color="black",
        clip_on=False,
    )
    timeline_ax.add_patch(arrow)

    x_start, x_end = axis_config["x_lim"]
    upper_ticks = axis_config.get("grid_ticks", axis_config["ticks"])
    lower_ticks = axis_config["ticks"]
    lower_labels = axis_config["labels"]

    for tick in upper_ticks:
        tick_line = timeline_ax.vlines(tick, line_y, line_y + 0.12, color="black", linewidth=1.0)
        tick_line.set_clip_on(False)

    for tick, label in zip(lower_ticks, lower_labels, strict=False):
        tick_line = timeline_ax.vlines(tick, line_y - 0.10, line_y, color="black", linewidth=1.0)
        tick_line.set_clip_on(False)
        if tick == x_start:
            label_align = "left"
        elif tick == x_end:
            label_align = "right"
        else:
            label_align = "center"
        timeline_ax.text(tick, line_y - 0.22, label, ha=label_align, va="top", fontsize=9, color="black")

    month_centers = [
        MONTH_START_HOURS[index] + ((MONTH_BOUNDARIES[index] - MONTH_START_HOURS[index]) / 2)
        for index in range(len(MONTH_NAMES))
    ]
    for tick, label in zip(month_centers, MONTH_NAMES, strict=False):
        timeline_ax.text(tick, line_y + 0.20, label, ha="center", va="bottom", fontsize=9, fontweight="bold")

    return timeline_ax


def style_heating_year_power_axis(ax, axis_config, heat_ymin=0, heat_ylabel="Heizleistung [W]"):
    """Formatiert die Hauptachse im Stil des Heating-Year-Templates."""
    ax.set_facecolor(PLOT_BG)
    ax.set_xlim(axis_config["x_lim"])
    ax.set_ylim(bottom=heat_ymin)
    ax.set_ylabel(heat_ylabel, fontsize=10, color=TEXT_COLOR)
    ax.set_xticks(axis_config.get("grid_ticks", axis_config["ticks"]))
    ax.set_xticklabels([])
    ax.tick_params(axis="x", length=0, labelbottom=False)
    ax.tick_params(axis="y", colors=TEXT_COLOR, labelsize=9)
    ax.grid(True, which="major", axis="both", color=GRID_COLOR, linewidth=0.9)

    for boundary_tick in axis_config.get("boundary_ticks", []):
        ax.axvline(boundary_tick, color=SPINE_COLOR, linewidth=1.0, alpha=0.55)

    for spine in ax.spines.values():
        spine.set_color(SPINE_COLOR)
        spine.set_linewidth(1.1)


def draw_heating_year_line_plot(
    plot_df: pd.DataFrame,
    x_col: str,
    group_col: str,
    title: str,
    subtitle: str,
    output_file: str | Path,
    line_colors: list[str] | tuple[str, ...] | None = None,
    single_series_legend_label: str | None = None,
):
    """Rendert ein Heating-Jahresdiagramm im Plot-Template-Stil ohne Overlays."""
    axis_config = build_energy_time_axis_config("year")
    series_names = list(dict.fromkeys(plot_df[group_col].tolist()))
    format_rule = "heating.timeline.single.png" if len(series_names) <= 1 else "heating.timeline.compare.png"
    figure, ax_heat = plt.subplots(figsize=get_figure_size_inches(format_rule, (12.8, 7.2)))
    figure.patch.set_facecolor("white")

    ax_heat.set_title(title, loc="center", fontsize=14, fontweight="bold", color="black", pad=28)
    ax_heat.text(
        1.0,
        1.02,
        subtitle,
        transform=ax_heat.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        color="black",
    )

    colors = list(line_colors or HEATING_LINE_COLORS)
    handles = []
    for index, series_name in enumerate(series_names):
        series_df = plot_df[plot_df[group_col] == series_name].sort_values(by=x_col)
        label = single_series_legend_label if len(series_names) == 1 and single_series_legend_label else series_name
        color = HEATING_SINGLE_LINE_COLOR if len(series_names) == 1 else colors[index % len(colors)]
        line = ax_heat.plot(
            series_df[x_col],
            series_df["q_heat"],
            color=color,
            linewidth=0.8 if len(series_names) == 1 else 1.0,
            alpha=0.95,
            label=label,
            zorder=3,
        )[0]
        handles.append(line)

    heat_ymin = 0
    heat_min = plot_df["q_heat"].min()
    if pd.notna(heat_min) and heat_min < 0:
        heat_ymin = heat_min * 1.08

    style_heating_year_power_axis(ax_heat, axis_config, heat_ymin=heat_ymin)
    figure.subplots_adjust(left=0.08, right=0.92, top=0.80, bottom=0.298)
    add_heating_year_timeline_axis(figure, axis_config, timeline_bottom=0.145)

    legend = figure.legend(
        handles=handles,
        loc="lower left",
        bbox_to_anchor=(0.08, 0.035),
        frameon=False,
        ncol=min(4, max(1, len(handles))),
        fontsize=8.5,
        handlelength=2.8,
        columnspacing=1.0,
    )
    for text in legend.get_texts():
        text.set_color(TEXT_COLOR)

    figure.text(0.50, 0.125, "Stunden [h]", ha="center", va="center", fontsize=10, color="black")
    annotate_timestamp(figure)
    figure.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(figure)
