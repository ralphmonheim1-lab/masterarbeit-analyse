"""Ausfuehrungslogik fuer die ma_analyse-Befehle."""

from __future__ import annotations

import argparse
import os
import shutil
import time
from pathlib import Path

from ..analysis.comfort.main import get_run_id, process_analysis, process_overview, process_plots
from ..analysis.cooling import main as compare_cooling_comparison
from ..analysis.excel import build_excel_report
from ..analysis.heating import main as compare_heating_comparison
from ..analysis.templates import build_plot_template
from ..core.config import DOCS_DIR, OUTPUT_DIR, ROOMS, TEST_OUTPUT_DIR
from ..core.logging import format_duration, timed_step
from ..preprocessing.prepare import process_all_variants

STEP_SEQUENCE = ["prepare", "plots", "overview", "analysis", "analyze", "heating", "cooling", "plot_template"]
DATABASE_STEPS = {"plots", "overview", "analysis", "analyze", "heating", "cooling", "plot_template"}
STEP_TITLES = {
    "prepare": "prepare (Rohdaten aufbereiten)",
    "plots": "plots (Einzelne Raumdiagramme)",
    "overview": "overview (PDF-Uebersicht)",
    "analysis": "analysis (Behaglichkeitsanalyse)",
    "analyze": "analyze_data (Excel-Auswertung)",
    "heating": "heating (Heizvergleich)",
    "cooling": "cooling (Kuehlvergleich)",
    "plot_template": "plot-template (Diagramm-Vorlage)",
}
COMMAND_TO_INTERNAL_STEP = {
    "prepare": "prepare",
    "plots": "plots",
    "overview": "overview",
    "analysis": "analysis",
    "analyze_data": "analyze",
    "analyze-data": "analyze",
    "heating": "heating",
    "cooling": "cooling",
    "plot-template": "plot_template",
}

COMFORT_OUTPUT_TYPES = {
    "plot": {
        "steps": ["plots"],
        "plot_single": True,
        "plot_overview": False,
        "analysis_individual": False,
        "analysis_overview": False,
    },
    "plot_overview": {
        "steps": ["overview"],
        "plot_single": False,
        "plot_overview": True,
        "analysis_individual": False,
        "analysis_overview": False,
    },
    "plot_analysis": {
        "steps": ["plots", "analysis"],
        "plot_single": True,
        "plot_overview": False,
        "analysis_individual": True,
        "analysis_overview": False,
    },
    "plot_analysis_overview": {
        "steps": ["plots", "overview", "analysis"],
        "plot_single": True,
        "plot_overview": True,
        "analysis_individual": True,
        "analysis_overview": True,
    },
}


def get_comfort_output_settings(output_type):
    """Uebersetzt Comfort-Unterbefehle in interne Pipeline-Schritte."""
    if output_type not in COMFORT_OUTPUT_TYPES:
        raise ValueError(f"Ungültiger output_type: {output_type}. Erwartet: {', '.join(COMFORT_OUTPUT_TYPES)}")
    return COMFORT_OUTPUT_TYPES[output_type]


def run_prepare(args):
    """Fuehrt den prepare-Befehl aus und erzeugt Nutzdaten."""
    process_all_variants(
        args.input_dir,
        args.rooms,
        args.datenbank_dir,
        debug=args.debug,
        selected_variants=args.variants,
        export_format=getattr(args, "export_format", "csv"),
    )


def run_plots(args):
    """Fuehrt Comfort-Einzelplots aus."""
    process_plots(
        datenbank_dir=args.datenbank_dir,
        rooms=args.rooms,
        run_id=args.run_id,
        output_root=args.output_root,
        variant_dirs=args.variants,
        debug=args.debug,
        output_subdir=getattr(args, "plot_output_subdir", None),
    )


def run_overview(args):
    """Fuehrt Comfort-PDF-Uebersichten aus."""
    process_overview(
        datenbank_dir=args.datenbank_dir,
        rooms=args.rooms,
        run_id=args.run_id,
        output_root=args.output_root,
        variant_dirs=args.variants,
        debug=args.debug,
    )


