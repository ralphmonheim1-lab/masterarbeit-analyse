"""Vorlage fuer Heating-Jahresdiagramme mit zusaetzlichen Temperaturkurven."""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from ...core.config import DATENBANK_DIR, INPUT_DIR, TEST_OUTPUT_DIR
from ...settings.plot_templates import OPERATIVE_OVERLAY_ID, OUTDOOR_OVERLAY_ID
from ..components.figures import get_figure_size_inches
from ..components.heating_year_layout import add_heating_year_timeline_axis, style_heating_year_power_axis
from ..components.rooms import get_room_data_file
from ..components.runtime import annotate_timestamp, get_run_id, sanitize_file_name
from ..components.time_windows import build_energy_time_axis_config
from ..components.variants import get_variant_display_name, normalize_variant_name, strip_variant_suffix
from .catalog import HEATING_YEAR_TEMPLATE, get_plot_template_spec, template_requires_single_room
from .timeline import validate_timeline_template_time_selection

REQUIRED_HEATING_COLUMN = "zone_energy_q_heat"
OPERATIVE_TEMPERATURE_COLUMNS = ("temperatures_top", "local_de_comf_diag_t_top")
DEFAULT_SETPOINT_MIN = 21.0
DEFAULT_SETPOINT_MAX = 26.0
DEFAULT_TEMPERATURE_YMIN = -20.0
DEFAULT_TEMPERATURE_YMAX = 40.0
DEFAULT_OUTDOOR_COLUMN = "tair"
DEFAULT_SHOW_SETPOINT_BAND = True
DEFAULT_SHOW_OUTDOOR_TEMPERATURE = True
DEFAULT_SHOW_OPERATIVE_TEMPERATURE = True
TARGET_HOURS = 8760

PLOT_BG = "#fbfbfb"
GRID_COLOR = "#b8b8b8"
SPINE_COLOR = "#2e2e2e"
TEXT_COLOR = "#1f1f1f"
HEATING_COLOR = "#ff0000"
OUTDOOR_COLOR = "#2563eb"
OPERATIVE_COLOR = "#2a9d8f"
SETPOINT_BAND_COLOR = "#9ad29f"
FREE_OVERLAY_COLORS = ["#7c3aed", "#f97316", "#0f766e", "#b91c1c", "#4b5563", "#a16207"]
RESERVED_OVERLAY_COLUMNS = {"time", "room", REQUIRED_HEATING_COLUMN}
DEFAULT_FIXED_OVERLAYS = [
    {
        "id": OUTDOOR_OVERLAY_ID,
        "label": "Außenlufttemperatur",
        "source": "aux",
        "column": DEFAULT_OUTDOOR_COLUMN,
        "axis": "temperature",
        "enabled": True,
        "color": OUTDOOR_COLOR,
    },
    {
        "id": OPERATIVE_OVERLAY_ID,
        "label": "Operative Temperatur",
        "source": "csv",
        "column": OPERATIVE_TEMPERATURE_COLUMNS[0],
        "fallback_columns": [OPERATIVE_TEMPERATURE_COLUMNS[1]],
        "axis": "temperature",
        "enabled": True,
        "color": OPERATIVE_COLOR,
    },
]


def validate_template_request(
    template: str,
    variants: list[str] | tuple[str, ...] | None,
    rooms: list[str] | tuple[str, ...] | None,
    setpoint_min: float,
    setpoint_max: float,
    temperature_ymin: float,
    temperature_ymax: float,
    validate_setpoint_band: bool = True,
    month: str | None = None,
    week: int | None = None,
    day: int | None = None,
) -> list[str]:
    """Prueft die fachlichen Mindestangaben fuer den Template-Lauf."""
    errors = []
    spec = get_plot_template_spec(template)
    if spec is None:
        errors.append(f"Unbekanntes Template: {template}")
    if not variants:
        errors.append("plot-template erwartet mindestens eine Variante.")
    if not rooms:
        errors.append("plot-template erwartet mindestens einen Raum.")
    elif template_requires_single_room(template) and len(rooms) != 1:
        errors.append("Dieses plot-template erwartet genau einen Raum.")
    if spec is not None and spec.name == HEATING_YEAR_TEMPLATE:
        if validate_setpoint_band and setpoint_min >= setpoint_max:
            errors.append("setpoint-min muss kleiner als setpoint-max sein.")
        if temperature_ymin >= temperature_ymax:
            errors.append("temperature-ymin muss kleiner als temperature-ymax sein.")
        if validate_setpoint_band and (setpoint_min < temperature_ymin or setpoint_max > temperature_ymax):
            errors.append("Das Sollwertband muss innerhalb der Temperaturachse liegen.")
    errors.extend(validate_timeline_template_time_selection(template, month=month, week=week, day=day))
    return errors


