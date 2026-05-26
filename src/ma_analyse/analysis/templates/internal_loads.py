"""Plot-Templates fuer interne Lasten aus Personen, Geraeten und Beleuchtung."""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from ...core.config import DATENBANK_DIR, TEST_OUTPUT_DIR
from ..components.figures import get_figure_size_inches
from ..components.rooms import get_room_data_file
from ..components.runtime import annotate_timestamp, get_run_id, sanitize_file_name
from ..components.time_windows import (
    MONTH_BOUNDARIES,
    MONTH_NAMES,
    MONTH_START_HOURS,
    build_energy_time_axis_config,
    filter_time_window,
    get_time_window,
)
from ..components.variants import get_variant_display_name, normalize_variant_name, strip_variant_suffix
from .catalog import (
    INTERNAL_LOADS_DAY_TEMPLATE,
    INTERNAL_LOADS_MONTH_TEMPLATE,
    INTERNAL_LOADS_MONTHLY_SUM_TEMPLATE,
    INTERNAL_LOADS_ROOM_COMPARISON_TEMPLATE,
    INTERNAL_LOADS_WEEK_TEMPLATE,
    INTERNAL_LOADS_YEAR_TEMPLATE,
    get_plot_template_spec,
)
from .timeline import validate_timeline_template_time_selection

LOAD_SERIES = (
    ("zone_energy_q_occ", "Personen", "#00a6d6"),
    ("zone_energy_q_equip", "Geraete", "#c00000"),
    ("zone_energy_q_light", "Beleuchtung", "#f2b400"),
)
PLOT_BG = "#fbfbfb"
GRID_COLOR = "#7d7d7d"
SPINE_COLOR = "#2e2e2e"
TEXT_COLOR = "#1f1f1f"


def _resolve_processed_variant_dir(datenbank_dir: str | Path, variant_name: str) -> Path:
    variant_stem = strip_variant_suffix(variant_name)
    variant_dir = Path(datenbank_dir) / normalize_variant_name(variant_stem, "_nutzdaten")
    if not variant_dir.exists():
        raise FileNotFoundError(f"Aufbereitete Variante nicht gefunden: {variant_dir}")
    return variant_dir


def _load_internal_loads_room_data(csv_file: str | Path) -> pd.DataFrame:
    df = pd.read_csv(csv_file)
    required_columns = ["time", *[column for column, _, _ in LOAD_SERIES]]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Fehlende Spalten in {csv_file}: {missing_columns}")

    result = df[required_columns].copy()
    for column in required_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.dropna(subset=required_columns)
    if result.empty:
        return pd.DataFrame(columns=required_columns)

    result["time"] = result["time"].floordiv(1).astype(int)
    result = result.groupby("time", as_index=False).mean(numeric_only=True)
    return result.sort_values(by="time").reset_index(drop=True)


def _load_variant_room_data(
    datenbank_dir: str | Path,
    variant_name: str,
    rooms: list[str] | tuple[str, ...],
) -> tuple[Path, dict[str, pd.DataFrame]]:
    processed_variant_dir = _resolve_processed_variant_dir(datenbank_dir, variant_name)
    room_data = {}
    for room_name in rooms:
        room_file = get_room_data_file(processed_variant_dir, room_name)
        if not os.path.exists(room_file):
            raise FileNotFoundError(f"Raum-CSV nicht gefunden: {room_file}")
        df = _load_internal_loads_room_data(room_file)
        if not df.empty:
            room_data[room_name] = df
    return processed_variant_dir, room_data