def run_analysis(args, run_id=None, output_individual=True, output_overview=True):
    """Fuehrt die Comfort-Zonenanalyse aus und protokolliert die Tabelle."""
    result = process_analysis(
        datenbank_dir=args.datenbank_dir,
        rooms=args.rooms,
        run_id=run_id,
        output_root=args.output_root,
        variant_dirs=args.variants,
        debug=args.debug,
        output_individual=output_individual,
        output_overview=output_overview,
    )
    if result is None:
        print("X Keine Ergebnisse erzeugt")
        raise SystemExit(1)

    print(result.to_string(index=False))


def run_analyze(args):
    """Fuehrt analyze_data aus und mappt GUI-Ausgabearten auf Excel-Modi."""
    layout_mode = getattr(args, "heating_series_layout", None)
    if layout_mode == "separate":
        variant_mode = "single"
    elif layout_mode == "combined":
        variant_mode = "compare"
    else:
        variant_mode = getattr(args, "heating_mode", None)
        if variant_mode is None:
            variant_mode = "compare" if getattr(args, "variant_mode_explicit", False) else "single"

    output_files = build_excel_report(
        args.datenbank_dir,
        output_root=args.output_root,
        debug=args.debug,
        run_id=args.run_id,
        selected_variants=args.variants,
        rooms=args.rooms,
        variant_mode=variant_mode,
    )
    if isinstance(output_files, list):
        for output_file in output_files:
            print(f"Excel-Ausgabe erstellt: {output_file}")
        return
    print(f"Excel-Ausgabe erstellt: {output_files}")


def run_heating(args):
    """Fuehrt den Heating-Vergleich mit den gewaehlten Zeit-/Layoutoptionen aus."""
    compare_heating_comparison(
        args.datenbank_dir,
        debug=args.debug,
        selected_variants=args.variants,
        rooms=args.rooms,
        view=getattr(args, "view", "bar"),
        month=getattr(args, "month", None),
        week=getattr(args, "week", None),
        day=getattr(args, "day", None),
        variant_mode=getattr(args, "heating_mode", None) or "compare",
        series_layout=getattr(args, "heating_series_layout", None) or "separate",
        output_root=getattr(args, "output_root", None),
        run_id=getattr(args, "run_id", None),
    )


def run_cooling(args):
    """Fuehrt den Cooling-Vergleich mit den gewaehlten Zeit-/Layoutoptionen aus."""
    view = getattr(args, "view", "year")
    compare_cooling_comparison(
        args.datenbank_dir,
        debug=args.debug,
        selected_variants=args.variants,
        rooms=args.rooms,
        view=view,
        month=getattr(args, "month", None),
        week=getattr(args, "week", None),
        day=getattr(args, "day", None),
        variant_mode=getattr(args, "heating_mode", None) or "compare",
        series_layout=getattr(args, "heating_series_layout", None) or "separate",
        output_root=getattr(args, "output_root", None),
        run_id=getattr(args, "run_id", None),
    )


def run_plot_template(args):
    """Fuehrt die manuell anpassbare Diagrammvorlage aus."""
    output_root = getattr(args, "output_root", None)
    if not getattr(args, "output_root_explicit", False) and output_root == OUTPUT_DIR:
        output_root = TEST_OUTPUT_DIR

    output_files = build_plot_template(
        datenbank_dir=args.datenbank_dir,
        input_dir=args.input_dir,
        output_root=output_root,
        selected_variants=args.variants,
        rooms=args.rooms,
        template=getattr(args, "template", "heating-year"),
        setpoint_min=getattr(args, "setpoint_min", 21.0),
        setpoint_max=getattr(args, "setpoint_max", 26.0),
        temperature_ymin=getattr(args, "temperature_ymin", -20.0),
        temperature_ymax=getattr(args, "temperature_ymax", 40.0),
        outdoor_column=getattr(args, "outdoor_column", "tair"),
        show_setpoint_band=getattr(args, "show_setpoint_band", True),
        show_outdoor_temperature=getattr(args, "show_outdoor_temperature", True),
        show_operative_temperature=getattr(args, "show_operative_temperature", True),
        overlay_lines=getattr(args, "overlay_lines", None),
        fixed_overlays=getattr(args, "fixed_overlays", None),
        month=getattr(args, "month", None),
        week=getattr(args, "week", None),
        day=getattr(args, "day", None),
        run_id=getattr(args, "run_id", None),
        debug=getattr(args, "debug", False),
    )
    if isinstance(output_files, list):
        print(f"Plot-Templates gespeichert: {len(output_files)} Dateien")
        for output_file in output_files:
            print(f"- {output_file}")
        return

    print(f"Plot-Template gespeichert: {output_files}")


