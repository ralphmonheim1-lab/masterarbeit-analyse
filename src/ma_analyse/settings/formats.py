"""Zentrale Ausgabeformat-Einstellungen fuer Diagramme, PDFs und Excel."""

from __future__ import annotations

from pathlib import Path

from ..core.config import OUTPUT_FORMATS_DOC

FORMAT_DOC = OUTPUT_FORMATS_DOC

FORMAT_CATALOG = {
    "16x9 cm": {"width_cm": 16.0, "height_cm": 9.0, "description": "Standard fuer Einzel-Diagramme"},
    "24x13.5 cm": {"width_cm": 24.0, "height_cm": 13.5, "description": "Mehr Platz fuer Vergleichsdiagramme"},
    "A4 Hoch": {"width_cm": 21.0, "height_cm": 29.7, "description": "PDF-Seite im Hochformat"},
    "A4 Quer": {"width_cm": 29.7, "height_cm": 21.0, "description": "PDF-Seite im Querformat"},
    "12.8x7.2 cm": {"width_cm": 12.8, "height_cm": 7.2, "description": "Kompaktes 16:9-Format für Plot-Templates"},
    "11.6x6.6 cm": {"width_cm": 11.6, "height_cm": 6.6, "description": "Kompakter Balkendiagramm-Output"},
    "11.8x6.6 cm": {"width_cm": 11.8, "height_cm": 6.6, "description": "Kompakter Raumvergleichs-Output"},
    "Keine Größe": {"width_cm": None, "height_cm": None, "description": "Fuer Ausgaben ohne feste Bildgroesse"},
}

DEFAULT_OUTPUT_RULES = [
    {
        "id": "comfort.plot.png",
        "command": "comfort",
        "subcommand": "plot",
        "output": "Einzelraum-Komfortdiagramm",
        "format": "16x9 cm",
    },
    {
        "id": "comfort.plot_analysis.png",
        "command": "comfort",
        "subcommand": "plot_analysis",
        "output": "Einzelraum-Analyse-Diagramm",
        "format": "16x9 cm",
    },
    {
        "id": "comfort.plot_overview.pdf",
        "command": "comfort",
        "subcommand": "plot_overview",
        "output": "Comfort-Uebersicht PDF",
        "format": "A4 Quer",
    },
    {
        "id": "comfort.plot_analysis_overview.pdf",
        "command": "comfort",
        "subcommand": "plot_analysis_overview",
        "output": "Analyse-Uebersicht PDF",
        "format": "A4 Quer",
    },
    {
        "id": "heating.bar.png",
        "command": "heating",
        "subcommand": "bar",
        "output": "Heating Balkendiagramm",
        "format": "16x9 cm",
    },
    {
        "id": "heating.timeline.single.png",
        "command": "heating",
        "subcommand": "timeline",
        "output": "Heating Zeitdiagramm single",
        "format": "16x9 cm",
    },
    {
        "id": "heating.timeline.compare.png",
        "command": "heating",
        "subcommand": "timeline",
        "output": "Heating Zeitdiagramm compare",
        "format": "24x13.5 cm",
    },
    {
        "id": "cooling.bar.png",
        "command": "cooling",
        "subcommand": "bar",
        "output": "Cooling Balkendiagramm",
        "format": "16x9 cm",
    },
    {
        "id": "cooling.timeline.single.png",
        "command": "cooling",
        "subcommand": "timeline",
        "output": "Cooling Zeitdiagramm single",
        "format": "16x9 cm",
    },
    {
        "id": "cooling.timeline.compare.png",
        "command": "cooling",
        "subcommand": "timeline",
        "output": "Cooling Zeitdiagramm compare",
        "format": "24x13.5 cm",
    },
    {
        "id": "internal-loads.year.png",
        "command": "plot-template",
        "subcommand": "internal-loads-year",
        "output": "Internal Loads Jahresverlauf",
        "format": "12.8x7.2 cm",
    },
    {
        "id": "internal-loads.timeline.png",
        "command": "plot-template",
        "subcommand": "internal-loads-month/week/day",
        "output": "Internal Loads Zeitverlauf",
        "format": "12.8x7.2 cm",
    },
    {
        "id": "internal-loads.profile.png",
        "command": "plot-template",
        "subcommand": "internal-loads-month/week/day",
        "output": "Internal Loads Profil",
        "format": "12.8x7.2 cm",
    },
    {
        "id": "internal-loads.monthly-sum.png",
        "command": "plot-template",
        "subcommand": "internal-loads-monthly-sum",
        "output": "Internal Loads Monatssummen",
        "format": "11.6x6.6 cm",
    },
    {
        "id": "internal-loads.room-comparison.png",
        "command": "plot-template",
        "subcommand": "internal-loads-room-comparison",
        "output": "Internal Loads Raumvergleich",
        "format": "11.8x6.6 cm",
    },
    {
        "id": "energy-balance.template.png",
        "command": "plot-template",
        "subcommand": "energy-balance",
        "output": "Energiebilanz Zeitdiagramm",
        "format": "12.8x7.2 cm",
    },
    {
        "id": "thermal-room-climate.template.png",
        "command": "plot-template",
        "subcommand": "thermal-room-climate",
        "output": "Raumklima-Zeitdiagramm",
        "format": "12.8x7.2 cm",
    },
    {
        "id": "analyze_data.excel",
        "command": "analyze_data",
        "subcommand": "-",
        "output": "Excel-Auswertung",
        "format": "Keine Größe",
    },
]