def _normalize_fixed_overlays(fixed_overlays: list[dict] | tuple[dict, ...] | None) -> dict[str, dict]:
    """Normalisiert feste, per Config definierte Standard-Overlays nach ID."""
    overlays = fixed_overlays if fixed_overlays is not None else DEFAULT_FIXED_OVERLAYS
    color_by_id = {
        OUTDOOR_OVERLAY_ID: OUTDOOR_COLOR,
        OPERATIVE_OVERLAY_ID: OPERATIVE_COLOR,
    }
    normalized: dict[str, dict] = {}

    for raw_overlay in overlays or []:
        if not isinstance(raw_overlay, dict):
            continue
        overlay_id = str(raw_overlay.get("id", "")).strip()
        source = str(raw_overlay.get("source", "")).strip().lower()
        column = str(raw_overlay.get("column", "")).strip()
        axis = str(raw_overlay.get("axis", "")).strip().lower()
        if not overlay_id or source not in {"csv", "aux"} or axis not in {"heat", "temperature"} or not column:
            continue

        fallback_columns = raw_overlay.get("fallback_columns")
        if isinstance(fallback_columns, list):
            fallback_columns = [item.strip() for item in fallback_columns if isinstance(item, str) and item.strip()]
        else:
            fallback_columns = []

        normalized[overlay_id] = {
            "id": overlay_id,
            "source": source,
            "column": column.lower() if source == "aux" else column,
            "label": str(raw_overlay.get("label") or column).strip(),
            "axis": axis,
            "enabled": bool(raw_overlay.get("enabled", True)),
            "fallback_columns": fallback_columns,
            "color": raw_overlay.get("color") or color_by_id.get(overlay_id, TEXT_COLOR),
        }
    return normalized


def _get_fixed_overlay(
    fixed_overlays: list[dict] | tuple[dict, ...] | None,
    overlay_id: str,
    enabled: bool,
) -> dict | None:
    overlay = _normalize_fixed_overlays(fixed_overlays).get(overlay_id)
    if overlay is None or not enabled or not overlay.get("enabled", True):
        return None
    return overlay


def _read_prn_file(file_path: str | Path) -> pd.DataFrame:
    with open(file_path, "r", encoding="utf-8") as handle:
        header_line = handle.readline().strip()
        if header_line.startswith("#"):
            header_line = header_line[1:].strip()
        column_names = [column.lower() for column in header_line.split()]
        return pd.read_csv(handle, sep=r"\s+", names=column_names, header=None)


def _read_prn_columns(file_path: str | Path) -> list[str]:
    with open(file_path, "r", encoding="utf-8") as handle:
        header_line = handle.readline().strip()
    if header_line.startswith("#"):
        header_line = header_line[1:].strip()
    return [column.lower() for column in header_line.split()]


def load_hourly_prn_series(file_path: str | Path, value_column: str) -> pd.DataFrame:
    """Laedt eine PRN-Spalte und mittelt sub-stuendige Werte auf Stunden."""
    value_column = value_column.lower()
    df = _read_prn_file(file_path)
    if "time" not in df.columns:
        raise ValueError(f"Spalte 'time' fehlt in {file_path}")
    if value_column not in df.columns:
        raise ValueError(f"Spalte '{value_column}' fehlt in {file_path}")

    df["time"] = pd.to_numeric(df["time"], errors="coerce")
    df[value_column] = pd.to_numeric(df[value_column], errors="coerce")
    df = df.dropna(subset=["time", value_column])
    if df.empty:
        return pd.DataFrame(columns=["time", value_column])

    df["hour"] = df["time"].floordiv(1).astype(int)
    hourly = df.groupby("hour", as_index=False)[value_column].mean(numeric_only=True)
    hourly = hourly.rename(columns={"hour": "time"})
    hourly = hourly[(hourly["time"] >= 0) & (hourly["time"] < TARGET_HOURS)]
    return hourly.sort_values(by="time").reset_index(drop=True)


