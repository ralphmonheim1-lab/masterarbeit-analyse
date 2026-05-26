"""Erzeugt Heating-Diagramme aus aufbereiteten Raumdaten.

Eingaben:
    CSV-Dateien je Raum aus ``data/database/<Variante>_nutzdaten``.

Ausgaben:
    PNG-Diagramme fuer Balken- und Zeitansichten unter ``data/output`` oder
    einem per CLI/GUI uebergebenen Ausgabeordner.

Wichtige Annahmen:
    Die Heating-Zeitreihe steht in der Spalte ``zone_energy_q_heat`` und die
    Zeitachse nutzt ein nicht-Schaltjahr mit 8760 Stunden.
"""

import argparse
import os

import matplotlib
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.patches import FancyArrowPatch

from ..core.config import COMBINED_HEATING_OUTPUT_DIR, DATENBANK_DIR, ROOMS
from .components.figures import get_figure_size_inches
from .components.heating_year_layout import draw_heating_year_line_plot
from .components.rooms import get_room_data_file
from .components.runtime import annotate_timestamp, get_run_id
from .components.time_windows import MONTH_NAMES, filter_time_window, get_time_window
from .components.variants import get_variant_display_name, normalize_variant_name
from .energy.common import (
    EnergyOutputSpec,
)
from .energy.common import (
    build_combined_plot_filename as build_energy_combined_plot_filename,
)
from .energy.common import (
    build_compare_output_dir as build_energy_compare_output_dir,
)
from .energy.common import (
    build_plot_subtitle as build_energy_plot_subtitle,
)
from .energy.common import (
    build_run_output_dir as build_energy_run_output_dir,
)
from .energy.common import (
    build_single_series_plot_filename as build_energy_single_series_plot_filename,
)
from .energy.common import (
    build_time_axis_config as build_energy_time_axis_config,
)
from .energy.common import (
    build_variant_plot_filename as build_energy_variant_plot_filename,
)
from .energy.common import (
    get_output_prefix as get_energy_output_prefix,
)
from .energy.common import (
    validate_time_selection as validate_energy_time_selection,
)

# ============================================================================
# Konfiguration
# ============================================================================
# Zentrales Ausgabe-Root für alle erzeugten Bilddateien.
# Darunter wird automatisch pro Skriptlauf ein eigener Unterordner angelegt,
# damit alte Ergebnisse nicht überschrieben werden.
REQUIRED_HEATING_COLUMN = "zone_energy_q_heat"


# ============================================================================
# Allgemeine Hilfsfunktionen
# ============================================================================
TECHNICAL_PLOT_BG = "#fbfbfb"
TECHNICAL_GRID_COLOR = "#b8b8b8"
TECHNICAL_SPINE_COLOR = "#2e2e2e"
TECHNICAL_TEXT_COLOR = "#1f1f1f"
HEATING_LINE_COLORS = ["#d62828", "#2563eb", "#2a9d8f", "#f77f00", "#7c3aed", "#0081a7"]
HEATING_OUTPUT_SPEC = EnergyOutputSpec(
    metric="heating",
    output_prefix_label="HeatingComparison",
    combined_output_dir=COMBINED_HEATING_OUTPUT_DIR,
    time_selection_label="heating",
    year_subtitle="Von 01.01.2025 bis 31.12.2025",
)


def get_output_prefix(reference_time=None):
    """Erzeugt den Tagespraefix fuer Heating-Ausgaben."""
    return get_energy_output_prefix(HEATING_OUTPUT_SPEC, reference_time)


def validate_time_selection(view, month=None, week=None, day=None):
    """Prueft CLI-/GUI-Zeitangaben fuer Heating-Auswertungen."""
    return validate_energy_time_selection(HEATING_OUTPUT_SPEC, view, month=month, week=week, day=day)


def build_run_output_dir(variant_dir, run_id, output_root=None):
    """Baut den Laufordner fuer Heating-Einzelplots."""
    return build_energy_run_output_dir(variant_dir, run_id, output_root=output_root)


def build_compare_output_dir(run_id, output_root=None):
    """Baut den Laufordner fuer kombinierte Heating-Variantenvergleiche."""
    return build_energy_compare_output_dir(HEATING_OUTPUT_SPEC, run_id, output_root=output_root)


def build_variant_plot_filename(view, time_window=None):
    """Dateiname fuer separate Heating-Raumplots."""
    return build_energy_variant_plot_filename(HEATING_OUTPUT_SPEC, view, time_window=time_window)


def build_single_series_plot_filename(room, view, time_window=None):
    """Dateiname fuer einen einzelnen Heating-Raumplot."""
    return build_energy_single_series_plot_filename(HEATING_OUTPUT_SPEC, room, view, time_window=time_window)


