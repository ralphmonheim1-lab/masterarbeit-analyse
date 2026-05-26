"""Oeffentliche CLI fuer das Paket ``ma_analyse``."""

from __future__ import annotations

import argparse
import sys

from ..analysis.components.time_windows import MONTH_NAMES
from ..analysis.templates import (
    DEFAULT_OUTDOOR_COLUMN,
    DEFAULT_SETPOINT_MAX,
    DEFAULT_SETPOINT_MIN,
    DEFAULT_SHOW_OPERATIVE_TEMPERATURE,
    DEFAULT_SHOW_OUTDOOR_TEMPERATURE,
    DEFAULT_SHOW_SETPOINT_BAND,
    DEFAULT_TEMPERATURE_YMAX,
    DEFAULT_TEMPERATURE_YMIN,
    HEATING_YEAR_TEMPLATE,
    PLOT_TEMPLATE_CHOICES,
)
from ..core.config import DATENBANK_DIR, EXPORT_FORMATS, INPUT_DIR, OUTPUT_DIR, ROOMS, TEST_OUTPUT_DIR
from ..core.logging import command_log, should_log_command
from ..settings.plot_templates import get_heating_year_template_defaults
from .commands import dispatch_command, get_comfort_output_settings


def parse_comma_separated_list(value):
    """Wandelt eine kommaseparierte CLI-Eingabe in eine Liste um."""
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def has_cli_option(argv, *option_names):
    """Prueft, ob eine Option explizit in der CLI-Eingabe vorkam."""
    for item in argv:
        if item in option_names:
            return True
        if any(item.startswith(f"{option_name}=") for option_name in option_names):
            return True
    return False


def normalize_rooms(selected_rooms):
    """Normalisiert eine optionale Raumauswahl auf die Standardraumliste."""
    if selected_rooms is None:
        return ROOMS.copy()

    normalized = [room for room in ROOMS if room in selected_rooms]
    if normalized:
        return normalized

    print(f"X Ungueltige Raeume: {selected_rooms}")
    print(f"  Verfuegbare Raeume: {ROOMS}")
    raise SystemExit(1)


def add_plot_template_arguments(parser, hide_help=False, config_path=None):
    """Ergaenzt Argumente fuer den Plot-Template-Befehl."""
    help_value = argparse.SUPPRESS if hide_help else None
    template_defaults = (
        get_heating_year_template_defaults(config_path)
        if config_path is not None
        else get_heating_year_template_defaults()
    )
    parser.set_defaults(fixed_overlays=template_defaults.get("default_overlays"))
    parser.add_argument(
        "--template",
        choices=PLOT_TEMPLATE_CHOICES,
        default=HEATING_YEAR_TEMPLATE,
        help=help_value or "Diagrammvorlage fuer Plot-Template-Ausgaben",
    )
    parser.add_argument(
        "--setpoint-min",
        type=float,
        default=template_defaults.get("setpoint_min", DEFAULT_SETPOINT_MIN),
        help=help_value or "Untere Grenze des Sollwertbands in Grad Celsius",
    )
    parser.add_argument(
        "--setpoint-max",
        type=float,
        default=template_defaults.get("setpoint_max", DEFAULT_SETPOINT_MAX),
        help=help_value or "Obere Grenze des Sollwertbands in Grad Celsius",
    )
    parser.add_argument(
        "--temperature-ymin",
        type=float,
        default=template_defaults.get("temperature_ymin", DEFAULT_TEMPERATURE_YMIN),
        help=help_value or "Untere Grenze der Temperaturachse",
    )
    parser.add_argument(
        "--temperature-ymax",
        type=float,
        default=template_defaults.get("temperature_ymax", DEFAULT_TEMPERATURE_YMAX),
        help=help_value or "Obere Grenze der Temperaturachse",
    )
    parser.add_argument(
        "--outdoor-column",
        default=template_defaults.get("outdoor_column", DEFAULT_OUTDOOR_COLUMN),
        help=help_value or "Spalte aus REPORT-AUX.prn fuer die Aussenlufttemperatur",
    )
    parser.add_argument(
        "--no-setpoint-band",
        dest="show_setpoint_band",
        action="store_false",
        default=template_defaults.get("show_setpoint_band", DEFAULT_SHOW_SETPOINT_BAND),
        help=help_value or "Sollwertband im Plot-Template ausblenden",
    )
    parser.add_argument(
        "--no-outdoor-temperature",
        dest="show_outdoor_temperature",
        action="store_false",
        default=template_defaults.get("show_outdoor_temperature", DEFAULT_SHOW_OUTDOOR_TEMPERATURE),
        help=help_value or "Aussenlufttemperatur im Plot-Template ausblenden",
    )
    parser.add_argument(
        "--no-operative-temperature",
        dest="show_operative_temperature",
        action="store_false",
        default=template_defaults.get("show_operative_temperature", DEFAULT_SHOW_OPERATIVE_TEMPERATURE),
        help=help_value or "Operative Temperatur im Plot-Template ausblenden",
    )


