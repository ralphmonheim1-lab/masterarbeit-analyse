"""Plot-Templates fuer Comfort-PNGs und Comfort-PDF-Uebersichten."""

from __future__ import annotations

import os
from pathlib import Path

from ...core.config import DATENBANK_DIR, TEST_OUTPUT_DIR
from ..comfort.analysis_plots import create_analysis_overview_pdf, create_zone_plot
from ..comfort.data import load_room_csv
from ..comfort.plots import create_overview_pdf, create_room_plot
from ..comfort.zones import COMFORT_NORMAL, build_zone_masks, count_points_in_zone
from ..components.rooms import get_room_data_file
from ..components.runtime import get_run_id, sanitize_file_name
from ..components.variants import get_variant_display_name, normalize_variant_name, strip_variant_suffix
from .catalog import (
    COMFORT_ANALYSIS_OVERVIEW_TEMPLATE,
    COMFORT_ANALYSIS_TEMPLATE,
    COMFORT_PLOT_OVERVIEW_TEMPLATE,
    COMFORT_PLOT_TEMPLATE,
    get_plot_template_spec,
    template_requires_single_room,
)


def _resolve_processed_variant_dir(datenbank_dir: str | Path, variant_name: str) -> Path:
    variant_stem = strip_variant_suffix(variant_name)
    variant_dir = Path(datenbank_dir) / normalize_variant_name(variant_stem, "_nutzdaten")
    if not variant_dir.exists():
        raise FileNotFoundError(f"Aufbereitete Variante nicht gefunden: {variant_dir}")
    return variant_dir


def validate_comfort_template_request(
    template: str,
    variants: list[str] | tuple[str, ...] | None,
    rooms: list[str] | tuple[str, ...] | None,
) -> list[str]:
    """Prueft Mindestangaben fuer Comfort-Templates."""
    errors = []
    spec = get_plot_template_spec(template)
    if spec is None or spec.metric != "comfort":
        errors.append(f"Unbekanntes Comfort-Template: {template}")
        return errors
    if not variants:
        errors.append("plot-template erwartet mindestens eine Variante.")
    if not rooms:
        errors.append("plot-template erwartet mindestens einen Raum.")
    elif template_requires_single_room(template) and len(rooms) != 1:
        errors.append("Dieses plot-template erwartet genau einen Raum.")
    return errors


def _load_comfort_room_data(processed_variant_dir: Path, room_name: str, debug: bool = False):
    room_file = get_room_data_file(processed_variant_dir, room_name)
    if not os.path.exists(room_file):
        raise FileNotFoundError(f"Raum-CSV nicht gefunden: {room_file}")
    room_data = load_room_csv(room_file, debug=debug)
    if room_data is None or room_data.empty:
        raise ValueError(f"Keine Comfort-Daten fuer {room_name} gefunden.")
    return room_data


def _build_output_file(output_dir: Path, template: str, room_name: str | None = None) -> Path:
    if template == COMFORT_PLOT_TEMPLATE:
        return output_dir / f"{sanitize_file_name(room_name)}_comfort_plot_template.png"
    if template == COMFORT_ANALYSIS_TEMPLATE:
        return output_dir / f"{sanitize_file_name(room_name)}_comfort_analysis_template.png"
    if template == COMFORT_PLOT_OVERVIEW_TEMPLATE:
        return output_dir / "comfort_plot_overview_template.pdf"
    if template == COMFORT_ANALYSIS_OVERVIEW_TEMPLATE:
        return output_dir / "comfort_analysis_overview_template.pdf"
    raise ValueError(f"Unbekanntes Comfort-Template: {template}")


def _draw_comfort_analysis_template(room_data, room_name: str, output_file: str | Path, debug: bool = False) -> None:
    comfort_high_mask, _, outside_mask = build_zone_masks(room_data)
    comfort_high_count = int(comfort_high_mask.sum())
    comfort_normal_count = count_points_in_zone(room_data, COMFORT_NORMAL)
    outside_count = int(outside_mask.sum())
    create_zone_plot(
        room_data,
        room_name,
        output_file,
        comfort_high_count,
        comfort_normal_count,
        outside_count,
        debug=debug,
    )


def build_comfort_template(
    datenbank_dir: str | Path = DATENBANK_DIR,
    output_root: str | Path | None = TEST_OUTPUT_DIR,
    selected_variants: list[str] | tuple[str, ...] | None = None,
    rooms: list[str] | tuple[str, ...] | None = None,
    template: str = COMFORT_PLOT_TEMPLATE,
    run_id: str | None = None,
    debug: bool = False,
) -> str | list[str]:
    """Erzeugt Comfort-Plot-Templates fuer eine oder mehrere Varianten."""
    errors = validate_comfort_template_request(template, selected_variants, rooms)
    if errors:
        raise ValueError("; ".join(errors))

    output_base = Path(output_root or TEST_OUTPUT_DIR)
    resolved_run_id = get_run_id("plot_template", run_id=run_id)
    output_files = []

    for variant_name in selected_variants:
        processed_variant_dir = _resolve_processed_variant_dir(datenbank_dir, variant_name)
        variant_display_name = get_variant_display_name(processed_variant_dir)
        output_dir = output_base / "PlotTemplates" / resolved_run_id / variant_display_name
        output_dir.mkdir(parents=True, exist_ok=True)

        if template == COMFORT_PLOT_TEMPLATE:
            room_name = rooms[0]
            room_data = _load_comfort_room_data(processed_variant_dir, room_name, debug=debug)
            output_file = _build_output_file(output_dir, template, room_name)
            create_room_plot(room_data, room_name, output_file, debug=debug)
        elif template == COMFORT_ANALYSIS_TEMPLATE:
            room_name = rooms[0]
            room_data = _load_comfort_room_data(processed_variant_dir, room_name, debug=debug)
            output_file = _build_output_file(output_dir, template, room_name)
            _draw_comfort_analysis_template(room_data, room_name, output_file, debug=debug)
        elif template == COMFORT_PLOT_OVERVIEW_TEMPLATE:
            output_file = _build_output_file(output_dir, template)
            create_overview_pdf(processed_variant_dir, rooms, output_file, debug=debug)
        elif template == COMFORT_ANALYSIS_OVERVIEW_TEMPLATE:
            output_file = _build_output_file(output_dir, template)
            create_analysis_overview_pdf(processed_variant_dir, rooms, output_file, debug=debug)
        else:
            raise ValueError(f"Unbekanntes Comfort-Template: {template}")

        if debug:
            print(f"Template: {template}")
            print(f"Template-Variante: {variant_display_name}")
            print(f"Template-Ausgabe: {output_file}")
        output_files.append(str(output_file))

    if len(output_files) == 1:
        return output_files[0]
    return output_files
