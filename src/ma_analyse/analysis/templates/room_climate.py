"""Plot-Templates fuer thermisches Raumklima mit festen Overlay-Komponenten."""

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
from ..components.time_windows import build_energy_time_axis_config, filter_time_window, get_time_window
from ..components.variants import get_variant_display_name, normalize_variant_name, strip_variant_suffix
from .catalog import THERMAL_ROOM_CLIMATE_DAY_TEMPLATE, get_plot_template_spec
from .heating_year import DEFAULT_SETPOINT_MAX, DEFAULT_SETPOINT_MIN, load_hourly_prn_series
from .timeline import validate_timeline_template_time_selection

ROOM_TEMPERATURE_COLUMNS = ("temperatures_tairmean", "temperatures_top", "local_de_comf_diag_t_top")
OUTDOOR_COLUMN = "tair"
INTERNAL_LOAD_COLUMNS = ("zone_energy_q_occ", "zone_energy_q_equip", "zone_energy_q_light")
VENTILATION_COLUMN = "zone_energy_qventil"
COOLING_COLUMN = "zone_energy_q_cool"

PLOT_BG = "#fbfbfb"
GRID_COLOR = "#8f8f8f"
SPINE_COLOR = "#2e2e2e"
TEXT_COLOR = "#1f1f1f"
SETPOINT_BAND_COLOR = "#f4b183"
INTERNAL_LOAD_COLOR = "#ffc000"
VENTILATION_COLOR = "#8eb4e3"
COOLING_COLOR = "#20c7e8"
ROOM_TEMP_COLOR = "#ff0000"
OUTDOOR_TEMP_COLOR = "#7030a0"


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


def validate_room_climate_template_request(
    template: str,
    variants: list[str] | tuple[str, ...] | None,
    rooms: list[str] | tuple[str, ...] | None,
    setpoint_min: float = DEFAULT_SETPOINT_MIN,
    setpoint_max: float = DEFAULT_SETPOINT_MAX,
    month: str | None = None,
    week: int | None = None,
    day: int | None = None,
) -> list[str]:
    """Prueft Mindestangaben fuer Raumklima-Templates."""
    errors = []
    spec = get_plot_template_spec(template)
    if spec is None or spec.metric != "thermal_room_climate":
        errors.append(f"Unbekanntes Raumklima-Template: {template}")
        return errors
    if not variants:
        errors.append("plot-template erwartet mindestens eine Variante.")
    if not rooms or len(rooms) != 1:
        errors.append("Dieses plot-template erwartet genau einen Raum.")
    if setpoint_min >= setpoint_max:
        errors.append("setpoint-min muss kleiner als setpoint-max sein.")
    errors.extend(validate_timeline_template_time_selection(template, month=month, week=week, day=day))
    return errors


def _load_room_climate_data(csv_file: str | Path) -> pd.DataFrame:
    df = pd.read_csv(csv_file)
    room_temperature_column = next((column for column in ROOM_TEMPERATURE_COLUMNS if column in df.columns), None)
    required_columns = ["time", *INTERNAL_LOAD_COLUMNS, VENTILATION_COLUMN, COOLING_COLUMN]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if room_temperature_column is None:
        missing_columns.append("room_temperature")
    if missing_columns:
        raise ValueError(f"Fehlende Raumklima-Spalten in {csv_file}: {missing_columns}")

    selected_columns = [*required_columns, room_temperature_column]
    result = df[selected_columns].copy()
    for column in selected_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.dropna(subset=["time"])
    if result.empty:
        return pd.DataFrame(
            columns=[
                "time",
                "internal_loads_total",
                "ventilation",
                "cooling",
                "room_temperature",
            ]
        )

    result["time"] = result["time"].floordiv(1).astype(int)
    result = result.groupby("time", as_index=False).mean(numeric_only=True)
    result["internal_loads_total"] = result[list(INTERNAL_LOAD_COLUMNS)].sum(axis=1)
    result["ventilation"] = result[VENTILATION_COLUMN]
    result["cooling"] = -result[COOLING_COLUMN].abs()
    result = result.rename(columns={room_temperature_column: "room_temperature"})
    return result[
        [
            "time",
            "internal_loads_total",
            "ventilation",
            "cooling",
            "room_temperature",
        ]
    ].sort_values(by="time")