def _style_power_axis(ax, title: str, subtitle: str, ylabel: str = "Leistung [W]") -> None:
    ax.set_facecolor(PLOT_BG)
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", color=TEXT_COLOR, pad=10)
    if subtitle:
        ax.text(
            1.0,
            1.06,
            subtitle,
            transform=ax.transAxes,
            ha="right",
            va="bottom",
            fontsize=9,
            color=TEXT_COLOR,
        )
    ax.set_ylabel(ylabel, fontsize=10, color=TEXT_COLOR)
    ax.tick_params(axis="both", colors=TEXT_COLOR, labelsize=9)
    ax.grid(True, which="major", axis="both", color=GRID_COLOR, linestyle=(0, (5, 3)), linewidth=0.9, alpha=0.9)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_color(SPINE_COLOR)
        spine.set_linewidth(1.0)


def _add_generic_timeline_axis(figure, ax, axis_config) -> None:
    main_position = ax.get_position()
    timeline_height = 0.115
    timeline_gap = 0.018
    timeline_bottom = max(0.02, main_position.y0 - timeline_gap - timeline_height)
    timeline_ax = figure.add_axes(
        [
            main_position.x0,
            timeline_bottom,
            main_position.width,
            timeline_height,
        ]
    )
    timeline_ax.set_facecolor("white")
    timeline_ax.set_xlim(axis_config["x_lim"])
    timeline_ax.set_ylim(0, 1)
    timeline_ax.axis("off")

    line_y = 0.52
    timeline_ax.hlines(line_y, axis_config["x_lim"][0], axis_config["x_lim"][1], color=TEXT_COLOR, linewidth=1.0)
    for tick in axis_config.get("grid_ticks", axis_config["ticks"]):
        timeline_ax.vlines(tick, line_y, line_y + 0.10, color=TEXT_COLOR, linewidth=0.7)

    x_start, x_end = axis_config["x_lim"]
    for tick, label in zip(axis_config["ticks"], axis_config["labels"], strict=False):
        timeline_ax.vlines(tick, line_y - 0.10, line_y, color=TEXT_COLOR, linewidth=0.8)
        label_align = "left" if tick == x_start else "right" if tick == x_end else "center"
        timeline_ax.text(tick, line_y - 0.21, label, ha=label_align, va="top", fontsize=8.5, color=TEXT_COLOR)

    annotation_ticks = axis_config.get("annotation_ticks")
    annotation_labels = axis_config.get("annotation_labels")
    if annotation_ticks and annotation_labels:
        for tick, label in zip(annotation_ticks, annotation_labels, strict=False):
            timeline_ax.text(tick, line_y + 0.15, label, ha="center", va="bottom", fontsize=8.5, color=TEXT_COLOR)


def _format_time_subtitle(view: str, month: str | None = None, week: int | None = None, day: int | None = None) -> str:
    if view == "year":
        return "Zeitraum: Jan bis Dez"
    if view == "month":
        return f"Zeitraum: Monat {month}"
    if view == "week":
        return f"Zeitraum: KW {week:02d}"
    if view == "day":
        return f"Zeitraum: {day:02d}. {month}"
    return ""


def _draw_year_line_plot(
    room_df: pd.DataFrame,
    variant_name: str,
    room_name: str,
    output_file: str | Path,
) -> None:
    axis_config = build_energy_time_axis_config("year")
    figure, ax = plt.subplots(figsize=get_figure_size_inches("internal-loads.year.png", (12.8, 7.2)))
    figure.patch.set_facecolor("white")
    sorted_df = room_df.sort_values(by="time")

    for column, label, color in LOAD_SERIES:
        ax.plot(sorted_df["time"], sorted_df[column], color=color, linewidth=1.0, alpha=0.92, label=label)
    _style_power_axis(
        ax,
        f"Interne Lasten Jahresverlauf - {variant_name} / {room_name}",
        _format_time_subtitle("year"),
    )
    ax.set_xlim(axis_config["x_lim"])
    ax.set_xticks(axis_config.get("grid_ticks", axis_config["ticks"]))
    ax.set_xticklabels([])
    ax.tick_params(axis="x", length=0, labelbottom=False)
    ax.set_ylim(bottom=0)
    for boundary_tick in axis_config.get("boundary_ticks", []):
        ax.axvline(boundary_tick, color=SPINE_COLOR, linewidth=0.9, alpha=0.5)

    legend = ax.legend(loc="upper left", bbox_to_anchor=(0.0, -0.30), frameon=False, ncol=4, fontsize=9)
    for text in legend.get_texts():
        text.set_color(TEXT_COLOR)
    figure.subplots_adjust(left=0.08, right=0.98, top=0.80, bottom=0.34)
    _add_generic_timeline_axis(figure, ax, axis_config)
    annotate_timestamp(figure)
    figure.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(figure)