def build_combined_plot_filename(room, view, time_window=None):
    """Dateiname fuer einen Heating-Variantenvergleich eines Raums."""
    return build_energy_combined_plot_filename(HEATING_OUTPUT_SPEC, room, view, time_window=time_window)


def build_plot_subtitle(view, month_name=None, week_number=None, day_number=None):
    """Kurzer Zeitraumtext fuer Heating-Diagramme."""
    return build_energy_plot_subtitle(
        HEATING_OUTPUT_SPEC,
        view,
        month_name=month_name,
        week_number=week_number,
        day_number=day_number,
    )


def build_time_axis_config(view, time_window=None):
    """Definiert Grid, Zeitstrahl und Zusatzlabels fuer die gewaehlte Heating-Ansicht."""
    return build_energy_time_axis_config(HEATING_OUTPUT_SPEC, view, time_window=time_window)


# ============================================================================
# Achsen- und Diagrammlayout
# ============================================================================


def get_line_color(index):
    """Waehlt eine wiederholbare Linienfarbe fuer die Datenreihe."""
    return HEATING_LINE_COLORS[index % len(HEATING_LINE_COLORS)]


def style_technical_axis(ax, title, subtitle, axis_config, series_count, show_legend, legend_y_anchor=-0.18):
    """Formatiert das Hauptdiagramm ohne sichtbare x-Achsenbeschriftung."""
    ax.set_facecolor(TECHNICAL_PLOT_BG)
    display_title = title
    if title.startswith("Heating Jahresansicht - "):
        display_title = title.replace("Heating Jahresansicht - ", "Heating Jahresansicht\n", 1)
    ax.set_title(display_title, loc="left", fontsize=12, fontweight="bold", color=TECHNICAL_TEXT_COLOR, pad=10)
    ax.text(
        1.0,
        1.10,
        subtitle,
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        color=TECHNICAL_TEXT_COLOR,
    )
    ax.set_ylabel("Heizleistung [W]", fontsize=10, color=TECHNICAL_TEXT_COLOR)
    ax.set_xticks(axis_config.get("grid_ticks", axis_config["ticks"]))
    ax.set_xticklabels([])
    ax.set_xlim(axis_config["x_lim"])
    ax.set_ylim(bottom=0)
    ax.grid(True, which="major", axis="both", color=TECHNICAL_GRID_COLOR, linewidth=0.9)
    ax.tick_params(axis="both", colors=TECHNICAL_TEXT_COLOR, labelsize=9)
    ax.tick_params(axis="x", length=0, labelbottom=False)
    for spine in ax.spines.values():
        spine.set_color(TECHNICAL_SPINE_COLOR)
        spine.set_linewidth(1.1)

    for boundary_tick in axis_config.get("boundary_ticks", []):
        ax.axvline(boundary_tick, color=TECHNICAL_SPINE_COLOR, linewidth=1.0, alpha=0.7)

    legend = None
    if show_legend:
        legend = ax.legend(
            loc="upper left",
            bbox_to_anchor=(0.0, legend_y_anchor),
            frameon=False,
            ncol=min(3, max(1, series_count)),
            fontsize=9,
            handlelength=3.2,
            handletextpad=0.6,
            columnspacing=1.0,
        )
        if legend is not None:
            for text in legend.get_texts():
                text.set_color(TECHNICAL_TEXT_COLOR)


def add_timeline_axis(figure, ax, axis_config):
    """Zeichnet den separaten Pfeil-Zeitstrahl unterhalb des Hauptdiagramms."""
    main_position = ax.get_position()
    timeline_height = 0.12
    timeline_gap = 0.02
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
    arrow = FancyArrowPatch(
        (0.0, line_y),
        (1.02, line_y),
        transform=timeline_ax.transAxes,
        arrowstyle="->",
        mutation_scale=13,
        linewidth=1.1,
        color=TECHNICAL_TEXT_COLOR,
        clip_on=False,
    )
    timeline_ax.add_patch(arrow)

    for tick in axis_config.get("grid_ticks", axis_config["ticks"]):
        tick_line = timeline_ax.vlines(tick, line_y, line_y + 0.10, color=TECHNICAL_TEXT_COLOR, linewidth=0.7)
        tick_line.set_clip_on(False)

    x_start, x_end = axis_config["x_lim"]
    for tick, label in zip(axis_config["ticks"], axis_config["labels"], strict=False):
        tick_line = timeline_ax.vlines(tick, line_y - 0.10, line_y, color=TECHNICAL_TEXT_COLOR, linewidth=0.8)
        tick_line.set_clip_on(False)
        if tick == x_start:
            label_align = "left"
        elif tick == x_end:
            label_align = "right"
        else:
            label_align = "center"
        timeline_ax.text(
            tick,
            line_y - 0.22,
            label,
            ha=label_align,
            va="top",
            fontsize=8.5,
            color=TECHNICAL_TEXT_COLOR,
            clip_on=False,
        )

    annotation_ticks = axis_config.get("annotation_ticks")
    annotation_labels = axis_config.get("annotation_labels")
    if annotation_ticks and annotation_labels:
        for tick, label in zip(annotation_ticks, annotation_labels, strict=False):
            timeline_ax.text(
                tick,
                line_y + 0.16,
                label,
                ha="center",
                va="bottom",
                fontsize=9,
                color=TECHNICAL_TEXT_COLOR,
                clip_on=False,
            )

    return timeline_ax