def _load_template_dataframe(
    datenbank_dir: str | Path,
    input_dir: str | Path,
    variant_name: str,
    room_name: str,
) -> tuple[pd.DataFrame, str]:
    processed_variant_dir = _resolve_processed_variant_dir(datenbank_dir, variant_name)
    input_variant_dir = _resolve_input_variant_dir(input_dir, variant_name)
    room_file = get_room_data_file(processed_variant_dir, room_name)
    if not os.path.exists(room_file):
        raise FileNotFoundError(f"Raum-CSV nicht gefunden: {room_file}")

    room_df = _load_room_climate_data(room_file)
    report_aux_file = input_variant_dir / "REPORT-AUX.prn"
    if not report_aux_file.exists():
        raise FileNotFoundError(f"REPORT-AUX.prn nicht gefunden: {report_aux_file}")

    try:
        outdoor_df = load_hourly_prn_series(report_aux_file, OUTDOOR_COLUMN).rename(
            columns={OUTDOOR_COLUMN: "outdoor_temperature"}
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

    time_window = get_time_window(view, month=month, week=week, day=day)
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


def _configure_time_axis(ax, view: str, axis_config: dict, time_window: dict | None = None) -> None:
    ax.set_facecolor(PLOT_BG)
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
        ax.set_xticklabels([f"{hour:02d}" if hour < 24 else "0" for hour in ticks])
        ax.set_xlabel("Tagesstunde [h]", fontsize=10, fontweight="bold", color=TEXT_COLOR)
        return

    ax.set_xlim(axis_config["x_lim"])
    ax.set_xticks(axis_config["ticks"])
    ax.set_xticklabels(axis_config["labels"], rotation=axis_config.get("rotation", 0))
    ax.set_xlabel(axis_config["x_label"], fontsize=10, fontweight="bold", color=TEXT_COLOR)


def _configure_temperature_axis(ax_temp, view_df: pd.DataFrame, setpoint_min: float, setpoint_max: float) -> None:
    values = pd.concat(
        [view_df["room_temperature"], view_df["outdoor_temperature"]],
        ignore_index=True,
    ).dropna()
    if values.empty:
        ymin, ymax = 15.0, 40.0
    else:
        ymin = min(15.0, float(values.min()) - 2.0, setpoint_min - 2.0)
        ymax = max(40.0, float(values.max()) + 2.0, setpoint_max + 2.0)
    ax_temp.set_ylim(ymin, ymax)
    ax_temp.set_ylabel("Temperatur [degC]", fontsize=10, fontweight="bold", color=TEXT_COLOR)
    ax_temp.tick_params(axis="y", colors=TEXT_COLOR, labelsize=9)
    for spine in ax_temp.spines.values():
        spine.set_color(SPINE_COLOR)
        spine.set_linewidth(1.0)


def _configure_power_axis(ax_power, view_df: pd.DataFrame) -> None:
    power_columns = ["internal_loads_total", "ventilation", "cooling"]
    max_abs = max(float(view_df[power_columns].abs().max().max()), 1.0)
    ax_power.set_ylim(-max_abs * 1.15, max_abs * 1.15)
    ax_power.set_ylabel("Leistung [W]", fontsize=10, fontweight="bold", color=TEXT_COLOR)
    ax_power.tick_params(axis="y", colors=TEXT_COLOR, labelsize=9)
    for spine in ax_power.spines.values():
        spine.set_color(SPINE_COLOR)
        spine.set_linewidth(1.0)


def _draw_room_climate_plot(
    plot_df: pd.DataFrame,
    variant_name: str,
    room_name: str,
    view: str,
    output_file: str | Path,
    setpoint_min: float = DEFAULT_SETPOINT_MIN,
    setpoint_max: float = DEFAULT_SETPOINT_MAX,
    month: str | None = None,
    week: int | None = None,
    day: int | None = None,
) -> None:
    view_df, time_window = _build_view_dataframe(plot_df, view, month=month, week=week, day=day)
    if view_df.empty:
        raise ValueError(f"Keine Raumklimadaten fuer {variant_name} / {room_name} im Zeitraum gefunden.")

    axis_config = build_energy_time_axis_config(view, time_window=time_window)
    figure, ax_temp = plt.subplots(figsize=get_figure_size_inches("thermal-room-climate.template.png", (12.8, 7.2)))
    figure.patch.set_facecolor("white")
    ax_power = ax_temp.twinx()

    x_values = view_df["time_axis"]
    ax_temp.axhspan(setpoint_min, setpoint_max, color=SETPOINT_BAND_COLOR, alpha=0.35, zorder=0)
    ax_power.fill_between(
        x_values,
        0,
        view_df["internal_loads_total"],
        color=INTERNAL_LOAD_COLOR,
        alpha=0.5,
        linewidth=0.8,
        edgecolor=INTERNAL_LOAD_COLOR,
        step="mid" if view == "day" else None,
    )
    ax_power.fill_between(
        x_values,
        0,
        view_df["ventilation"],
        color=VENTILATION_COLOR,
        alpha=0.55,
        linewidth=0.8,
        edgecolor="#4472c4",
        step="mid" if view == "day" else None,
    )
    ax_power.fill_between(
        x_values,
        0,
        view_df["cooling"],
        color=COOLING_COLOR,
        alpha=0.55,
        linewidth=0.8,
        edgecolor="#00a8d8",
        step="mid" if view == "day" else None,
    )
    ax_temp.plot(
        x_values, view_df["room_temperature"], color=ROOM_TEMP_COLOR, linewidth=2.2, label="Raumlufttemperatur"
    )
    ax_temp.plot(
        x_values,
        view_df["outdoor_temperature"],
        color=OUTDOOR_TEMP_COLOR,
        linewidth=2.2,
        label="Aussenlufttemperatur",
    )

    ax_temp.set_title(
        f"Thermisches Raumklima {view.capitalize()} - {variant_name} / {room_name}",
        loc="center",
        fontsize=13,
        fontweight="bold",
        color=TEXT_COLOR,
        pad=12,
    )
    ax_temp.text(
        1.0,
        1.04,
        _format_subtitle(view, month=month, week=week, day=day),
        transform=ax_temp.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        color=TEXT_COLOR,
    )
    _configure_time_axis(ax_temp, view, axis_config, time_window=time_window)
    _configure_temperature_axis(ax_temp, view_df, setpoint_min, setpoint_max)
    _configure_power_axis(ax_power, view_df)

    handles = [
        Patch(facecolor=SETPOINT_BAND_COLOR, edgecolor="#f4a460", alpha=0.35, label="Sollwertband"),
        Patch(facecolor=INTERNAL_LOAD_COLOR, edgecolor=INTERNAL_LOAD_COLOR, alpha=0.5, label="Interne Lasten total"),
        Patch(facecolor=VENTILATION_COLOR, edgecolor="#4472c4", alpha=0.55, label="Lueftung"),
        Patch(facecolor=COOLING_COLOR, edgecolor="#00a8d8", alpha=0.55, label="Raumkaelte"),
        Line2D([0], [0], color=ROOM_TEMP_COLOR, linewidth=2.2, label="Raumlufttemperatur"),
        Line2D([0], [0], color=OUTDOOR_TEMP_COLOR, linewidth=2.2, label="Aussenlufttemperatur"),
    ]
    figure.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.02),
        frameon=False,
        ncol=3,
        fontsize=8.5,
    )
    figure.subplots_adjust(left=0.08, right=0.92, top=0.84, bottom=0.22)
    annotate_timestamp(figure)
    figure.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(figure)