def _draw_time_line_plot(
    room_df: pd.DataFrame,
    variant_name: str,
    room_name: str,
    view: str,
    output_file: str | Path,
    month: str | None = None,
    week: int | None = None,
    day: int | None = None,
) -> None:
    if view == "month":
        time_window = get_time_window("month", month=month)
    elif view == "week":
        time_window = get_time_window("week", week=week)
    elif view == "day":
        time_window = get_time_window("day", month=month, day=day)
    else:
        raise ValueError(f"Nicht unterstuetzte Internal-Loads-Zeitansicht: {view}")

    filtered = filter_time_window(room_df[["time", *[column for column, _, _ in LOAD_SERIES]]].copy(), time_window)
    if filtered.empty:
        raise ValueError(f"Keine Daten fuer {variant_name} / {room_name} im gewaehlten Zeitraum gefunden.")

    axis_config = build_energy_time_axis_config(view, time_window=time_window)
    figure, ax = plt.subplots(figsize=get_figure_size_inches("internal-loads.timeline.png", (12.8, 7.2)))
    figure.patch.set_facecolor("white")

    for column, label, color in LOAD_SERIES:
        ax.plot(filtered["time_window"], filtered[column], color=color, linewidth=1.15, label=label)

    _style_power_axis(
        ax,
        f"Interne Lasten {time_window['title_text']} - {variant_name} / {room_name}",
        _format_time_subtitle(view, month=month, week=week, day=day),
    )
    ax.set_xlim(axis_config["x_lim"])
    ax.set_xticks(axis_config.get("grid_ticks", axis_config["ticks"]))
    ax.set_xticklabels([])
    ax.tick_params(axis="x", length=0, labelbottom=False)
    ax.set_ylim(bottom=0)
    for boundary_tick in axis_config.get("boundary_ticks", []):
        ax.axvline(boundary_tick, color=SPINE_COLOR, linewidth=0.8, alpha=0.45)

    legend = ax.legend(loc="upper left", bbox_to_anchor=(0.0, -0.31), frameon=False, ncol=4, fontsize=9)
    for text in legend.get_texts():
        text.set_color(TEXT_COLOR)
    figure.subplots_adjust(left=0.08, right=0.98, top=0.80, bottom=0.34)
    _add_generic_timeline_axis(figure, ax, axis_config)
    annotate_timestamp(figure)
    figure.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(figure)


def _get_profile_bar_width(view: str) -> float:
    if view == "day":
        return 0.78
    return 0.86


def _configure_profile_x_axis(ax, view: str, axis_config: dict, time_window: dict) -> bool:
    """Formatiert die x-Achse fuer gestapelte Lastprofile.

    Tagesprofile zeigen Uhrzeiten direkt an der Achse. Monats- und Wochenprofile
    behalten den separaten Zeitstrahl, damit die vielen Balken lesbar bleiben.
    """
    total_hours = time_window["end_hour"] - time_window["start_hour"]
    if view == "day":
        ticks = list(range(0, total_hours + 1, 2))
        ax.set_xlim(-0.5, total_hours - 0.5)
        ax.set_xticks(ticks)
        ax.set_xticklabels([f"{hour:02d}:00" for hour in ticks])
        ax.set_xlabel("Uhrzeit", fontsize=10, color=TEXT_COLOR)
        ax.tick_params(axis="x", length=0, labelbottom=True)
        return False

    ax.set_xlim(axis_config["x_lim"])
    ax.set_xticks(axis_config.get("grid_ticks", axis_config["ticks"]))
    ax.set_xticklabels([])
    ax.tick_params(axis="x", length=0, labelbottom=False)
    return True