def cm_to_inches(width_cm, height_cm):
    return (width_cm / 2.54, height_cm / 2.54)


def get_format_names():
    return list(FORMAT_CATALOG.keys())


def _split_markdown_row(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def load_output_format_rules(doc_path=FORMAT_DOC):
    if not Path(doc_path).exists():
        return [rule.copy() for rule in DEFAULT_OUTPUT_RULES]

    rules = []
    for line in Path(doc_path).read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = _split_markdown_row(line)
        if len(cells) < 5 or cells[0] in {"ID", "---"} or cells[0].startswith("---"):
            continue
        rule_id, command, subcommand, output, format_name = cells[:5]
        if rule_id in {"", "ID"} or command == "---":
            continue
        rules.append(
            {
                "id": rule_id,
                "command": command,
                "subcommand": subcommand,
                "output": output,
                "format": format_name,
            }
        )

    if not rules:
        return [rule.copy() for rule in DEFAULT_OUTPUT_RULES]

    defaults_by_id = {rule["id"]: rule for rule in DEFAULT_OUTPUT_RULES}
    loaded_by_id = {rule["id"]: rule for rule in rules}
    merged = []
    for default_rule in DEFAULT_OUTPUT_RULES:
        merged.append({**default_rule, **loaded_by_id.get(default_rule["id"], {})})
    for rule in rules:
        if rule["id"] not in defaults_by_id:
            merged.append(rule)
    return merged


def write_output_format_rules(rules, doc_path=FORMAT_DOC):
    doc_path = Path(doc_path)
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Zentrale Ausgabeformate",
        "",
        "Dieses Dokument steuert die Standardgroessen fuer erzeugte Diagramme, PDFs und Excel-Ausgaben.",
        "",
        "Regeln:",
        "- Aendere in der Tabelle `Ausgabe-Regeln` die Spalte `Format`.",
        "- Erlaubte Werte stehen unten im `Formatkatalog`.",
        "- Diagrammgroessen werden in Zentimetern angegeben und intern fuer Matplotlib umgerechnet.",
        "- `Keine Größe` wird fuer Ausgaben ohne feste Bild- oder Seitengroesse verwendet.",
        "",
        "## Ausgabe-Regeln",
        "",
        "| ID | Befehl | Unterbefehl | Ausgabe | Format |",
        "| --- | --- | --- | --- | --- |",
    ]
    for rule in rules:
        lines.append(
            f"| {rule['id']} | {rule['command']} | {rule['subcommand']} | {rule['output']} | {rule['format']} |"
        )

    lines.extend(
        [
            "",
            "## Formatkatalog",
            "",
            "| Format | Breite cm | Hoehe cm | Verwendung |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for format_name, values in FORMAT_CATALOG.items():
        width = "" if values["width_cm"] is None else f"{values['width_cm']:g}"
        height = "" if values["height_cm"] is None else f"{values['height_cm']:g}"
        lines.append(f"| {format_name} | {width} | {height} | {values['description']} |")

    doc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_output_format_doc(doc_path=FORMAT_DOC):
    if not Path(doc_path).exists():
        write_output_format_rules(DEFAULT_OUTPUT_RULES, doc_path)
    return Path(doc_path)


def get_rule(rule_id, doc_path=FORMAT_DOC):
    for rule in load_output_format_rules(doc_path):
        if rule["id"] == rule_id:
            return rule
    return None


def get_figure_size_inches(rule_id, fallback_inches=None, doc_path=FORMAT_DOC):
    rule = get_rule(rule_id, doc_path)
    if rule is None:
        return fallback_inches
    format_values = FORMAT_CATALOG.get(rule["format"])
    if not format_values or format_values["width_cm"] is None or format_values["height_cm"] is None:
        return fallback_inches
    return cm_to_inches(format_values["width_cm"], format_values["height_cm"])