def _build_output_file(output_dir: Path, room_name: str, view: str) -> Path:
    return output_dir / f"{sanitize_file_name(room_name)}_thermal_room_climate_{view}_template.png"


def build_room_climate_template(
    datenbank_dir: str | Path = DATENBANK_DIR,
    input_dir: str | Path = INPUT_DIR,
    output_root: str | Path | None = TEST_OUTPUT_DIR,
    selected_variants: list[str] | tuple[str, ...] | None = None,
    rooms: list[str] | tuple[str, ...] | None = None,
    template: str = THERMAL_ROOM_CLIMATE_DAY_TEMPLATE,
    setpoint_min: float = DEFAULT_SETPOINT_MIN,
    setpoint_max: float = DEFAULT_SETPOINT_MAX,
    month: str | None = None,
    week: int | None = None,
    day: int | None = None,
    run_id: str | None = None,
    debug: bool = False,
) -> str | list[str]:
    """Erzeugt Raumklima-Templates fuer eine oder mehrere Varianten."""
    errors = validate_room_climate_template_request(
        template,
        selected_variants,
        rooms,
        setpoint_min=setpoint_min,
        setpoint_max=setpoint_max,
        month=month,
        week=week,
        day=day,
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
            raise ValueError(f"Keine Raumklimadaten fuer {variant_name} / {room_name} gefunden.")

        output_dir = output_base / "PlotTemplates" / resolved_run_id / variant_display_name
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = _build_output_file(output_dir, room_name, spec.view)

        if debug:
            print(f"Template: {template}")
            print(f"Template-Variante: {variant_name}")
            print(f"Template-Raum: {room_name}")

        _draw_room_climate_plot(
            plot_df,
            variant_display_name,
            room_name,
            spec.view,
            output_file,
            setpoint_min=setpoint_min,
            setpoint_max=setpoint_max,
            month=month,
            week=week,
            day=day,
        )
        output_files.append(str(output_file))

    if len(output_files) == 1:
        return output_files[0]
    return output_files