def draw_technical_line_plot(plot_df, x_col, group_col, title, subtitle, axis_config, output_file):
    """Rendert ein technisches Heating-Zeitdiagramm als PNG.

    ``plot_df`` enthaelt eine oder mehrere Datenreihen. Die Anzahl der
    Datenreihen entscheidet ueber die Formatregel und ob eine Legende sichtbar
    wird.
    """
    line_count = plot_df[group_col].nunique() if group_col in plot_df.columns else 1
    format_rule = "heating.timeline.single.png" if line_count <= 1 else "heating.timeline.compare.png"
    figure, ax = plt.subplots(figsize=get_figure_size_inches(format_rule, (12.8, 7.2)))
    figure.patch.set_facecolor("white")

    series_names = list(dict.fromkeys(plot_df[group_col].tolist()))
    show_legend = len(series_names) > 1
    display_title = title
    if len(series_names) == 1 and series_names[0] not in title:
        display_title = f"{title} - {series_names[0]}"
    for index, series_name in enumerate(series_names):
        series_df = plot_df[plot_df[group_col] == series_name].sort_values(by=x_col)
        ax.plot(
            series_df[x_col],
            series_df["q_heat"],
            color=get_line_color(index),
            linewidth=1.15,
            alpha=0.95,
            label=series_name,
        )

    legend_y_anchor = -0.43 if show_legend else -0.18
    style_technical_axis(
        ax,
        display_title,
        subtitle,
        axis_config,
        len(series_names),
        show_legend=show_legend,
        legend_y_anchor=legend_y_anchor,
    )
    bottom_margin = 0.36 if show_legend else 0.28
    figure.subplots_adjust(left=0.08, right=0.98, top=0.78, bottom=bottom_margin)
    add_timeline_axis(figure, ax, axis_config)
    annotate_timestamp(figure)
    plt.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(figure)


# ============================================================================
# Datenzugriff
# ============================================================================


def get_room_hourly_data(csv_file, debug=False):
    """Lädt die stündliche q_heat-Zeitreihe eines Raums."""
    df = load_room_csv(csv_file, debug=debug)
    if df is None or df.empty:
        return None
    if "time" not in df.columns:
        print(f"    X Spalte 'time' fehlt in {csv_file}")
        return None
    df = df[["time", REQUIRED_HEATING_COLUMN]].copy()
    df["time"] = pd.to_numeric(df["time"], errors="coerce")
    df = df.dropna(subset=["time", REQUIRED_HEATING_COLUMN])
    if df.empty:
        return None
    return df.sort_values(by="time").reset_index(drop=True)


def get_variant_room_series(variant_dir, debug=False, rooms=None):
    """Laedt alle verfuegbaren Raum-Zeitreihen einer Variante."""
    if rooms is None:
        rooms = ROOMS

    series = {}
    for room in rooms:
        csv_file = get_room_data_file(variant_dir, room)
        if not os.path.exists(csv_file):
            print(f"    X CSV für Raum {room} nicht gefunden: {csv_file}")
            continue
        room_df = get_room_hourly_data(csv_file, debug=debug)
        if room_df is not None and not room_df.empty:
            series[room] = room_df
    return series


# ============================================================================
# Zeitdiagramme: eine Variante oder eine einzelne Datenreihe
# ============================================================================


def plot_yearly_single_variant(room_data, variant_name, output_dir, debug=False):
    """Erzeugt einen Jahresplot mit allen ausgewaehlten Raeumen einer Variante."""
    rows = []
    for room, df in room_data.items():
        rows.append(
            pd.DataFrame(
                {
                    "time": df["time"],
                    "room": room,
                    "q_heat": df[REQUIRED_HEATING_COLUMN],
                }
            )
        )

    if not rows:
        print("X Keine Raumdaten für Jahresansicht gefunden.")
        return 0

    plot_df = pd.concat(rows, ignore_index=True)
    os.makedirs(output_dir, exist_ok=True)
    plot_file = os.path.join(output_dir, build_variant_plot_filename("year"))
    draw_heating_year_line_plot(
        plot_df,
        x_col="time",
        group_col="room",
        title=f"Heating Jahresansicht - {variant_name}",
        subtitle=build_plot_subtitle("year"),
        output_file=plot_file,
        line_colors=HEATING_LINE_COLORS,
    )
    print(f"Plot gespeichert: {plot_file}")
    return 1