def _get_plot_template_example_specs() -> list[dict[str, object]]:
    """Definiert stabile Beispiele fuer alle Plot-Templates."""
    examples = [
        {
            "template": "heating-year",
            "rooms": ["208 office"],
            "kwargs": {},
            "command": 'python -m ma_analyse plot-template --template heating-year --variants Dimensionierung --rooms "208 office"',
        },
        {
            "template": "heating-month",
            "rooms": ["208 office"],
            "kwargs": {"month": "Jul"},
            "command": 'python -m ma_analyse plot-template --template heating-month --variants Dimensionierung --rooms "208 office" --month Jul',
        },
        {
            "template": "heating-week",
            "rooms": ["208 office"],
            "kwargs": {"week": 29},
            "command": 'python -m ma_analyse plot-template --template heating-week --variants Dimensionierung --rooms "208 office" --week 29',
        },
        {
            "template": "heating-day",
            "rooms": ["208 office"],
            "kwargs": {"month": "Jul", "day": 20},
            "command": 'python -m ma_analyse plot-template --template heating-day --variants Dimensionierung --rooms "208 office" --month Jul --day 20',
        },
        {
            "template": "cooling-year",
            "rooms": ["208 office"],
            "kwargs": {},
            "command": 'python -m ma_analyse plot-template --template cooling-year --variants Dimensionierung --rooms "208 office"',
        },
        {
            "template": "cooling-month",
            "rooms": ["208 office"],
            "kwargs": {"month": "Jul"},
            "command": 'python -m ma_analyse plot-template --template cooling-month --variants Dimensionierung --rooms "208 office" --month Jul',
        },
        {
            "template": "cooling-week",
            "rooms": ["208 office"],
            "kwargs": {"week": 29},
            "command": 'python -m ma_analyse plot-template --template cooling-week --variants Dimensionierung --rooms "208 office" --week 29',
        },
        {
            "template": "cooling-day",
            "rooms": ["208 office"],
            "kwargs": {"month": "Jul", "day": 20},
            "command": 'python -m ma_analyse plot-template --template cooling-day --variants Dimensionierung --rooms "208 office" --month Jul --day 20',
        },
        {
            "template": "heating-bar",
            "rooms": ROOMS.copy(),
            "kwargs": {},
            "command": 'python -m ma_analyse plot-template --template heating-bar --variants Dimensionierung --rooms "{}"'.format(
                ",".join(ROOMS)
            ),
        },
        {
            "template": "cooling-bar",
            "rooms": ROOMS.copy(),
            "kwargs": {},
            "command": 'python -m ma_analyse plot-template --template cooling-bar --variants Dimensionierung --rooms "{}"'.format(
                ",".join(ROOMS)
            ),
        },
        {
            "template": "comfort-plot",
            "rooms": ["208 office"],
            "kwargs": {},
            "command": 'python -m ma_analyse plot-template --template comfort-plot --variants Dimensionierung --rooms "208 office"',
        },
        {
            "template": "comfort-analysis",
            "rooms": ["208 office"],
            "kwargs": {},
            "command": 'python -m ma_analyse plot-template --template comfort-analysis --variants Dimensionierung --rooms "208 office"',
        },
        {
            "template": "comfort-plot-overview",
            "rooms": ROOMS.copy(),
            "kwargs": {},
            "command": 'python -m ma_analyse plot-template --template comfort-plot-overview --variants Dimensionierung --rooms "{}"'.format(
                ",".join(ROOMS)
            ),
        },
        {
            "template": "comfort-analysis-overview",
            "rooms": ROOMS.copy(),
            "kwargs": {},
            "command": 'python -m ma_analyse plot-template --template comfort-analysis-overview --variants Dimensionierung --rooms "{}"'.format(
                ",".join(ROOMS)
            ),
        },
        {
            "template": "internal-loads-year",
            "rooms": ["208 office"],
            "kwargs": {},
            "command": 'python -m ma_analyse plot-template --template internal-loads-year --variants Dimensionierung --rooms "208 office"',
        },
        {
            "template": "internal-loads-month",
            "rooms": ["208 office"],
            "kwargs": {"month": "Jul"},
            "command": 'python -m ma_analyse plot-template --template internal-loads-month --variants Dimensionierung --rooms "208 office" --month Jul',
        },
        {
            "template": "internal-loads-week",
            "rooms": ["208 office"],
            "kwargs": {"week": 29},
            "command": 'python -m ma_analyse plot-template --template internal-loads-week --variants Dimensionierung --rooms "208 office" --week 29',
        },
        {
            "template": "internal-loads-day",
            "rooms": ["208 office"],
            "kwargs": {"month": "Jul", "day": 20},
            "command": 'python -m ma_analyse plot-template --template internal-loads-day --variants Dimensionierung --rooms "208 office" --month Jul --day 20',
        },
        {
            "template": "internal-loads-monthly-sum",
            "rooms": ["208 office"],
            "kwargs": {},
            "command": 'python -m ma_analyse plot-template --template internal-loads-monthly-sum --variants Dimensionierung --rooms "208 office"',
        },
        {
            "template": "internal-loads-room-comparison",
            "rooms": ROOMS.copy(),
            "kwargs": {},
            "command": 'python -m ma_analyse plot-template --template internal-loads-room-comparison --variants Dimensionierung --rooms "{}"'.format(
                ",".join(ROOMS)
            ),
        },
        {
            "template": "energy-balance-year",
            "rooms": ["208 office"],
            "kwargs": {},
            "command": 'python -m ma_analyse plot-template --template energy-balance-year --variants Dimensionierung --rooms "208 office"',
        },
        {
            "template": "energy-balance-month",
            "rooms": ["208 office"],
            "kwargs": {"month": "Jul"},
            "command": 'python -m ma_analyse plot-template --template energy-balance-month --variants Dimensionierung --rooms "208 office" --month Jul',
        },
        {
            "template": "energy-balance-week",
            "rooms": ["208 office"],
            "kwargs": {"week": 29},
            "command": 'python -m ma_analyse plot-template --template energy-balance-week --variants Dimensionierung --rooms "208 office" --week 29',
        },
        {
            "template": "energy-balance-day",
            "rooms": ["208 office"],
            "kwargs": {"month": "Jul", "day": 20},
            "command": 'python -m ma_analyse plot-template --template energy-balance-day --variants Dimensionierung --rooms "208 office" --month Jul --day 20',
        },
        {
            "template": "thermal-room-climate-year",
            "rooms": ["208 office"],
            "kwargs": {},
            "command": 'python -m ma_analyse plot-template --template thermal-room-climate-year --variants Dimensionierung --rooms "208 office"',
        },
        {
            "template": "thermal-room-climate-month",
            "rooms": ["208 office"],
            "kwargs": {"month": "Jul"},
            "command": 'python -m ma_analyse plot-template --template thermal-room-climate-month --variants Dimensionierung --rooms "208 office" --month Jul',
        },
        {
            "template": "thermal-room-climate-week",
            "rooms": ["208 office"],
            "kwargs": {"week": 29},
            "command": 'python -m ma_analyse plot-template --template thermal-room-climate-week --variants Dimensionierung --rooms "208 office" --week 29',
        },
        {
            "template": "thermal-room-climate-day",
            "rooms": ["208 office"],
            "kwargs": {"month": "Jul", "day": 20},
            "command": 'python -m ma_analyse plot-template --template thermal-room-climate-day --variants Dimensionierung --rooms "208 office" --month Jul --day 20',
        },
    ]
    return examples