def load_hourly_prn_columns(file_path: str | Path, value_columns: list[str] | tuple[str, ...]) -> pd.DataFrame:
    """Laedt mehrere PRN-Spalten und mittelt sub-stuendige Werte auf Stunden."""
    normalized_columns = [column.lower() for column in value_columns if column]
    if not normalized_columns:
        return pd.DataFrame(columns=["time"])
    df = _read_prn_file(file_path)
    if "time" not in df.columns:
        raise ValueError(f"Spalte 'time' fehlt in {file_path}")
    missing_columns = [column for column in normalized_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Spalten fehlen in {file_path}: {missing_columns}")

    df["time"] = pd.to_numeric(df["time"], errors="coerce")
    for column in normalized_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["time"])
    if df.empty:
        return pd.DataFrame(columns=["time", *normalized_columns])

    df["hour"] = df["time"].floordiv(1).astype(int)
    hourly = df.groupby("hour", as_index=False)[normalized_columns].mean(numeric_only=True)
    hourly = hourly.rename(columns={"hour": "time"})
    hourly = hourly[(hourly["time"] >= 0) & (hourly["time"] < TARGET_HOURS)]
    return hourly.sort_values(by="time").reset_index(drop=True)


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


def _is_reserved_overlay_column(column: str) -> bool:
    return column in RESERVED_OVERLAY_COLUMNS or column.endswith("_order")


def _list_numeric_csv_columns(csv_file: str | Path) -> list[str]:
    df = pd.read_csv(csv_file, nrows=200)
    columns = []
    for column in df.columns:
        if _is_reserved_overlay_column(column):
            continue
        values = pd.to_numeric(df[column], errors="coerce")
        if values.notna().any():
            columns.append(column)
    return columns


def _list_aux_columns(report_aux_file: str | Path, reserved_columns: set[str] | None = None) -> list[str]:
    reserved_columns = reserved_columns or set()
    return [
        column
        for column in _read_prn_columns(report_aux_file)
        if column not in {"time", "order"} and column not in reserved_columns
    ]


def list_heating_year_overlay_sources(
    datenbank_dir: str | Path,
    input_dir: str | Path,
    variant_name: str,
    room_name: str,
    outdoor_column: str = DEFAULT_OUTDOOR_COLUMN,
    fixed_overlays: list[dict] | tuple[dict, ...] | None = None,
) -> dict[str, list[str]]:
    """Listet frei auswaehlbare Overlay-Spalten aus Raum-CSV und REPORT-AUX."""
    processed_variant_dir = _resolve_processed_variant_dir(datenbank_dir, variant_name)
    input_variant_dir = _resolve_input_variant_dir(input_dir, variant_name)
    room_file = get_room_data_file(processed_variant_dir, room_name)
    report_aux_file = input_variant_dir / "REPORT-AUX.prn"
    outdoor_overlay = _get_fixed_overlay(fixed_overlays, OUTDOOR_OVERLAY_ID, enabled=True)
    resolved_outdoor_column = outdoor_overlay["column"] if outdoor_overlay is not None else outdoor_column

    if not os.path.exists(room_file):
        raise FileNotFoundError(f"Raum-CSV nicht gefunden: {room_file}")
    if not report_aux_file.exists():
        raise FileNotFoundError(f"REPORT-AUX.prn nicht gefunden: {report_aux_file}")

    return {
        "csv": _list_numeric_csv_columns(room_file),
        "aux": _list_aux_columns(report_aux_file, reserved_columns={resolved_outdoor_column.lower()}),
    }