def plot_monthly_single_variant(room_data, variant_name, output_dir, month_name, debug=False):
    """Erzeugt einen Monatsplot mit allen ausgewaehlten Raeumen einer Variante."""
    time_window = get_time_window("month", month=month_name)
    rows = []
    for room, df in room_data.items():
        temp = filter_time_window(df[["time", REQUIRED_HEATING_COLUMN]].copy(), time_window)
        if temp.empty:
            continue
        temp["room"] = room
        temp["q_heat"] = temp[REQUIRED_HEATING_COLUMN]
        rows.append(temp[["time_window", "room", "q_heat"]])

    if not rows:
        print(f"X Keine Raumdaten für Monatsansicht {month_name} gefunden.")
        return 0

    plot_df = pd.concat(rows, ignore_index=True)

    os.makedirs(output_dir, exist_ok=True)
    plot_file = os.path.join(output_dir, build_variant_plot_filename("month", time_window=time_window))
    draw_technical_line_plot(
        plot_df,
        x_col="time_window",
        group_col="room",
        title=f"Heizlastverlauf Raeume - {variant_name}",
        subtitle=build_plot_subtitle("month", month_name=month_name),
        axis_config=build_time_axis_config("month", time_window=time_window),
        output_file=plot_file,
    )
    print(f"Plot gespeichert: {plot_file}")
    return 1


def plot_weekly_single_variant(room_data, variant_name, output_dir, week_number, debug=False):
    """Erzeugt einen Wochenplot mit allen ausgewaehlten Raeumen einer Variante."""
    time_window = get_time_window("week", week=week_number)
    rows = []
    for room, df in room_data.items():
        temp = filter_time_window(df[["time", REQUIRED_HEATING_COLUMN]].copy(), time_window)
        if temp.empty:
            continue
        temp["room"] = room
        temp["q_heat"] = temp[REQUIRED_HEATING_COLUMN]
        rows.append(temp[["time_window", "room", "q_heat"]])

    if not rows:
        print(f"X Keine Raumdaten für {time_window['title_text']} gefunden.")
        return 0

    plot_df = pd.concat(rows, ignore_index=True)

    os.makedirs(output_dir, exist_ok=True)
    plot_file = os.path.join(output_dir, build_variant_plot_filename("week", time_window=time_window))
    draw_technical_line_plot(
        plot_df,
        x_col="time_window",
        group_col="room",
        title=f"Heizlastverlauf Raeume - {variant_name}",
        subtitle=build_plot_subtitle("week", week_number=week_number),
        axis_config=build_time_axis_config("week", time_window=time_window),
        output_file=plot_file,
    )
    print(f"Plot gespeichert: {plot_file}")
    return 1


def plot_daily_single_variant(room_data, variant_name, output_dir, month_name, day_number, debug=False):
    """Erzeugt einen Tagesplot mit allen ausgewaehlten Raeumen einer Variante."""
    time_window = get_time_window("day", month=month_name, day=day_number)
    rows = []
    for room, df in room_data.items():
        temp = filter_time_window(df[["time", REQUIRED_HEATING_COLUMN]].copy(), time_window)
        if temp.empty:
            continue
        temp["room"] = room
        temp["q_heat"] = temp[REQUIRED_HEATING_COLUMN]
        rows.append(temp[["time_window", "room", "q_heat"]])

    if not rows:
        print(f"X Keine Raumdaten für {time_window['title_text']} gefunden.")
        return 0

    plot_df = pd.concat(rows, ignore_index=True)

    os.makedirs(output_dir, exist_ok=True)
    plot_file = os.path.join(output_dir, build_variant_plot_filename("day", time_window=time_window))
    draw_technical_line_plot(
        plot_df,
        x_col="time_window",
        group_col="room",
        title=f"Heizlastverlauf Raeume - {variant_name}",
        subtitle=build_plot_subtitle("day", month_name=month_name, day_number=day_number),
        axis_config=build_time_axis_config("day", time_window=time_window),
        output_file=plot_file,
    )
    print(f"Plot gespeichert: {plot_file}")
    return 1