def _render_gallery_markdown(entries: list[dict[str, object]], output_file: Path) -> None:
    lines = [
        "# Plot-Template Beispiele",
        "",
        "Diese Galerie zeigt stabil erzeugte Beispielbilder und -dokumente fuer alle `plot-template`-Vorlagen.",
        "",
        "Die Bilder liegen unter `docs/examples/plot_templates/`.",
        "",
    ]

    groups = {
        "Heating": [
            "heating-year",
            "heating-month",
            "heating-week",
            "heating-day",
        ],
        "Cooling": [
            "cooling-year",
            "cooling-month",
            "cooling-week",
            "cooling-day",
        ],
        "Barplots": ["heating-bar", "cooling-bar"],
        "Comfort": [
            "comfort-plot",
            "comfort-analysis",
            "comfort-plot-overview",
            "comfort-analysis-overview",
        ],
        "Energy Balance": [
            "energy-balance-year",
            "energy-balance-month",
            "energy-balance-week",
            "energy-balance-day",
        ],
        "Internal Loads": [
            "internal-loads-year",
            "internal-loads-month",
            "internal-loads-week",
            "internal-loads-day",
            "internal-loads-monthly-sum",
            "internal-loads-room-comparison",
        ],
        "Thermal Room Climate": [
            "thermal-room-climate-year",
            "thermal-room-climate-month",
            "thermal-room-climate-week",
            "thermal-room-climate-day",
        ],
    }

    entry_by_template = {entry["template"]: entry for entry in entries}

    for heading, templates in groups.items():
        lines.append(f"## {heading}")
        lines.append("")
        for template in templates:
            entry = entry_by_template[template]
            target_file = entry["target_file"].name
            lines.append(f"### `{template}`")
            lines.append("")
            lines.append(f"**Beispielbefehl:** `{entry['command']}`")
            lines.append("")
            if target_file.lower().endswith(".pdf"):
                lines.append(f"[PDF-Ausgabe](examples/plot_templates/{target_file})")
            else:
                lines.append(f"![{template}](examples/plot_templates/{target_file})")
            lines.append("")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "Diese Beispiele werden reproduzierbar mit dem Befehl `python -m ma_analyse plot-template-examples` erzeugt.",
            "Wenn sich das Aussehen von Plot-Templates aendert, ersetzen neue Generierungsläufe die vorhandenen Dateien.",
            "",
        ]
    )

    output_file.write_text("\n".join(lines), encoding="utf-8")