def _draw_time_stacked_bar_plot(
    room_df: pd.DataFrame,
    variant_name: str,
    room_name: str,
    view: str,
    output_file: str | Path,
    month: str | None = None,
    week: int | None = None,
    day: int | None = None,
) -> None:
    if view == "month":
        time_window = get_time_window("month", month=month)
    elif view == "week":
        time_window = get_time_window("week", week=week)
    elif view == "day":
        time_window = get_time_window("day", month=month, day=day)
    else:
        raise ValueError(f"Nicht unterstuetzte Internal-Loads-Zeitansicht: {view}")

    filtered = filter_time_window(room_df[["time", *[column for column, _, _ in LOAD_SERIES]]].copy(), time_window)
    if filtered.empty:
        raise ValueError(f"Keine Daten fuer {variant_name} / {room_name} im gewaehlten Zeitraum gefunden.")

    axis_config = build_energy_time_axis_config(view, time_window=time_window)
    figure, ax = plt.subplots(figsize=get_figure_size_inches("internal-loads.profile.png", (12.8, 7.2)))
    figure.patch.set_facecolor("white")

    bottoms = [0.0] * len(filtered)
    x_values = filtered["time_window"]
    for column, label, color in LOAD_SERIES:
        ax.bar(
            x_values,
            filtered[column],
            bottom=bottoms,
            width=_get_profile_bar_width(view),
            color=color,
            edgecolor="white",
            linewidth=0.25,
            label=label,
            align="center",
        )
        bottoms = [bottom + value for bottom, value in zip(bottoms, filtered[column], strict=False)]

    _style_power_axis(
        ax,
        f"Interne Lasten {time_window['title_text']} - {variant_name} / {room_name}",
        _format_time_subtitle(view, month=month, week=week, day=day),
    )
    use_timeline_axis = _configure_profile_x_axis(ax, view, axis_config, time_window)
    ax.set_ylim(bottom=0)
    for boundary_tick in axis_config.get("boundary_ticks", []):
        ax.axvline(boundary_tick, color=SPINE_COLOR, linewidth=0.8, alpha=0.45)

    legend = ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), frameon=False, ncol=3, fontsize=10)
    for text in legend.get_texts():
        text.set_color(TEXT_COLOR)
    bottom_margin = 0.22 if view == "day" else 0.34
    figure.subplots_adjust(left=0.08, right=0.98, top=0.80, bottom=bottom_margin)
    if use_timeline_axis:
        _add_generic_timeline_axis(figure, ax, axis_config)
    annotate_timestamp(figure)
    figure.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(figure)


