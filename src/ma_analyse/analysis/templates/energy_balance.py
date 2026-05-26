"""Plot-Templates fuer Energiebilanzen mit Leistungskomponenten und Temperaturen."""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from ...core.config import DATENBANK_DIR, INPUT_DIR, TEST_OUTPUT_DIR
from ..components.figures import get_figure_size_inches
from ..components.rooms import get_room_data_file
from ..components.runtime import annotate_timestamp, get_run_id, sanitize_file_name
from ..components.time_windows import (
    build_energy_time_axis_config,
    filter_time_window,
    get_time_window,
)
from ..components.variants import get_variant_display_name, normalize_variant_name, strip_variant_suffix
from .catalog import (
    ENERGY_BALANCE_YEAR_TEMPLATE,
    get_plot_template_spec,
)
from .heating_year import load_hourly_prn_series
from .timeline import validate_timeline_template_time_selection

POWER_COMPONENTS = (
    ("zone_energy_q_heat", "Raumwaerme", "#cf5f5f"),
    ("zone_energy_qventil", "Lueftung", "#1f77c8"),
    ("zone_energy_q_light", "Interne Lasten Beleuchtung", "#fff200"),
    ("zone_energy_qwcb", "Huelle & Waermebruecken", "#a85f1a"),
    ("zone_energy_ql_a", "Infiltration", "#ff4fc3"),
    ("zone_energy_q_cool", "Raumkaelte", "#54e1df"),
    ("zone_energy_qintw", "Innenwaende & Massen", "#1eb15a"),
    ("zone_energy_q_occ", "Interne Lasten Personen", "#c9bf92"),
    ("zone_energy_qwind", "Fenster und Solar", "#ffbd1a"),
    ("zone_energy_q_equip", "Interne Lasten Geraete", "#8c8c8c"),
)
ROOM_TEMPERATURE_COLUMNS = ("temperatures_tairmean", "temperatures_top", "local_de_comf_diag_t_top")
OUTDOOR_COLUMN = "tair"
PLOT_BG = "#fbfbfb"
GRID_COLOR = "#898989"
SPINE_COLOR = "#2e2e2e"
TEXT_COLOR = "#1f1f1f"
OUTDOOR_COLOR = "#7030a0"
ROOM_TEMP_COLOR = "#ff0000"


def _resolve_processed_variant_dir(datenbank_dir: str | Path, variant_name: str) -> Path:
    variant_stem = strip_variant_suffix(variant_name)
    variant_dir = Path(datenbank_dir) / normalize_variant_name(variant_stem, "_nutzdaten")
    if not variant_dir.exists():
        raise FileNotFoundError(f"Aufbereitete Variante nicht gefunden: {variant_dir}")
    return variant_dir