def _copy_gallery_file(source: str | Path, target_dir: Path, template: str) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    source_path = Path(source)
    target_path = target_dir / f"{template}{source_path.suffix}"
    shutil.copy2(source_path, target_path)
    return target_path


def run_plot_template_examples(args):
    """Erzeugt die Dokumentationsgalerie fuer alle Plot-Template-Beispiele."""
    gallery_dir = DOCS_DIR / "examples" / "plot_templates"
    gallery_dir.mkdir(parents=True, exist_ok=True)
    for existing_file in gallery_dir.iterdir():
        if existing_file.is_file():
            existing_file.unlink()

    generated_root = Path(TEST_OUTPUT_DIR) / "plot_template_examples"
    generated_root.mkdir(parents=True, exist_ok=True)

    example_specs = _get_plot_template_example_specs()
    output_entries = []
    for example in example_specs:
        output = build_plot_template(
            datenbank_dir=args.datenbank_dir,
            input_dir=args.input_dir,
            output_root=generated_root,
            selected_variants=["Dimensionierung"],
            rooms=example["rooms"],
            template=example["template"],
            run_id="plot_template_examples",
            month=example["kwargs"].get("month"),
            week=example["kwargs"].get("week"),
            day=example["kwargs"].get("day"),
            debug=args.debug,
        )
        if isinstance(output, list):
            output = output[0]
        target = _copy_gallery_file(output, gallery_dir, example["template"])
        output_entries.append({**example, "target_file": target})

    markdown_file = DOCS_DIR / "plot_template_examples.md"
    _render_gallery_markdown(output_entries, markdown_file)
    print(f"Beispielgalerie erzeugt: {markdown_file}")
    print(f"Bilder erzeugt: {len(output_entries)} Dateien")