def plot_single_room_time_series(
    room_df, variant_name, room, output_dir, view, month_name=None, week_number=None, day_number=None, debug=False
):
    """Erzeugt im Modus ``single`` genau ein Diagramm fuer Variante/Raum."""
    if room_df is None or room_df.empty:
        return 0

    if view == "year":
        plot_df = pd.DataFrame(
            {
                "time_axis": room_df["time"],
                "series": room,
                "q_heat": room_df[REQUIRED_HEATING_COLUMN],
            }
        )
        axis_config = build_time_axis_config("year")
        subtitle = build_plot_subtitle("year")
        plot_file = os.path.join(output_dir, build_single_series_plot_filename(room, "year"))
    else:
        if view == "month":
            time_window = get_time_window("month", month=month_name)
            subtitle = build_plot_subtitle("month", month_name=month_name)
        elif view == "week":
            time_window = get_time_window("week", week=week_number)
            subtitle = build_plot_subtitle("week", week_number=week_number)
        elif view == "day":
            time_window = get_time_window("day", month=month_name, day=day_number)
            subtitle = build_plot_subtitle("day", month_name=month_name, day_number=day_number)
        else:
            raise ValueError(f"Nicht unterstützte Einzelreihen-Ansicht: {view}")

        filtered = filter_time_window(room_df[["time", REQUIRED_HEATING_COLUMN]].copy(), time_window)
        if filtered.empty:
            if debug:
                print(f"    X Keine Daten für {variant_name} / {room} in {time_window['title_text']}.")
            return 0
        plot_df = pd.DataFrame(
            {
                "time_axis": filtered["time_window"],
                "series": room,
                "q_heat": filtered[REQUIRED_HEATING_COLUMN],
            }
        )
        axis_config = build_time_axis_config(view, time_window=time_window)
        plot_file = os.path.join(output_dir, build_single_series_plot_filename(room, view, time_window=time_window))

    if plot_df.empty:
        return 0

    os.makedirs(output_dir, exist_ok=True)
    if view == "year":
        draw_heating_year_line_plot(
            plot_df,
            x_col="time_axis",
            group_col="series",
            title=f"Heating Jahresansicht - {variant_name} / {room}",
            subtitle=subtitle,
            output_file=plot_file,
            line_colors=HEATING_LINE_COLORS,
            single_series_legend_label="Heizleistung",
        )
    else:
        draw_technical_line_plot(
            plot_df,
            x_col="time_axis",
            group_col="series",
            title=f"Heizlastverlauf - {variant_name} - {room}",
            subtitle=subtitle,
            axis_config=axis_config,
            output_file=plot_file,
        )
    print(f"Plot gespeichert: {plot_file}")
    return 1


# ============================================================================
# Zeitdiagramme: Variantenvergleich
# ============================================================================


def plot_yearly_variant_comparison(room_data_by_variant, rooms, output_dir, debug=False):
    """Erzeugt je Raum einen Jahresplot mit mehreren Varianten als Datenreihen."""
    created_count = 0
    for room in rooms:
        rows = []
        for variant_name, room_data in room_data_by_variant.items():
            df = room_data.get(room)
            if df is None or df.empty:
                continue
            rows.append(
                pd.DataFrame(
                    {
                        "time": df["time"],
                        "variant": variant_name,
                        "q_heat": df[REQUIRED_HEATING_COLUMN],
                    }
                )
            )

        if not rows:
            continue

        plot_df = pd.concat(rows, ignore_index=True)

        os.makedirs(output_dir, exist_ok=True)
        plot_file = os.path.join(
            output_dir,
            build_combined_plot_filename(room, "year"),
        )
        draw_heating_year_line_plot(
            plot_df,
            x_col="time",
            group_col="variant",
            title=f"Heating Jahresansicht - {room}",
            subtitle=build_plot_subtitle("year"),
            output_file=plot_file,
            line_colors=HEATING_LINE_COLORS,
        )
        print(f"Plot gespeichert: {plot_file}")
        created_count += 1
    return created_count


def plot_monthly_variant_comparison(room_data_by_variant, rooms, output_dir, month_name, debug=False):
    """Erzeugt je Raum einen Monatsplot mit mehreren Varianten als Datenreihen."""
    time_window = get_time_window("month", month=month_name)
    created_count = 0
    for room in rooms:
        rows = []
        for variant_name, room_data in room_data_by_variant.items():
            df = room_data.get(room)
            if df is None or df.empty:
                continue
            temp = filter_time_window(df[["time", REQUIRED_HEATING_COLUMN]].copy(), time_window)
            if temp.empty:
                continue
            temp["variant"] = variant_name
            temp["q_heat"] = temp[REQUIRED_HEATING_COLUMN]
            rows.append(temp[["time_window", "variant", "q_heat"]])

        if not rows:
            continue

        plot_df = pd.concat(rows, ignore_index=True)

        os.makedirs(output_dir, exist_ok=True)
        plot_file = os.path.join(
            output_dir,
            build_combined_plot_filename(room, "month", time_window=time_window),
        )
        draw_technical_line_plot(
            plot_df,
            x_col="time_window",
            group_col="variant",
            title=f"Heizlastvergleich Varianten - {room}",
            subtitle=build_plot_subtitle("month", month_name=month_name),
            axis_config=build_time_axis_config("month", time_window=time_window),
            output_file=plot_file,
        )
        print(f"Plot gespeichert: {plot_file}")
        created_count += 1
    return created_count