def build_parser(plot_template_config_path=None):
    """Definiert die zentrale CLI mit allen Befehlen und gemeinsamen Optionen."""
    parser = argparse.ArgumentParser(
        description="Zentraler Einstiegspunkt fuer Datenaufbereitung, Auswertung und GUI der Pipeline."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--input-dir",
        default=INPUT_DIR,
        help="Wurzelverzeichnis mit Variantenordnern, optional mit Suffix *_rohdaten",
    )
    common.add_argument(
        "--datenbank-dir",
        default=DATENBANK_DIR,
        help="Verzeichnis mit aufbereiteten Daten vom Typ *_nutzdaten",
    )
    common.add_argument(
        "--output-root",
        default=OUTPUT_DIR,
        help="Wurzelverzeichnis fuer erzeugte Ausgaben",
    )
    common.add_argument(
        "--run-id",
        default=None,
        help="Optionale Lauf-ID fuer Plot- und Analyseausgaben",
    )
    common.add_argument(
        "--variants",
        type=parse_comma_separated_list,
        default=None,
        help="Komma-getrennte Variantenliste ohne Suffix",
    )
    common.add_argument(
        "--rooms",
        type=parse_comma_separated_list,
        default=None,
        help="Komma-getrennte Raumliste",
    )
    common.add_argument(
        "--view",
        choices=["bar", "year", "month", "week", "day"],
        default="bar",
        help="Darstellungsmodus fuer heating/cooling: bar, year, month, week oder day",
    )
    common.add_argument(
        "--month",
        choices=MONTH_NAMES,
        default=None,
        help="Monatsfilter fuer heating/cooling bei view=month",
    )
    common.add_argument(
        "--week",
        type=int,
        default=None,
        help="Kalenderwoche fuer heating/cooling bei view=week",
    )
    common.add_argument(
        "--day",
        type=int,
        default=None,
        help="Tag im gewaelten Monat fuer heating/cooling bei view=day",
    )
    common.add_argument(
        "--heating-mode",
        "--variant-mode",
        choices=["single", "compare"],
        default=None,
        dest="heating_mode",
        help="Ausgabe fuer heating/cooling/analyze_data: single erzeugt getrennte Ausgaben, compare fasst Ausgaben zusammen",
    )
    common.add_argument(
        "--heating-series-layout",
        "--series-layout",
        choices=["separate", "combined"],
        default=None,
        dest="heating_series_layout",
        help="Ausgabe fuer heating/cooling/analyze_data: separate oder combined; Standard ist separate",
    )
    common.add_argument(
        "--gui-refresh-port",
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )
    common.add_argument(
        "--gui-window-x",
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )
    common.add_argument(
        "--gui-window-y",
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )
    common.add_argument(
        "--gui-window-width",
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )
    common.add_argument(
        "--gui-window-height",
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )
    common.add_argument(
        "--gui-window-maximized",
        type=int,
        choices=[0, 1],
        default=0,
        help=argparse.SUPPRESS,
    )
    common.add_argument("--debug", dest="debug", action="store_true", help="Aktiviert Debug-Ausgaben")
    common.add_argument("--no-debug", dest="debug", action="store_false", help="Deaktiviert Debug-Ausgaben")

    prepare_parser = subparsers.add_parser(
        "prepare",
        parents=[common],
        help="Bereitet Rohdaten zu Raum-CSV-, Raum-XLSX- oder kombinierten Ausgaben auf",
    )
    prepare_parser.add_argument(
        "--export-format",
        choices=EXPORT_FORMATS,
        default="csv",
        help="Exportformat fuer prepare: csv, excel oder both",
    )
    prepare_parser.set_defaults(debug=True)

    comfort_parser = subparsers.add_parser(
        "comfort",
        parents=[common],
        help="Erstellt Komfortausgaben: plot, overview, analysis oder Kombinationen",
    )
    comfort_parser.add_argument(
        "--output-type",
        choices=["plot", "plot_overview", "plot_analysis", "plot_analysis_overview"],
        default="plot_analysis_overview",
        help="Wählt das Komfort-Ausgabeprofil aus",
    )
    comfort_parser.set_defaults(debug=True)

    analyze_parser = subparsers.add_parser(
        "analyze-data",
        aliases=["analyze_data"],
        parents=[common],
        help="Erstellt die Excel-Auswertung",
    )
    analyze_parser.set_defaults(debug=True)

    heating_parser = subparsers.add_parser(
        "heating",
        parents=[common],
        help="Erstellt Heizleistungsvergleichsdiagramme",
    )
    heating_parser.set_defaults(debug=True)

    cooling_parser = subparsers.add_parser(
        "cooling",
        parents=[common],
        help="Erstellt Kuehlleistungsvergleichsdiagramme",
    )
    cooling_parser.set_defaults(debug=True)

    plot_template_parser = subparsers.add_parser(
        "plot-template",
        parents=[common],
        help="Erstellt manuell anpassbare Diagramm-Vorlagen",
    )
    add_plot_template_arguments(plot_template_parser, config_path=plot_template_config_path)
    plot_template_parser.set_defaults(debug=True, output_root=TEST_OUTPUT_DIR)

    plot_template_examples_parser = subparsers.add_parser(
        "plot-template-examples",
        parents=[common],
        help="Erzeugt die stabile Beispielgalerie fuer alle Plot-Template-Ausgaben",
    )
    plot_template_examples_parser.set_defaults(debug=True)

    gui_parser = subparsers.add_parser(
        "gui",
        parents=[common],
        help="Startet die grafische Pipeline-Oberflaeche",
    )
    gui_parser.add_argument(
        "--export-format",
        choices=EXPORT_FORMATS,
        default="csv",
        help="Startwert fuer das Prepare-Exportformat in der GUI",
    )
    add_plot_template_arguments(gui_parser, hide_help=True, config_path=plot_template_config_path)
    gui_parser.set_defaults(debug=True)

    all_parser = subparsers.add_parser(
        "all",
        parents=[common],
        help="Erzeugt Comfort-/Analyseuebersichten sowie Heating-/Cooling-Barplots und Jahresplots",
    )
    all_parser.set_defaults(debug=True)

    return parser


def main():
    """Parst CLI-Argumente und verzweigt zum gewaehlten Befehl."""
    parser = build_parser()
    args = parser.parse_args()
    raw_argv = sys.argv[1:]
    args.variant_mode_explicit = has_cli_option(raw_argv, "--heating-mode", "--variant-mode")
    args.series_layout_explicit = has_cli_option(raw_argv, "--heating-series-layout", "--series-layout")
    args.output_root_explicit = has_cli_option(raw_argv, "--output-root")

    args.rooms = normalize_rooms(args.rooms)

    if should_log_command(args.command):
        with command_log(args.command) as log_file:
            print(f"Logdatei: {log_file}")
            dispatch_command(args)
        print(f"Log gespeichert: {log_file}")
        return

    dispatch_command(args)


__all__ = [
    "build_parser",
    "add_plot_template_arguments",
    "get_comfort_output_settings",
    "has_cli_option",
    "main",
    "normalize_rooms",
    "parse_comma_separated_list",
]