def _resolve_csv_overlay_column(df: pd.DataFrame, overlay: dict | None, fallback_columns=()) -> str | None:
    if overlay is None:
        candidates = list(fallback_columns)
    else:
        candidates = [overlay["column"], *overlay.get("fallback_columns", [])]
    return next((column for column in candidates if column in df.columns), None)


def _load_room_template_data(
    csv_file: str | Path,
    operative_overlay: dict | None = None,
    require_operative: bool = True,
) -> pd.DataFrame:
    df = pd.read_csv(csv_file)
    missing_columns = [column for column in ("time", REQUIRED_HEATING_COLUMN) if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Fehlende Spalten in {csv_file}: {missing_columns}")

    operative_column = _resolve_csv_overlay_column(
        df,
        operative_overlay,
        fallback_columns=OPERATIVE_TEMPERATURE_COLUMNS,
    )
    if operative_column is None and require_operative:
        raise ValueError(f"Keine operative Temperaturspalte in {csv_file} gefunden.")

    selected_columns = ["time", REQUIRED_HEATING_COLUMN]
    if operative_column is not None:
        selected_columns.append(operative_column)
    selected_columns.extend(
        column for column in df.columns if column not in selected_columns and not _is_reserved_overlay_column(column)
    )
    result = df[selected_columns].copy()
    result["time"] = pd.to_numeric(result["time"], errors="coerce")
    for column in selected_columns:
        if column == "time":
            continue
        result[column] = pd.to_numeric(result[column], errors="coerce")
    required_subset = ["time", REQUIRED_HEATING_COLUMN]
    if operative_column is not None:
        required_subset.append(operative_column)
    result = result.dropna(subset=required_subset)
    if result.empty:
        return pd.DataFrame(columns=["time", "q_heat", "operative_temperature"])

    result["time"] = result["time"].floordiv(1).astype(int)
    result = result.groupby("time", as_index=False).mean(numeric_only=True)
    result = result.rename(columns={REQUIRED_HEATING_COLUMN: "q_heat"})
    if operative_column is not None:
        result["operative_temperature"] = result[operative_column]
    result = result[(result["time"] >= 0) & (result["time"] < TARGET_HOURS)]
    return result.sort_values(by="time").reset_index(drop=True)


def _normalize_overlay_lines(overlay_lines: list[dict] | tuple[dict, ...] | None) -> list[dict]:
    normalized = []
    for index, raw_overlay in enumerate(overlay_lines or []):
        if not isinstance(raw_overlay, dict) or not raw_overlay.get("enabled", True):
            continue
        source = str(raw_overlay.get("source", "")).strip().lower()
        column = str(raw_overlay.get("column", "")).strip()
        axis = str(raw_overlay.get("axis", "")).strip().lower()
        if source not in {"csv", "aux"} or axis not in {"heat", "temperature"} or not column:
            raise ValueError(f"Ungueltige Overlay-Linie: {raw_overlay}")
        normalized.append(
            {
                "source": source,
                "column": column.lower() if source == "aux" else column,
                "label": str(raw_overlay.get("label") or column).strip(),
                "axis": axis,
                "color": raw_overlay.get("color") or FREE_OVERLAY_COLORS[index % len(FREE_OVERLAY_COLORS)],
            }
        )
    return normalized


def _build_template_dataframe(
    datenbank_dir: str | Path,
    input_dir: str | Path,
    variant_name: str,
    room_name: str,
    outdoor_column: str,
    show_outdoor_temperature: bool = DEFAULT_SHOW_OUTDOOR_TEMPERATURE,
    show_operative_temperature: bool = DEFAULT_SHOW_OPERATIVE_TEMPERATURE,
    overlay_lines: list[dict] | tuple[dict, ...] | None = None,
    fixed_overlays: list[dict] | tuple[dict, ...] | None = None,
) -> tuple[pd.DataFrame, str]:
    processed_variant_dir = _resolve_processed_variant_dir(datenbank_dir, variant_name)
    input_variant_dir = _resolve_input_variant_dir(input_dir, variant_name)
    room_file = get_room_data_file(processed_variant_dir, room_name)
    if not os.path.exists(room_file):
        raise FileNotFoundError(f"Raum-CSV nicht gefunden: {room_file}")

    normalized_overlays = _normalize_overlay_lines(overlay_lines)
    outdoor_overlay = _get_fixed_overlay(fixed_overlays, OUTDOOR_OVERLAY_ID, show_outdoor_temperature)
    operative_overlay = _get_fixed_overlay(fixed_overlays, OPERATIVE_OVERLAY_ID, show_operative_temperature)
    room_df = _load_room_template_data(
        room_file,
        operative_overlay=operative_overlay,
        require_operative=show_operative_temperature and operative_overlay is not None,
    )
    for overlay in normalized_overlays:
        if overlay["source"] != "csv":
            continue
        if overlay["column"] not in room_df.columns:
            raise ValueError(f"CSV-Spalte '{overlay['column']}' fehlt in {room_file}")

    report_aux_file = input_variant_dir / "REPORT-AUX.prn"
    aux_columns = []
    if outdoor_overlay is not None:
        aux_columns.append(outdoor_overlay["column"])
    aux_columns.extend(overlay["column"] for overlay in normalized_overlays if overlay["source"] == "aux")
    aux_columns = list(dict.fromkeys(column.lower() for column in aux_columns if column))

    merged = room_df
    if aux_columns:
        if not report_aux_file.exists():
            raise FileNotFoundError(f"REPORT-AUX.prn nicht gefunden: {report_aux_file}")
        outdoor_df = load_hourly_prn_columns(report_aux_file, aux_columns)
        rename_map = {}
        if outdoor_overlay is not None:
            rename_map[outdoor_overlay["column"].lower()] = "outdoor_temperature"
        for overlay in normalized_overlays:
            if overlay["source"] == "aux":
                rename_map.setdefault(overlay["column"], f"aux__{overlay['column']}")
        outdoor_df = outdoor_df.rename(columns=rename_map)
        merged = pd.merge(room_df, outdoor_df, on="time", how="left")
    return merged.sort_values(by="time").reset_index(drop=True), get_variant_display_name(processed_variant_dir)


def _add_year_timeline_axis(figure, axis_config, timeline_bottom=0.145):
    """Zeichnet den separaten Jahres-Zeitstrahl wie in den Heating-Zeitplots."""
    return add_heating_year_timeline_axis(figure, axis_config, timeline_bottom=timeline_bottom)


def _style_main_axes(ax_heat, ax_temp, axis_config, temperature_ymin, temperature_ymax, heat_ymin=0, heat_ylabel=None):
    style_heating_year_power_axis(
        ax_heat,
        axis_config,
        heat_ymin=heat_ymin,
        heat_ylabel=heat_ylabel or "Heizleistung [W]",
    )

    ax_temp.set_ylim(temperature_ymin, temperature_ymax)
    ax_temp.set_ylabel("Temperatur [°C]", fontsize=10, color=TEXT_COLOR)
    ax_temp.tick_params(axis="y", colors=TEXT_COLOR, labelsize=9)
    if temperature_ymin == -20 and temperature_ymax == 40:
        ax_temp.set_yticks([-20, -10, 0, 10, 20, 30, 40])

    for spine in ax_temp.spines.values():
        spine.set_color(SPINE_COLOR)
        spine.set_linewidth(1.1)


def _draw_heating_year_template(
    plot_df: pd.DataFrame,
    variant_name: str,
    room_name: str,
    output_file: str | Path,
    setpoint_min: float,
    setpoint_max: float,
    temperature_ymin: float,
    temperature_ymax: float,
    show_setpoint_band: bool = DEFAULT_SHOW_SETPOINT_BAND,
    show_outdoor_temperature: bool = DEFAULT_SHOW_OUTDOOR_TEMPERATURE,
    show_operative_temperature: bool = DEFAULT_SHOW_OPERATIVE_TEMPERATURE,
    overlay_lines: list[dict] | tuple[dict, ...] | None = None,
    fixed_overlays: list[dict] | tuple[dict, ...] | None = None,
):
    axis_config = build_energy_time_axis_config("year")
    figure, ax_heat = plt.subplots(figsize=get_figure_size_inches("heating.timeline.single.png", (12.8, 7.2)))
    figure.patch.set_facecolor("white")
    ax_temp = ax_heat.twinx()

    title = f"Heating Jahresansicht - {variant_name} / {room_name}"
    ax_heat.set_title(title, loc="center", fontsize=14, fontweight="bold", color="black", pad=28)
    ax_heat.text(
        1.0,
        1.02,
        "Von 01.01.2025 bis 31.12.2025",
        transform=ax_heat.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        color="black",
    )

    handles = []
    band_handle = None
    if show_setpoint_band:
        band = ax_temp.axhspan(setpoint_min, setpoint_max, color=SETPOINT_BAND_COLOR, alpha=0.22, zorder=0)
        band_label = f"Sollwertband {setpoint_min:g}-{setpoint_max:g} °C"
        band_handle = Patch(facecolor=band.get_facecolor(), edgecolor="none", alpha=0.35, label=band_label)

    heat_line = ax_heat.plot(
        plot_df["time"],
        plot_df["q_heat"],
        color=HEATING_COLOR,
        linewidth=0.8,
        alpha=0.95,
        label="Heizleistung",
        zorder=3,
    )[0]
    handles.append(heat_line)

    temperature_axis_used = show_setpoint_band
    heat_axis_extra_used = False
    outdoor_overlay = _get_fixed_overlay(fixed_overlays, OUTDOOR_OVERLAY_ID, show_outdoor_temperature)
    operative_overlay = _get_fixed_overlay(fixed_overlays, OPERATIVE_OVERLAY_ID, show_operative_temperature)
    if outdoor_overlay is not None and "outdoor_temperature" in plot_df.columns:
        outdoor_line = ax_temp.plot(
            plot_df["time"],
            plot_df["outdoor_temperature"],
            color=outdoor_overlay["color"],
            linewidth=1.0,
            alpha=0.95,
            label=outdoor_overlay["label"],
            zorder=2,
        )[0]
        handles.append(outdoor_line)
        temperature_axis_used = True

    if operative_overlay is not None and "operative_temperature" in plot_df.columns:
        operative_line = ax_temp.plot(
            plot_df["time"],
            plot_df["operative_temperature"],
            color=operative_overlay["color"],
            linewidth=1.1,
            alpha=0.95,
            label=operative_overlay["label"],
            zorder=2,
        )[0]
        handles.append(operative_line)
        temperature_axis_used = True

    for overlay in _normalize_overlay_lines(overlay_lines):
        data_column = overlay["column"] if overlay["source"] == "csv" else f"aux__{overlay['column']}"
        if data_column not in plot_df.columns:
            raise ValueError(f"Overlay-Spalte '{overlay['column']}' fehlt in den Plotdaten.")
        target_axis = ax_heat if overlay["axis"] == "heat" else ax_temp
        line = target_axis.plot(
            plot_df["time"],
            plot_df[data_column],
            color=overlay["color"],
            linewidth=1.0,
            alpha=0.92,
            label=overlay["label"],
            zorder=2,
        )[0]
        handles.append(line)
        if overlay["axis"] == "heat":
            heat_axis_extra_used = True
        else:
            temperature_axis_used = True

    if band_handle is not None:
        handles.append(band_handle)

    heat_ymin = 0
    heat_columns = (
        ["q_heat"]
        + [
            overlay["column"]
            for overlay in _normalize_overlay_lines(overlay_lines)
            if overlay["source"] == "csv" and overlay["axis"] == "heat" and overlay["column"] in plot_df.columns
        ]
        + [
            f"aux__{overlay['column']}"
            for overlay in _normalize_overlay_lines(overlay_lines)
            if overlay["source"] == "aux"
            and overlay["axis"] == "heat"
            and f"aux__{overlay['column']}" in plot_df.columns
        ]
    )
    heat_min = plot_df[heat_columns].min(numeric_only=True).min()
    if pd.notna(heat_min) and heat_min < 0:
        heat_ymin = heat_min * 1.08

    _style_main_axes(
        ax_heat,
        ax_temp,
        axis_config,
        temperature_ymin,
        temperature_ymax,
        heat_ymin=heat_ymin,
        heat_ylabel="Leistung [W]" if heat_axis_extra_used else "Heizleistung [W]",
    )
    if not temperature_axis_used:
        ax_temp.set_yticks([])
        ax_temp.set_ylabel("")

    figure.subplots_adjust(left=0.08, right=0.92, top=0.80, bottom=0.298)

    _add_year_timeline_axis(figure, axis_config, timeline_bottom=0.145)

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


def build_heating_year_template(
    datenbank_dir: str | Path = DATENBANK_DIR,
    input_dir: str | Path = INPUT_DIR,
    output_root: str | Path | None = TEST_OUTPUT_DIR,
    selected_variants: list[str] | tuple[str, ...] | None = None,
    rooms: list[str] | tuple[str, ...] | None = None,
    template: str = HEATING_YEAR_TEMPLATE,
    setpoint_min: float = DEFAULT_SETPOINT_MIN,
    setpoint_max: float = DEFAULT_SETPOINT_MAX,
    temperature_ymin: float = DEFAULT_TEMPERATURE_YMIN,
    temperature_ymax: float = DEFAULT_TEMPERATURE_YMAX,
    outdoor_column: str = DEFAULT_OUTDOOR_COLUMN,
    show_setpoint_band: bool = DEFAULT_SHOW_SETPOINT_BAND,
    show_outdoor_temperature: bool = DEFAULT_SHOW_OUTDOOR_TEMPERATURE,
    show_operative_temperature: bool = DEFAULT_SHOW_OPERATIVE_TEMPERATURE,
    overlay_lines: list[dict] | tuple[dict, ...] | None = None,
    fixed_overlays: list[dict] | tuple[dict, ...] | None = None,
    run_id: str | None = None,
    debug: bool = False,
) -> str | list[str]:
    """Erzeugt den Heating-Jahresplot fuer eine oder mehrere Varianten und genau einen Raum."""
    errors = validate_template_request(
        template,
        selected_variants,
        rooms,
        setpoint_min,
        setpoint_max,
        temperature_ymin,
        temperature_ymax,
        validate_setpoint_band=show_setpoint_band,
    )
    if errors:
        raise ValueError("; ".join(errors))

    room_name = rooms[0]
    resolved_run_id = get_run_id("plot_template", run_id=run_id)
    output_base = Path(output_root or TEST_OUTPUT_DIR)
    output_files = []

    for variant_name in selected_variants:
        plot_df, variant_display_name = _build_template_dataframe(
            datenbank_dir,
            input_dir,
            variant_name,
            room_name,
            outdoor_column,
            show_outdoor_temperature=show_outdoor_temperature,
            show_operative_temperature=show_operative_temperature,
            overlay_lines=overlay_lines,
            fixed_overlays=fixed_overlays,
        )
        if plot_df.empty:
            raise ValueError(f"Keine Daten fuer {variant_name} / {room_name} gefunden.")

        output_dir = output_base / "PlotTemplates" / resolved_run_id / variant_display_name
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{sanitize_file_name(room_name)}_heating_year_template.png"

        if debug:
            print(f"Template-Variante: {variant_name}")
            print(f"Template-Datenpunkte: {len(plot_df)}")
            if show_outdoor_temperature:
                outdoor_overlay = _get_fixed_overlay(fixed_overlays, OUTDOOR_OVERLAY_ID, show_outdoor_temperature)
                print(f"Außenluft-Spalte: {outdoor_overlay['column'] if outdoor_overlay else outdoor_column}")
            if overlay_lines:
                print(f"Freie Overlay-Linien: {len(_normalize_overlay_lines(overlay_lines))}")

        _draw_heating_year_template(
            plot_df,
            variant_display_name,
            room_name,
            output_file,
            setpoint_min,
            setpoint_max,
            temperature_ymin,
            temperature_ymax,
            show_setpoint_band=show_setpoint_band,
            show_outdoor_temperature=show_outdoor_temperature,
            show_operative_temperature=show_operative_temperature,
            overlay_lines=overlay_lines,
            fixed_overlays=fixed_overlays,
        )
        output_files.append(str(output_file))

    if len(output_files) == 1:
        return output_files[0]
    return output_files