def plot_weekly_variant_comparison(room_data_by_variant, rooms, output_dir, week_number, debug=False):
    """Erzeugt je Raum einen Wochenplot mit mehreren Varianten als Datenreihen."""
    time_window = get_time_window("week", week=week_number)
    created_count = 0
    for room in rooms:
        rows = []
        for variant_name, room_data in room_data_by_variant.items():
            df = room_data.get(room)
            if df is None or df.empty:
                continue
            temp = filter_time_window(df[["time", REQUIRED_HEATING_COLUMN]].copy(), time_window)
            if temp.empty:
                continue
            temp["variant"] = variant_name
            temp["q_heat"] = temp[REQUIRED_HEATING_COLUMN]
            rows.append(temp[["time_window", "variant", "q_heat"]])

        if not rows:
            continue

        plot_df = pd.concat(rows, ignore_index=True)

        os.makedirs(output_dir, exist_ok=True)
        plot_file = os.path.join(
            output_dir,
            build_combined_plot_filename(room, "week", time_window=time_window),
        )
        draw_technical_line_plot(
            plot_df,
            x_col="time_window",
            group_col="variant",
            title=f"Heizlastvergleich Varianten - {room}",
            subtitle=build_plot_subtitle("week", week_number=week_number),
            axis_config=build_time_axis_config("week", time_window=time_window),
            output_file=plot_file,
        )
        print(f"Plot gespeichert: {plot_file}")
        created_count += 1
    return created_count


def plot_daily_variant_comparison(room_data_by_variant, rooms, output_dir, month_name, day_number, debug=False):
    """Erzeugt je Raum einen Tagesplot mit mehreren Varianten als Datenreihen."""
    time_window = get_time_window("day", month=month_name, day=day_number)
    created_count = 0
    for room in rooms:
        rows = []
        for variant_name, room_data in room_data_by_variant.items():
            df = room_data.get(room)
            if df is None or df.empty:
                continue
            temp = filter_time_window(df[["time", REQUIRED_HEATING_COLUMN]].copy(), time_window)
            if temp.empty:
                continue
            temp["variant"] = variant_name
            temp["q_heat"] = temp[REQUIRED_HEATING_COLUMN]
            rows.append(temp[["time_window", "variant", "q_heat"]])

        if not rows:
            continue

        plot_df = pd.concat(rows, ignore_index=True)

        os.makedirs(output_dir, exist_ok=True)
        plot_file = os.path.join(
            output_dir,
            build_combined_plot_filename(room, "day", time_window=time_window),
        )
        draw_technical_line_plot(
            plot_df,
            x_col="time_window",
            group_col="variant",
            title=f"Heizlastvergleich Varianten - {room}",
            subtitle=build_plot_subtitle("day", month_name=month_name, day_number=day_number),
            axis_config=build_time_axis_config("day", time_window=time_window),
            output_file=plot_file,
        )
        print(f"Plot gespeichert: {plot_file}")
        created_count += 1
    return created_count


def load_room_csv(csv_file, debug=False):
    """Lädt aufbereitete CSV-Datei eines Raumes und extrahiert q_heat."""
    try:
        df = pd.read_csv(csv_file)

        if REQUIRED_HEATING_COLUMN not in df.columns:
            print(f"    X Fehlende Spalte {REQUIRED_HEATING_COLUMN} in {csv_file}")
            return None

        # Robuste numerische Konvertierung
        df[REQUIRED_HEATING_COLUMN] = pd.to_numeric(df[REQUIRED_HEATING_COLUMN], errors="coerce")
        df = df.dropna(subset=[REQUIRED_HEATING_COLUMN])

        if debug:
            print(f"    + Geladen: {len(df)} Datenpunkte")
        return df
    except Exception as e:
        print(f"    X Fehler beim Lesen {csv_file}: {e}")
        return None


def get_variant_data(variant_dir, debug=False, rooms=None):
    """Laedt fuer die Balkenansicht die maximale Heizleistung je Raum."""
    if rooms is None:
        rooms = ROOMS

    data = {}
    for room in rooms:
        csv_file = get_room_data_file(variant_dir, room)
        if not os.path.exists(csv_file):
            print(f"    X CSV für Raum {room} nicht gefunden: {csv_file}")
            continue
        df = load_room_csv(csv_file, debug=debug)
        if df is not None:
            max_q_heat = df[REQUIRED_HEATING_COLUMN].max()
            data[room] = max_q_heat
            if debug:
                print(f"    {room}: Max q_heat = {max_q_heat}")
    return data


