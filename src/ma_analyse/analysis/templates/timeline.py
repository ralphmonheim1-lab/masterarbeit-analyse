"""Plot-Templates fuer Heating-/Cooling-Zeitansichten ohne Overlay-Logik."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from ...core.config import DATENBANK_DIR, TEST_OUTPUT_DIR
from .. import cooling as cooling_analysis
from .. import heating as heating_analysis
from ..components.rooms import get_room_data_file
from ..components.runtime import get_run_id, sanitize_file_name
from ..components.time_windows import (
    MAX_CALENDAR_WEEK,
    MONTH_DAY_COUNTS,
    MONTH_NAMES,
    filter_time_window,
    get_time_window,
)
from ..components.variants import get_variant_display_name, normalize_variant_name, strip_variant_suffix
from .catalog import HEATING_YEAR_TEMPLATE, get_plot_template_spec

METRIC_MODULES = {
    "heating": heating_analysis,
    "cooling": cooling_analysis,
}
METRIC_VALUE_COLUMNS = {
    "heating": ("zone_energy_q_heat", "q_heat"),
    "cooling": ("zone_energy_q_cool", "q_cool"),
}
VIEW_TITLES = {
    "year": "Jahresansicht",
    "month": "Monatsansicht",
    "week": "Wochenansicht",
    "day": "Tagesansicht",
}


def validate_timeline_template_time_selection(template: str, month=None, week=None, day=None) -> list[str]:
    """Validiert die Zeitangaben fuer nicht-overlay Plot-Templates."""
    spec = get_plot_template_spec(template)
    if spec is None or spec.name == HEATING_YEAR_TEMPLATE:
        return []

    errors = []
    if spec.view == "month":
        if month is None:
            errors.append("plot-template month erwartet --month.")
        elif month not in MONTH_NAMES:
            errors.append(f"Ungueltiger Monat fuer plot-template: {month}")
    elif spec.view == "week":
        if week is None:
            errors.append("plot-template week erwartet --week.")
        elif week < 1 or week > MAX_CALENDAR_WEEK:
            errors.append(f"Die Kalenderwoche muss zwischen 1 und {MAX_CALENDAR_WEEK} liegen.")
    elif spec.view == "day":
        if month is None:
            errors.append("plot-template day erwartet --month.")
        elif month not in MONTH_NAMES:
            errors.append(f"Ungueltiger Monat fuer plot-template: {month}")
        if day is None:
            errors.append("plot-template day erwartet --day.")
        elif month in MONTH_NAMES:
            max_day = MONTH_DAY_COUNTS[MONTH_NAMES.index(month)]
            if day < 1 or day > max_day:
                errors.append(f"Der Tag muss fuer {month} zwischen 1 und {max_day} liegen.")
    return errors


def _resolve_processed_variant_dir(datenbank_dir: str | Path, variant_name: str) -> Path:
    variant_stem = strip_variant_suffix(variant_name)
    variant_dir = Path(datenbank_dir) / normalize_variant_name(variant_stem, "_nutzdaten")
    if not variant_dir.exists():
        raise FileNotFoundError(f"Aufbereitete Variante nicht gefunden: {variant_dir}")
    return variant_dir


def _build_template_plot_dataframe(room_df: pd.DataFrame, metric: str, view: str, month=None, week=None, day=None):
    source_column, value_column = METRIC_VALUE_COLUMNS[metric]
    if view == "year":
        return (
            pd.DataFrame(
                {
                    "time_axis": room_df["time"],
                    "series": "Leistung",
                    value_column: room_df[source_column],
                }
            ),
            None,
        )

    if view == "month":
        time_window = get_time_window("month", month=month)
    elif view == "week":
        time_window = get_time_window("week", week=week)
    elif view == "day":
        time_window = get_time_window("day", month=month, day=day)
    else:
        raise ValueError(f"Nicht unterstuetzte Template-Zeitansicht: {view}")

    filtered = filter_time_window(room_df[["time", source_column]].copy(), time_window)
    if filtered.empty:
        return pd.DataFrame(columns=["time_axis", "series", value_column]), time_window
    return (
        pd.DataFrame(
            {
                "time_axis": filtered["time_window"],
                "series": "Leistung",
                value_column: filtered[source_column],
            }
        ),
        time_window,
    )


def _build_template_title(metric: str, view: str, variant_name: str, room_name: str) -> str:
    metric_label = "Heating" if metric == "heating" else "Cooling"
    return f"{metric_label} {VIEW_TITLES[view]} - {variant_name} / {room_name}"


def _build_template_output_file(output_dir: Path, room_name: str, metric: str, view: str) -> Path:
    return output_dir / f"{sanitize_file_name(room_name)}_{metric}_{view}_template.png"


def build_timeline_template(
    datenbank_dir: str | Path = DATENBANK_DIR,
    output_root: str | Path | None = TEST_OUTPUT_DIR,
    selected_variants: list[str] | tuple[str, ...] | None = None,
    rooms: list[str] | tuple[str, ...] | None = None,
    template: str = "heating-month",
    month: str | None = None,
    week: int | None = None,
    day: int | None = None,
    run_id: str | None = None,
    debug: bool = False,
) -> str | list[str]:
    """Erzeugt ein einzelnes Heating-/Cooling-Zeittemplate fuer eine oder mehrere Varianten."""
    spec = get_plot_template_spec(template)
    if spec is None or spec.name == HEATING_YEAR_TEMPLATE:
        raise ValueError(f"Unbekanntes Timeline-Template: {template}")
    if not selected_variants:
        raise ValueError("plot-template erwartet mindestens eine Variante.")
    if not rooms or len(rooms) != 1:
        raise ValueError("plot-template erwartet genau einen Raum.")

    time_errors = validate_timeline_template_time_selection(template, month=month, week=week, day=day)
    if time_errors:
        raise ValueError("; ".join(time_errors))

    metric_module = METRIC_MODULES[spec.metric]
    source_column, value_column = METRIC_VALUE_COLUMNS[spec.metric]
    room_name = rooms[0]
    output_base = Path(output_root or TEST_OUTPUT_DIR)
    resolved_run_id = get_run_id("plot_template", run_id=run_id)
    output_files = []

    for variant_name in selected_variants:
        processed_variant_dir = _resolve_processed_variant_dir(datenbank_dir, variant_name)
        room_file = get_room_data_file(processed_variant_dir, room_name)
        if not os.path.exists(room_file):
            raise FileNotFoundError(f"Raum-CSV nicht gefunden: {room_file}")

        room_df = metric_module.get_room_hourly_data(room_file, debug=debug)
        if room_df is None or room_df.empty:
            raise ValueError(f"Keine Daten fuer {variant_name} / {room_name} gefunden.")

        plot_df, time_window = _build_template_plot_dataframe(
            room_df,
            spec.metric,
            spec.view,
            month=month,
            week=week,
            day=day,
        )
        if plot_df.empty:
            raise ValueError(f"Keine Daten fuer {variant_name} / {room_name} im gewaehlten Zeitraum gefunden.")

        variant_display_name = get_variant_display_name(processed_variant_dir)
        output_dir = output_base / "PlotTemplates" / resolved_run_id / variant_display_name
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = _build_template_output_file(output_dir, room_name, spec.metric, spec.view)

        if debug:
            print(f"Template: {template}")
            print(f"Template-Variante: {variant_name}")
            print(f"Template-Datenpunkte: {len(plot_df)}")

        metric_module.draw_technical_line_plot(
            plot_df,
            x_col="time_axis",
            group_col="series",
            title=_build_template_title(spec.metric, spec.view, variant_display_name, room_name),
            subtitle=metric_module.build_plot_subtitle(
                spec.view,
                month_name=month,
                week_number=week,
                day_number=day,
            ),
            axis_config=metric_module.build_time_axis_config(spec.view, time_window=time_window),
            output_file=output_file,
        )
        output_files.append(str(output_file))

        if source_column not in room_df.columns or value_column not in plot_df.columns:
            raise ValueError(f"Template-Daten konnten fuer {template} nicht vollstaendig aufgebaut werden.")

    if len(output_files) == 1:
        return output_files[0]
    return output_files