def run_comfort(args):
    """Fuehrt den Comfort-Unterbefehl ueber die gemeinsame Pipeline aus."""
    output_type = getattr(args, "output_type", "plot_analysis_overview")
    settings = get_comfort_output_settings(output_type)
    execute_steps(
        args,
        steps=settings["steps"],
        variants=args.variants,
        rooms=args.rooms,
        comfort_options=settings,
    )


def ensure_required_data(args, steps):
    """Bricht Analyse-/Plotbefehle ab, wenn vorherige Nutzdaten fehlen."""
    if not any(step in DATABASE_STEPS for step in steps):
        return

    if os.path.exists(args.datenbank_dir):
        return

    if "prepare" in steps:
        return

    print(f"X Verzeichnis mit aufbereiteten Daten nicht gefunden: {args.datenbank_dir}")
    print("  Fuehren Sie zuerst 'prepare' aus oder waehlen Sie in der GUI auch prepare.")
    raise SystemExit(1)


def build_runtime_args(
    args,
    variants=None,
    rooms=None,
    heating_mode=None,
    prepare_options=None,
    comfort_options=None,
    heating_options=None,
    plot_template_options=None,
    plot_output_subdir=None,
):
    """Baut ein einheitliches Argumentobjekt fuer interne Pipeline-Schritte."""
    comfort_defaults = {
        "plot_single": True,
        "plot_overview": True,
        "analysis_individual": True,
        "analysis_overview": True,
    }
    if comfort_options:
        comfort_defaults.update(comfort_options)

    heating_defaults = {
        "view": getattr(args, "view", "bar"),
        "month": getattr(args, "month", None),
        "week": getattr(args, "week", None),
        "day": getattr(args, "day", None),
        "series_layout": getattr(args, "heating_series_layout", None) or "separate",
    }
    if heating_options:
        heating_defaults.update(heating_options)

    prepare_defaults = {
        "export_format": getattr(args, "export_format", "csv"),
    }
    if prepare_options:
        prepare_defaults.update(prepare_options)

    plot_template_defaults = {
        "template": getattr(args, "template", "heating-year"),
        "setpoint_min": getattr(args, "setpoint_min", 21.0),
        "setpoint_max": getattr(args, "setpoint_max", 26.0),
        "temperature_ymin": getattr(args, "temperature_ymin", -20.0),
        "temperature_ymax": getattr(args, "temperature_ymax", 40.0),
        "outdoor_column": getattr(args, "outdoor_column", "tair"),
        "show_setpoint_band": getattr(args, "show_setpoint_band", True),
        "show_outdoor_temperature": getattr(args, "show_outdoor_temperature", True),
        "show_operative_temperature": getattr(args, "show_operative_temperature", True),
        "overlay_lines": getattr(args, "overlay_lines", None),
        "fixed_overlays": getattr(args, "fixed_overlays", None),
        "month": getattr(args, "month", None),
        "week": getattr(args, "week", None),
        "day": getattr(args, "day", None),
    }
    if plot_template_options:
        plot_template_defaults.update(plot_template_options)

    return argparse.Namespace(
        input_dir=args.input_dir,
        datenbank_dir=args.datenbank_dir,
        output_root=args.output_root,
        output_root_explicit=getattr(args, "output_root_explicit", False),
        run_id=args.run_id,
        debug=args.debug,
        variants=variants,
        rooms=rooms if rooms is not None else ROOMS.copy(),
        view=heating_defaults["view"],
        month=plot_template_defaults["month"] if plot_template_options else heating_defaults["month"],
        week=plot_template_defaults["week"] if plot_template_options else heating_defaults["week"],
        day=plot_template_defaults["day"] if plot_template_options else heating_defaults["day"],
        heating_series_layout=heating_defaults["series_layout"],
        heating_mode=heating_mode or getattr(args, "heating_mode", None) or "compare",
        plot_single=comfort_defaults["plot_single"],
        plot_overview=comfort_defaults["plot_overview"],
        analysis_individual=comfort_defaults["analysis_individual"],
        analysis_overview=comfort_defaults["analysis_overview"],
        plot_output_subdir=plot_output_subdir,
        export_format=prepare_defaults["export_format"],
        template=plot_template_defaults["template"],
        setpoint_min=plot_template_defaults["setpoint_min"],
        setpoint_max=plot_template_defaults["setpoint_max"],
        temperature_ymin=plot_template_defaults["temperature_ymin"],
        temperature_ymax=plot_template_defaults["temperature_ymax"],
        outdoor_column=plot_template_defaults["outdoor_column"],
        show_setpoint_band=plot_template_defaults["show_setpoint_band"],
        show_outdoor_temperature=plot_template_defaults["show_outdoor_temperature"],
        show_operative_temperature=plot_template_defaults["show_operative_temperature"],
        overlay_lines=plot_template_defaults["overlay_lines"],
        fixed_overlays=plot_template_defaults["fixed_overlays"],
    )