def main(
    datenbank_dir,
    debug=False,
    selected_variants=None,
    rooms=None,
    view="bar",
    month=None,
    week=None,
    day=None,
    variant_mode="compare",
    series_layout="separate",
    output_root=None,
    run_id=None,
):
    """Laedt Varianten- und Raumdaten und erzeugt die angeforderte Heating-Ausgabe."""
    if not os.path.exists(datenbank_dir):
        print(f"X Verzeichnis mit aufbereiteten Daten nicht gefunden: {datenbank_dir}")
        return

    print("=" * 70)
    print("HEIZVERGLEICH - Vergleichsdiagramme")
    print("=" * 70)

    variants = []
    if os.path.isdir(datenbank_dir):
        for item in os.listdir(datenbank_dir):
            item_path = os.path.join(datenbank_dir, item)
            if os.path.isdir(item_path) and item.endswith("_nutzdaten"):
                variants.append((item, item_path))

    if selected_variants is not None:
        normalized = {normalize_variant_name(v, "_nutzdaten") for v in selected_variants if v.strip()}
        variants = [(name, path) for name, path in variants if name in normalized]

    if not variants:
        print("Keine Varianten gefunden.")
        return

    if not validate_time_selection(view, month=month, week=week, day=day):
        return

    resolved_run_id = get_run_id("heating_comparison", run_id=run_id)
    created_count = 0

    if view == "bar":
        for variant_name, variant_path in variants:
            variant_display_name = get_variant_display_name(variant_name)
            data = get_variant_data(variant_path, debug=debug, rooms=rooms)
            if not data:
                continue

            all_data = [{"room": room, "max_q_heat": max_q_heat} for room, max_q_heat in data.items()]
            df_plot = pd.DataFrame(all_data)

            plt.figure(figsize=get_figure_size_inches("heating.bar.png", (10, 6)))
            sns.barplot(data=df_plot, x="room", y="max_q_heat", palette="viridis")
            plt.title(f"Vergleich der maximalen Heizleistungen (q-heat) - {variant_display_name}")
            plt.xlabel("Raum")
            plt.ylabel("Maximale Heizleistung [W]")
            plt.xticks(rotation=45)
            plt.tight_layout()
            annotate_timestamp(plt.gcf())

            run_output_dir = build_run_output_dir(variant_name, resolved_run_id, output_root)
            os.makedirs(run_output_dir, exist_ok=True)

            plot_file = os.path.join(run_output_dir, build_variant_plot_filename("bar"))
            plt.savefig(plot_file, dpi=300, bbox_inches="tight")
            print(f"Plot gespeichert: {plot_file}")
            plt.close()
            created_count += 1
    else:
        if variant_mode == "single":
            selected_rooms = rooms if rooms is not None else ROOMS
            for variant_name, variant_path in variants:
                variant_display_name = get_variant_display_name(variant_name)
                room_data = get_variant_room_series(variant_path, debug=debug, rooms=selected_rooms)
                if not room_data:
                    print(f"Keine Raumdaten für {variant_display_name} gefunden.")
                    continue

                run_output_dir = build_run_output_dir(variant_name, resolved_run_id, output_root)
                for room in selected_rooms:
                    if room not in room_data:
                        continue
                    created_count += plot_single_room_time_series(
                        room_data[room],
                        variant_display_name,
                        room,
                        run_output_dir,
                        view,
                        month_name=month,
                        week_number=week,
                        day_number=day,
                        debug=debug,
                    )
        else:
            if len(variants) == 1:
                variant_name, variant_path = variants[0]
                variant_display_name = get_variant_display_name(variant_name)
                room_data = get_variant_room_series(variant_path, debug=debug, rooms=rooms)
                if not room_data:
                    print("Keine Raumdaten für die ausgewählte Variante gefunden.")
                    return

                print(
                    f"Hinweis: Variantenvergleich mit nur einer Variante nutzt den Raumvergleich für {variant_display_name}."
                )
                run_output_dir = build_run_output_dir(variant_name, resolved_run_id, output_root)
                if view == "year":
                    created_count = plot_yearly_single_variant(
                        room_data, variant_display_name, run_output_dir, debug=debug
                    )
                elif view == "month":
                    created_count = plot_monthly_single_variant(
                        room_data, variant_display_name, run_output_dir, month, debug=debug
                    )
                elif view == "week":
                    created_count = plot_weekly_single_variant(
                        room_data, variant_display_name, run_output_dir, week, debug=debug
                    )
                elif view == "day":
                    created_count = plot_daily_single_variant(
                        room_data, variant_display_name, run_output_dir, month, day, debug=debug
                    )
                print("=" * 70)
                print(f"Heizvergleich abgeschlossen: {created_count} Plots erstellt")
                print("=" * 70)
                return

            if series_layout == "separate":
                for variant_name, variant_path in variants:
                    variant_display_name = get_variant_display_name(variant_name)
                    room_data = get_variant_room_series(variant_path, debug=debug, rooms=rooms)
                    if not room_data:
                        continue
                    run_output_dir = build_run_output_dir(variant_name, resolved_run_id, output_root)
                    if view == "year":
                        created_count += plot_yearly_single_variant(
                            room_data, variant_display_name, run_output_dir, debug=debug
                        )
                    elif view == "month":
                        created_count += plot_monthly_single_variant(
                            room_data, variant_display_name, run_output_dir, month, debug=debug
                        )
                    elif view == "week":
                        created_count += plot_weekly_single_variant(
                            room_data, variant_display_name, run_output_dir, week, debug=debug
                        )
                    elif view == "day":
                        created_count += plot_daily_single_variant(
                            room_data, variant_display_name, run_output_dir, month, day, debug=debug
                        )
            else:
                room_data_by_variant = {
                    get_variant_display_name(variant_name): get_variant_room_series(
                        variant_path,
                        debug=debug,
                        rooms=rooms,
                    )
                    for variant_name, variant_path in variants
                }
                run_output_dir = build_compare_output_dir(resolved_run_id, output_root)
                if view == "year":
                    created_count = plot_yearly_variant_comparison(
                        room_data_by_variant,
                        rooms if rooms is not None else ROOMS,
                        run_output_dir,
                        debug=debug,
                    )
                elif view == "month":
                    created_count = plot_monthly_variant_comparison(
                        room_data_by_variant,
                        rooms if rooms is not None else ROOMS,
                        run_output_dir,
                        month,
                        debug=debug,
                    )
                elif view == "week":
                    created_count = plot_weekly_variant_comparison(
                        room_data_by_variant,
                        rooms if rooms is not None else ROOMS,
                        run_output_dir,
                        week,
                        debug=debug,
                    )
                elif view == "day":
                    created_count = plot_daily_variant_comparison(
                        room_data_by_variant,
                        rooms if rooms is not None else ROOMS,
                        run_output_dir,
                        month,
                        day,
                        debug=debug,
                    )

    print("=" * 70)
    print(f"Heizvergleich abgeschlossen: {created_count} Plots erstellt")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vergleicht Heizleistungen (q-heat) der Varianten.")
    parser.add_argument(
        "--datenbank_dir",
        default=DATENBANK_DIR,
        help="Verzeichnis mit Varianten-Unterordnern (Standard: data/database)",
    )
    parser.add_argument(
        "--variants",
        type=lambda v: [item.strip() for item in v.split(",") if item.strip()],
        default=None,
        help="Komma-getrennte Liste von Varianten ohne Suffix",
    )
    parser.add_argument(
        "--rooms",
        type=lambda v: [item.strip() for item in v.split(",") if item.strip()],
        default=None,
        help="Komma-getrennte Liste der Räume",
    )
    parser.add_argument(
        "--view",
        choices=["bar", "year", "month", "week", "day"],
        default="bar",
        help="Ansichtsmodus: bar (max), year (Jahresverlauf), month (Monat), week (Kalenderwoche), day (Tag)",
    )
    parser.add_argument(
        "--month", choices=MONTH_NAMES, default=None, help="Monatsfilter für die stündliche Monats- oder Tagesansicht"
    )
    parser.add_argument("--week", type=int, default=None, help="Kalenderwoche für die stündliche Wochenansicht")
    parser.add_argument("--day", type=int, default=None, help="Tag im gewählten Monat für die stündliche Tagesansicht")
    parser.add_argument(
        "--variant-mode",
        choices=["single", "compare"],
        default="compare",
        help="Vergleichsmodus: compare (mehrere Datenreihen je Diagramm) oder single (eine Datenreihe je Diagramm)",
    )
    parser.add_argument(
        "--series-layout",
        choices=["separate", "combined"],
        default="separate",
        help="Diagrammausgabe: separate fuer Variantenplots oder combined fuer Sammelplots",
    )
    parser.add_argument(
        "--output-root", default=None, help="Zielverzeichnis für erzeugte Ausgabeordner (Standard: data/output)"
    )
    parser.add_argument("--run-id", default=None, help="Optionale Lauf-ID fuer die Ablage")
    parser.add_argument("--debug", action="store_true", help="Debug-Ausgaben aktivieren")
    args = parser.parse_args()

    main(
        args.datenbank_dir,
        debug=args.debug,
        selected_variants=args.variants,
        rooms=args.rooms,
        view=args.view,
        month=args.month,
        week=args.week,
        day=args.day,
        variant_mode=args.variant_mode,
        series_layout=args.series_layout,
        output_root=args.output_root,
        run_id=args.run_id,
    )