def _resolve_input_variant_dir(input_dir: str | Path, variant_name: str) -> Path:
    variant_stem = strip_variant_suffix(variant_name)
    candidates = [
        Path(input_dir) / variant_name,
        Path(input_dir) / variant_stem,
        Path(input_dir) / f"{variant_stem}_rohdaten",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Rohdaten-Variante fuer REPORT-AUX.prn nicht gefunden: {variant_stem}")


def _load_energy_balance_room_data(csv_file: str | Path) -> pd.DataFrame:
    df = pd.read_csv(csv_file)
    required_columns = ["time", *[column for column, _, _ in POWER_COMPONENTS]]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Fehlende Bilanzspalten in {csv_file}: {missing_columns}")

    room_temperature_column = next((column for column in ROOM_TEMPERATURE_COLUMNS if column in df.columns), None)
    if room_temperature_column is None:
        raise ValueError(f"Keine Raumtemperaturspalte in {csv_file} gefunden.")

    selected_columns = [*required_columns, room_temperature_column]
    result = df[selected_columns].copy()
    for column in selected_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.dropna(subset=["time"])
    if result.empty:
        return pd.DataFrame(columns=[*required_columns, "room_temperature"])

    result["time"] = result["time"].floordiv(1).astype(int)
    result = result.groupby("time", as_index=False).mean(numeric_only=True)
    result = result.rename(columns={room_temperature_column: "room_temperature"})
    return result.sort_values(by="time").reset_index(drop=True)


def _load_template_dataframe(
    datenbank_dir: str | Path,
    input_dir: str | Path,
    variant_name: str,
    room_name: str,
    outdoor_column: str = OUTDOOR_COLUMN,
) -> tuple[pd.DataFrame, str]:
    processed_variant_dir = _resolve_processed_variant_dir(datenbank_dir, variant_name)
    input_variant_dir = _resolve_input_variant_dir(input_dir, variant_name)
    room_file = get_room_data_file(processed_variant_dir, room_name)
    if not os.path.exists(room_file):
        raise FileNotFoundError(f"Raum-CSV nicht gefunden: {room_file}")

    room_df = _load_energy_balance_room_data(room_file)
    report_aux_file = input_variant_dir / "REPORT-AUX.prn"
    if not report_aux_file.exists():
        raise FileNotFoundError(f"REPORT-AUX.prn nicht gefunden: {report_aux_file}")

    try:
        outdoor_df = load_hourly_prn_series(report_aux_file, outdoor_column).rename(
            columns={outdoor_column.lower(): "outdoor_temperature"}
        )
    except ValueError:
        outdoor_df = load_hourly_prn_series(report_aux_file, "tout").rename(columns={"tout": "outdoor_temperature"})
    merged = pd.merge(room_df, outdoor_df, on="time", how="left")
    return merged.sort_values(by="time").reset_index(drop=True), get_variant_display_name(processed_variant_dir)


def _build_view_dataframe(
    plot_df: pd.DataFrame,
    view: str,
    month: str | None = None,
    week: int | None = None,
    day: int | None = None,
) -> tuple[pd.DataFrame, dict | None]:
    if view == "year":
        result = plot_df.copy()
        result["time_axis"] = result["time"]
        return result, None

    if view == "month":
        time_window = get_time_window("month", month=month)
    elif view == "week":
        time_window = get_time_window("week", week=week)
    elif view == "day":
        time_window = get_time_window("day", month=month, day=day)
    else:
        raise ValueError(f"Nicht unterstuetzte Energiebilanzansicht: {view}")

    filtered = filter_time_window(plot_df.copy(), time_window)
    if filtered.empty:
        return filtered, time_window
    filtered["time_axis"] = filtered["time_window"]
    return filtered, time_window


def _format_subtitle(view: str, month: str | None = None, week: int | None = None, day: int | None = None) -> str:
    if view == "year":
        return "Zeitraum: Jan bis Dez"
    if view == "month":
        return f"Zeitraum: Monat {month}"
    if view == "week":
        return f"Zeitraum: KW {week:02d}"
    if view == "day":
        return f"Zeitraum: {day:02d}. {month}"
    return ""


def _configure_power_axis(ax, view: str, axis_config: dict, time_window: dict | None = None) -> None:
    ax.set_facecolor(PLOT_BG)
    ax.set_ylabel("Leistung [W]", fontsize=10, fontweight="bold", color=TEXT_COLOR)
    ax.tick_params(axis="both", colors=TEXT_COLOR, labelsize=9)
    ax.grid(True, which="major", axis="both", color=GRID_COLOR, linestyle=(0, (5, 3)), linewidth=0.85, alpha=0.85)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_color(SPINE_COLOR)
        spine.set_linewidth(1.0)

    if view == "day" and time_window is not None:
        total_hours = time_window["end_hour"] - time_window["start_hour"]
        ticks = list(range(0, total_hours + 1, 1))
        ax.set_xlim(0, total_hours)
        ax.set_xticks(ticks)
        ax.set_xticklabels([f"{hour:02d}" if hour < 24 else "00" for hour in ticks])
        ax.set_xlabel("Zeit [h]", fontsize=10, fontweight="bold", color=TEXT_COLOR)
        return

    ax.set_xlim(axis_config["x_lim"])
    ax.set_xticks(axis_config["ticks"])
    ax.set_xticklabels(axis_config["labels"], rotation=axis_config.get("rotation", 0))
    ax.set_xlabel(axis_config["x_label"], fontsize=10, fontweight="bold", color=TEXT_COLOR)


def _configure_temperature_axis(ax_temp, plot_df: pd.DataFrame) -> None:
    temperature_columns = [column for column in ("outdoor_temperature", "room_temperature") if column in plot_df]
    values = pd.concat([plot_df[column] for column in temperature_columns], ignore_index=True).dropna()
    if values.empty:
        ymin, ymax = 0, 40
    else:
        ymin = min(0, int((values.min() - 2) // 5 * 5))
        ymax = max(40, int(((values.max() + 7) // 5) * 5))
    ax_temp.set_ylim(ymin, ymax)
    ax_temp.set_ylabel("Temperatur [degC]", fontsize=10, fontweight="bold", color=TEXT_COLOR)
    ax_temp.tick_params(axis="y", colors=TEXT_COLOR, labelsize=9)
    for spine in ax_temp.spines.values():
        spine.set_color(SPINE_COLOR)
        spine.set_linewidth(1.0)


def _draw_signed_component_stack(ax, plot_df: pd.DataFrame) -> list[Patch]:
    x_values = plot_df["time_axis"]
    positive_base = pd.Series(0.0, index=plot_df.index)
    negative_base = pd.Series(0.0, index=plot_df.index)
    handles = []

    for column, label, color in POWER_COMPONENTS:
        values = pd.to_numeric(plot_df[column], errors="coerce").fillna(0.0)
        positive_values = values.clip(lower=0)
        negative_values = values.clip(upper=0)

        if positive_values.abs().sum() > 0:
            next_base = positive_base + positive_values
            ax.fill_between(x_values, positive_base, next_base, color=color, alpha=0.85, linewidth=0)
            positive_base = next_base

        if negative_values.abs().sum() > 0:
            next_base = negative_base + negative_values
            ax.fill_between(x_values, negative_base, next_base, color=color, alpha=0.85, linewidth=0)
            negative_base = next_base

        handles.append(Patch(facecolor=color, edgecolor="none", label=label))

    y_abs_max = max(float(positive_base.max()), abs(float(negative_base.min())), 1.0)
    ax.set_ylim(-y_abs_max * 1.12, y_abs_max * 1.12)
    ax.axhline(0, color=SPINE_COLOR, linewidth=0.9)
    return handles


def _draw_energy_balance_plot(
    plot_df: pd.DataFrame,
    variant_name: str,
    room_name: str,
    view: str,
    output_file: str | Path,
    month: str | None = None,
    week: int | None = None,
    day: int | None = None,
) -> None:
    view_df, time_window = _build_view_dataframe(plot_df, view, month=month, week=week, day=day)
    if view_df.empty:
        raise ValueError(f"Keine Energiebilanzdaten fuer {variant_name} / {room_name} im Zeitraum gefunden.")

    axis_config = build_energy_time_axis_config(view, time_window=time_window)
    figure, ax = plt.subplots(figsize=get_figure_size_inches("energy-balance.template.png", (12.8, 7.2)))
    figure.patch.set_facecolor("white")

    ax_temp = ax.twinx()
    component_handles = _draw_signed_component_stack(ax, view_df)
    if "outdoor_temperature" in view_df:
        ax_temp.plot(
            view_df["time_axis"],
            view_df["outdoor_temperature"],
            color=OUTDOOR_COLOR,
            linestyle=(0, (3, 1)),
            linewidth=1.4,
            label="Aussenlufttemperatur",
            zorder=5,
        )
    if "room_temperature" in view_df:
        ax_temp.plot(
            view_df["time_axis"],
            view_df["room_temperature"],
            color=ROOM_TEMP_COLOR,
            linestyle=(0, (3, 1)),
            linewidth=1.4,
            label="Raumlufttemperatur",
            zorder=5,
        )

    ax.set_title(
        f"Energiebilanz {view.capitalize()} - {variant_name} / {room_name}",
        loc="center",
        fontsize=13,
        fontweight="bold",
        color=TEXT_COLOR,
        pad=12,
    )
    ax.text(
        1.0,
        1.04,
        _format_subtitle(view, month=month, week=week, day=day),
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        color=TEXT_COLOR,
    )
    _configure_power_axis(ax, view, axis_config, time_window=time_window)
    _configure_temperature_axis(ax_temp, view_df)

    line_handles = [
        Line2D([0], [0], color=OUTDOOR_COLOR, linestyle=(0, (3, 1)), linewidth=1.6, label="Aussenlufttemperatur"),
        Line2D([0], [0], color=ROOM_TEMP_COLOR, linestyle=(0, (3, 1)), linewidth=1.6, label="Raumlufttemperatur"),
    ]
    legend = figure.legend(
        handles=[*component_handles, *line_handles],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.005),
        frameon=False,
        ncol=4,
        fontsize=8.5,
        columnspacing=1.2,
        handlelength=2.8,
        handletextpad=0.4,
    )
    for text in legend.get_texts():
        text.set_color("#555555")

    figure.subplots_adjust(left=0.08, right=0.92, top=0.84, bottom=0.28)
    annotate_timestamp(figure)
    figure.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(figure)


def validate_energy_balance_template_request(
    template: str,
    variants: list[str] | tuple[str, ...] | None,
    rooms: list[str] | tuple[str, ...] | None,
    month: str | None = None,
    week: int | None = None,
    day: int | None = None,
) -> list[str]:
    """Prueft Mindestangaben fuer Energiebilanz-Templates."""
    errors = []
    spec = get_plot_template_spec(template)
    if spec is None or spec.metric != "energy_balance":
        errors.append(f"Unbekanntes Energiebilanz-Template: {template}")
        return errors
    if not variants:
        errors.append("plot-template erwartet mindestens eine Variante.")
    if not rooms or len(rooms) != 1:
        errors.append("Dieses plot-template erwartet genau einen Raum.")
    errors.extend(validate_timeline_template_time_selection(template, month=month, week=week, day=day))
    return errors


def _build_output_file(output_dir: Path, room_name: str, view: str) -> Path:
    return output_dir / f"{sanitize_file_name(room_name)}_energy_balance_{view}_template.png"


def build_energy_balance_template(
    datenbank_dir: str | Path = DATENBANK_DIR,
    input_dir: str | Path = INPUT_DIR,
    output_root: str | Path | None = TEST_OUTPUT_DIR,
    selected_variants: list[str] | tuple[str, ...] | None = None,
    rooms: list[str] | tuple[str, ...] | None = None,
    template: str = ENERGY_BALANCE_YEAR_TEMPLATE,
    month: str | None = None,
    week: int | None = None,
    day: int | None = None,
    run_id: str | None = None,
    debug: bool = False,
) -> str | list[str]:
    """Erzeugt Energiebilanz-Plot-Templates fuer eine oder mehrere Varianten."""
    errors = validate_energy_balance_template_request(
        template, selected_variants, rooms, month=month, week=week, day=day
    )
    if errors:
        raise ValueError("; ".join(errors))

    spec = get_plot_template_spec(template)
    room_name = rooms[0]
    output_base = Path(output_root or TEST_OUTPUT_DIR)
    resolved_run_id = get_run_id("plot_template", run_id=run_id)
    output_files = []

    for variant_name in selected_variants:
        plot_df, variant_display_name = _load_template_dataframe(datenbank_dir, input_dir, variant_name, room_name)
        if plot_df.empty:
            raise ValueError(f"Keine Energiebilanzdaten fuer {variant_name} / {room_name} gefunden.")

        output_dir = output_base / "PlotTemplates" / resolved_run_id / variant_display_name
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = _build_output_file(output_dir, room_name, spec.view)

        if debug:
            print(f"Template: {template}")
            print(f"Template-Variante: {variant_name}")
            print(f"Template-Raum: {room_name}")

        _draw_energy_balance_plot(
            plot_df,
            variant_display_name,
            room_name,
            spec.view,
            output_file,
            month=month,
            week=week,
            day=day,
        )
        output_files.append(str(output_file))

    if len(output_files) == 1:
        return output_files[0]
    return output_files