def execute_steps(
    args,
    steps,
    variants=None,
    rooms=None,
    heating_mode=None,
    prepare_options=None,
    comfort_options=None,
    heating_options=None,
    plot_template_options=None,
    plot_output_subdir=None,
):
    """Fuehrt eine geordnete Teilmenge der Pipeline-Schritte aus."""
    selected_steps = [step for step in STEP_SEQUENCE if step in steps]
    ensure_required_data(args, selected_steps)

    runtime_args = build_runtime_args(
        args,
        variants=variants,
        rooms=rooms,
        heating_mode=heating_mode,
        prepare_options=prepare_options,
        comfort_options=comfort_options,
        heating_options=heating_options,
        plot_template_options=plot_template_options,
        plot_output_subdir=plot_output_subdir,
    )

    print("\n" + "=" * 70)
    print("PIPELINE GESTARTET")
    print("=" * 70)

    pipeline_start = time.perf_counter()
    total_steps = len(selected_steps)
    for index, step in enumerate(selected_steps, start=1):
        if step == "plots" and not runtime_args.plot_single:
            continue
        if step == "overview" and not runtime_args.plot_overview:
            continue

        step_title = STEP_TITLES[step]
        print(f"\nSchritt {index}/{total_steps}: {step_title}")
        print("-" * 70)

        with timed_step(step_title):
            if step == "prepare":
                run_prepare(runtime_args)
                continue

            if step == "plots":
                run_plots(runtime_args)
                continue

            if step == "overview":
                run_overview(runtime_args)
                continue

            if step == "analysis":
                run_analysis(
                    runtime_args,
                    run_id=runtime_args.run_id,
                    output_individual=runtime_args.analysis_individual,
                    output_overview=runtime_args.analysis_overview,
                )
                continue

            if step == "analyze":
                run_analyze(runtime_args)
                continue

            if step == "heating":
                run_heating(runtime_args)
                continue

            if step == "cooling":
                run_cooling(runtime_args)
                continue

            if step == "plot_template":
                run_plot_template(runtime_args)
                continue

    print("\n" + "=" * 70)
    print(f"Gesamtlaufzeit Pipeline: {format_duration(time.perf_counter() - pipeline_start)}")
    print("PIPELINE ABGESCHLOSSEN")
    print("=" * 70)