def _build_monthly_energy_table(room_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for index, month_name in enumerate(MONTH_NAMES):
        start_hour = MONTH_START_HOURS[index]
        end_hour = MONTH_BOUNDARIES[index]
        month_df = room_df[(room_df["time"] >= start_hour) & (room_df["time"] < end_hour)]
        row = {"month": month_name}
        for column, label, _ in LOAD_SERIES:
            row[label] = month_df[column].sum() / 1000.0
        rows.append(row)
    return pd.DataFrame(rows)


def _draw_monthly_sum_bars(
    room_df: pd.DataFrame,
    variant_name: str,
    room_name: str,
    output_file: str | Path,
) -> None:
    monthly_df = _build_monthly_energy_table(room_df)
    figure, ax = plt.subplots(figsize=get_figure_size_inches("internal-loads.monthly-sum.png", (11.6, 6.6)))
    figure.patch.set_facecolor("white")

    bottoms = [0.0] * len(monthly_df)
    for _, label, color in LOAD_SERIES:
        ax.bar(monthly_df["month"], monthly_df[label], bottom=bottoms, color=color, alpha=0.82, label=label)
        bottoms = [bottom + value for bottom, value in zip(bottoms, monthly_df[label], strict=False)]

    _style_power_axis(
        ax,
        f"Interne Lasten Monatssummen - {variant_name} / {room_name}",
        "Aggregation: Summe der Stundenwerte je Monat",
        ylabel="Energie [kWh]",
    )
    ax.set_xlabel("Monat", fontsize=10, color=TEXT_COLOR)
    ax.set_ylim(bottom=0)
    legend = ax.legend(loc="upper left", frameon=False, ncol=3, fontsize=9)
    for text in legend.get_texts():
        text.set_color(TEXT_COLOR)
    figure.tight_layout()
    annotate_timestamp(figure)
    figure.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(figure)


def _draw_room_comparison_bars(
    room_data: dict[str, pd.DataFrame],
    variant_name: str,
    output_file: str | Path,
) -> None:
    rows = []
    for room_name, room_df in room_data.items():
        row = {"room": room_name}
        for column, label, _ in LOAD_SERIES:
            row[label] = room_df[column].sum() / 1000.0
        rows.append(row)
    if not rows:
        raise ValueError(f"Keine Raumdaten fuer {variant_name} gefunden.")

    comparison_df = pd.DataFrame(rows)
    figure, ax = plt.subplots(figsize=get_figure_size_inches("internal-loads.room-comparison.png", (11.8, 6.6)))
    figure.patch.set_facecolor("white")

    bottoms = [0.0] * len(comparison_df)
    for _, label, color in LOAD_SERIES:
        ax.bar(comparison_df["room"], comparison_df[label], bottom=bottoms, color=color, alpha=0.82, label=label)
        bottoms = [bottom + value for bottom, value in zip(bottoms, comparison_df[label], strict=False)]

    _style_power_axis(
        ax,
        f"Interne Lasten Raumvergleich - {variant_name}",
        "Aggregation: Jahressumme je Raum",
        ylabel="Energie [kWh]",
    )
    ax.set_xlabel("Raum", fontsize=10, color=TEXT_COLOR)
    ax.tick_params(axis="x", rotation=35)
    ax.set_ylim(bottom=0)
    legend = ax.legend(loc="upper left", frameon=False, ncol=3, fontsize=9)
    for text in legend.get_texts():
        text.set_color(TEXT_COLOR)
    figure.tight_layout()
    annotate_timestamp(figure)
    figure.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(figure)


def validate_internal_loads_template_request(
    template: str,
    variants: list[str] | tuple[str, ...] | None,
    rooms: list[str] | tuple[str, ...] | None,
    month: str | None = None,
    week: int | None = None,
    day: int | None = None,
) -> list[str]:
    """Prueft Mindestangaben fuer Internal-Loads-Templates."""
    errors = []
    spec = get_plot_template_spec(template)
    if spec is None or spec.metric != "internal_loads":
        errors.append(f"Unbekanntes Internal-Loads-Template: {template}")
        return errors
    if not variants:
        errors.append("plot-template erwartet mindestens eine Variante.")
    if not rooms:
        errors.append("plot-template erwartet mindestens einen Raum.")
    elif spec.requires_single_room and len(rooms) != 1:
        errors.append("Dieses plot-template erwartet genau einen Raum.")
    errors.extend(validate_timeline_template_time_selection(template, month=month, week=week, day=day))
    return errors


def _build_output_file(output_dir: Path, template: str, room_name: str | None = None) -> Path:
    if template == INTERNAL_LOADS_ROOM_COMPARISON_TEMPLATE:
        return output_dir / "internal_loads_room_comparison_template.png"
    if room_name is None:
        raise ValueError("Fuer raumbezogene Internal-Loads-Templates muss ein Raum uebergeben werden.")
    suffix_by_template = {
        INTERNAL_LOADS_YEAR_TEMPLATE: "year",
        INTERNAL_LOADS_MONTH_TEMPLATE: "month",
        INTERNAL_LOADS_WEEK_TEMPLATE: "week",
        INTERNAL_LOADS_DAY_TEMPLATE: "day",
        INTERNAL_LOADS_MONTHLY_SUM_TEMPLATE: "monthly_sum",
    }
    suffix = suffix_by_template[template]
    return output_dir / f"{sanitize_file_name(room_name)}_internal_loads_{suffix}_template.png"


def build_internal_loads_template(
    datenbank_dir: str | Path = DATENBANK_DIR,
    output_root: str | Path | None = TEST_OUTPUT_DIR,
    selected_variants: list[str] | tuple[str, ...] | None = None,
    rooms: list[str] | tuple[str, ...] | None = None,
    template: str = INTERNAL_LOADS_YEAR_TEMPLATE,
    month: str | None = None,
    week: int | None = None,
    day: int | None = None,
    run_id: str | None = None,
    debug: bool = False,
) -> str | list[str]:
    """Erzeugt Internal-Loads-Plot-Templates fuer eine oder mehrere Varianten."""
    errors = validate_internal_loads_template_request(
        template,
        selected_variants,
        rooms,
        month=month,
        week=week,
        day=day,
    )
    if errors:
        raise ValueError("; ".join(errors))

    spec = get_plot_template_spec(template)
    output_base = Path(output_root or TEST_OUTPUT_DIR)
    resolved_run_id = get_run_id("plot_template", run_id=run_id)
    output_files = []

    for variant_name in selected_variants:
        processed_variant_dir, room_data = _load_variant_room_data(datenbank_dir, variant_name, rooms)
        if not room_data:
            raise ValueError(f"Keine Internal-Loads-Daten fuer {variant_name} gefunden.")

        variant_display_name = get_variant_display_name(processed_variant_dir)
        output_dir = output_base / "PlotTemplates" / resolved_run_id / variant_display_name
        output_dir.mkdir(parents=True, exist_ok=True)

        if debug:
            print(f"Template: {template}")
            print(f"Template-Variante: {variant_name}")
            print(f"Template-Raeume: {', '.join(room_data)}")

        if template == INTERNAL_LOADS_ROOM_COMPARISON_TEMPLATE:
            output_file = _build_output_file(output_dir, template)
            _draw_room_comparison_bars(room_data, variant_display_name, output_file)
            output_files.append(str(output_file))
            continue

        room_name = rooms[0]
        room_df = room_data.get(room_name)
        if room_df is None or room_df.empty:
            raise ValueError(f"Keine Internal-Loads-Daten fuer {variant_name} / {room_name} gefunden.")

        output_file = _build_output_file(output_dir, template, room_name=room_name)
        if template == INTERNAL_LOADS_YEAR_TEMPLATE:
            _draw_year_line_plot(room_df, variant_display_name, room_name, output_file)
        elif template == INTERNAL_LOADS_MONTH_TEMPLATE:
            _draw_time_line_plot(
                room_df,
                variant_display_name,
                room_name,
                spec.view,
                output_file,
                month=month,
                week=week,
                day=day,
            )
        elif template in {INTERNAL_LOADS_WEEK_TEMPLATE, INTERNAL_LOADS_DAY_TEMPLATE}:
            _draw_time_stacked_bar_plot(
                room_df,
                variant_display_name,
                room_name,
                spec.view,
                output_file,
                month=month,
                week=week,
                day=day,
            )
        elif template == INTERNAL_LOADS_MONTHLY_SUM_TEMPLATE:
            _draw_monthly_sum_bars(room_df, variant_display_name, room_name, output_file)
        else:
            raise ValueError(f"Nicht unterstuetztes Internal-Loads-Template: {template}")
        output_files.append(str(output_file))

    if len(output_files) == 1:
        return output_files[0]
    return output_files