def run_all(args):
    """Fuehrt das feste Ausgabeprofil fuer den Sammelbefehl ``all`` aus."""
    shared_run_id = get_run_id(command_name="all", run_id=args.run_id)
    args.run_id = shared_run_id

    steps = ["overview", "analysis", "heating", "cooling"]
    ensure_required_data(args, steps)

    variants = args.variants
    rooms = args.rooms if args.rooms is not None else ROOMS.copy()
    comfort_options = {
        "plot_single": False,
        "plot_overview": True,
        "analysis_individual": False,
        "analysis_overview": True,
    }
    year_separate_options = {
        "view": "year",
        "month": None,
        "week": None,
        "day": None,
        "series_layout": "separate",
    }
    bar_options = {
        "view": "bar",
        "month": None,
        "week": None,
        "day": None,
        "series_layout": "separate",
    }

    comfort_runtime_args = build_runtime_args(
        args,
        variants=variants,
        rooms=rooms,
        comfort_options=comfort_options,
    )
    load_single_args = build_runtime_args(
        args,
        variants=variants,
        rooms=rooms,
        heating_mode="single",
        heating_options=year_separate_options,
    )
    load_compare_args = build_runtime_args(
        args,
        variants=variants,
        rooms=rooms,
        heating_mode="compare",
        heating_options=year_separate_options,
    )
    load_bar_args = build_runtime_args(
        args,
        variants=variants,
        rooms=rooms,
        heating_mode="compare",
        heating_options=bar_options,
    )

    all_steps = [
        ("Comfort-Uebersicht", lambda: run_overview(comfort_runtime_args)),
        (
            "Analyse-Uebersicht",
            lambda: run_analysis(
                comfort_runtime_args,
                run_id=comfort_runtime_args.run_id,
                output_individual=False,
                output_overview=True,
            ),
        ),
        ("Heating Barplots", lambda: run_heating(load_bar_args)),
        ("Cooling Barplots", lambda: run_cooling(load_bar_args)),
        ("Heating Jahresplots single", lambda: run_heating(load_single_args)),
        ("Heating Jahresplots Raeume kombiniert", lambda: run_heating(load_compare_args)),
        ("Cooling Jahresplots single", lambda: run_cooling(load_single_args)),
        ("Cooling Jahresplots Raeume kombiniert", lambda: run_cooling(load_compare_args)),
    ]

    print("\n" + "=" * 70)
    print("ALL-PROFIL GESTARTET")
    print("=" * 70)
    print(f"Run-ID: {shared_run_id}")

    profile_start = time.perf_counter()
    total_steps = len(all_steps)
    for index, (title, runner) in enumerate(all_steps, start=1):
        print(f"\nSchritt {index}/{total_steps}: {title}")
        print("-" * 70)
        with timed_step(title):
            runner()

    print("\n" + "=" * 70)
    print(f"Gesamtlaufzeit all: {format_duration(time.perf_counter() - profile_start)}")
    print("ALL-PROFIL ABGESCHLOSSEN")
    print("=" * 70)


def dispatch_command(args):
    """Fuehrt den bereits geparsten CLI-Befehl aus."""
    if args.command == "prepare":
        with timed_step(STEP_TITLES["prepare"]):
            ensure_required_data(args, ["prepare"])
            run_prepare(args)
        return

    if args.command == "comfort":
        comfort_steps = get_comfort_output_settings(args.output_type)["steps"]
        ensure_required_data(args, comfort_steps)
        run_comfort(args)
        return

    if args.command in {"analyze-data", "analyze_data"}:
        with timed_step(STEP_TITLES["analyze"]):
            ensure_required_data(args, ["analyze"])
            run_analyze(args)
        return

    if args.command == "heating":
        with timed_step(STEP_TITLES["heating"]):
            ensure_required_data(args, ["heating"])
            run_heating(args)
        return

    if args.command == "cooling":
        with timed_step(STEP_TITLES["cooling"]):
            ensure_required_data(args, ["cooling"])
            run_cooling(args)
        return

    if args.command == "plot-template":
        with timed_step(STEP_TITLES["plot_template"]):
            ensure_required_data(args, ["plot_template"])
            run_plot_template(args)
        return

    if args.command == "plot-template-examples":
        with timed_step("plot-template-examples (Beispielgalerie erzeugen)"):
            run_plot_template_examples(args)
        return

    if args.command == "gui":
        from ..gui.app import run_gui

        run_gui(args)
        return

    if args.command == "all":
        run_all(args)
