"""Plot-Templates fuer Heating- und Cooling-Barplots."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd
import seaborn as sns

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from ...core.config import DATENBANK_DIR, TEST_OUTPUT_DIR
from .. import cooling as cooling_analysis
from .. import heating as heating_analysis
from ..components.figures import get_figure_size_inches
from ..components.runtime import annotate_timestamp, get_run_id
from ..components.variants import get_variant_display_name, normalize_variant_name, strip_variant_suffix
from .catalog import COOLING_BAR_TEMPLATE, HEATING_BAR_TEMPLATE, get_plot_template_spec

BAR_TEMPLATE_MODULES = {
    "heating_bar": heating_analysis,
    "cooling_bar": cooling_analysis,
}
BAR_VALUE_COLUMNS = {
    "heating_bar": "max_q_heat",
    "cooling_bar": "max_q_cool",
}
BAR_TITLES = {
    "heating_bar": "Vergleich der maximalen Heizleistungen (q-heat)",
    "cooling_bar": "Vergleich der maximalen Kuehlleistungen (q-cool)",
}
BAR_Y_LABELS = {
    "heating_bar": "Maximale Heizleistung [W]",
    "cooling_bar": "Kuehlleistung [W]",
}


def _resolve_processed_variant_dir(datenbank_dir: str | Path, variant_name: str) -> Path:
    variant_stem = strip_variant_suffix(variant_name)
    variant_dir = Path(datenbank_dir) / normalize_variant_name(variant_stem, "_nutzdaten")
    if not variant_dir.exists():
        raise FileNotFoundError(f"Aufbereitete Variante nicht gefunden: {variant_dir}")
    return variant_dir


def validate_bar_template_request(
    template: str,
    variants: list[str] | tuple[str, ...] | None,
    rooms: list[str] | tuple[str, ...] | None,
) -> list[str]:
    """Prueft Mindestangaben fuer Barplot-Templates."""
    errors = []
    spec = get_plot_template_spec(template)
    if spec is None or spec.metric not in BAR_TEMPLATE_MODULES:
        errors.append(f"Unbekanntes Barplot-Template: {template}")
        return errors
    if not variants:
        errors.append("plot-template erwartet mindestens eine Variante.")
    if not rooms:
        errors.append("plot-template erwartet mindestens einen Raum.")
    return errors


def _draw_heating_barplot(plot_df: pd.DataFrame, variant_name: str, output_file: str | Path) -> None:
    figure, ax = plt.subplots(figsize=get_figure_size_inches("heating.bar.png", (10, 6)))
    sns.barplot(data=plot_df, x="room", y="max_q_heat", hue="room", palette="viridis", legend=False, ax=ax)
    ax.set_title(f"{BAR_TITLES['heating_bar']} - {variant_name}")
    ax.set_xlabel("Raum")
    ax.set_ylabel(BAR_Y_LABELS["heating_bar"])
    ax.tick_params(axis="x", rotation=45)
    figure.tight_layout()
    annotate_timestamp(figure)
    figure.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(figure)


def _draw_cooling_barplot(plot_df: pd.DataFrame, variant_name: str, output_file: str | Path) -> None:
    figure, ax = plt.subplots(figsize=get_figure_size_inches("cooling.bar.png", (10, 6)))
    ax.bar(plot_df["room"], plot_df["max_q_cool"], color="#ff0000", edgecolor="#b00000", linewidth=0.8)
    ax.axhline(0, color="#2e2e2e", linewidth=1.1)
    ax.set_title(f"{BAR_TITLES['cooling_bar']} - {variant_name}")
    ax.set_xlabel("Raum")
    ax.set_ylabel(BAR_Y_LABELS["cooling_bar"])
    ax.grid(True, axis="y", color="#b8b8b8", linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", rotation=45)
    min_value = plot_df["max_q_cool"].min()
    ax.set_ylim(min_value * 1.12 if min_value < 0 else -1, 0)
    figure.tight_layout()
    annotate_timestamp(figure)
    figure.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(figure)


def _build_output_file(output_dir: Path, template: str) -> Path:
    if template == HEATING_BAR_TEMPLATE:
        return output_dir / "heating_bar_template.png"
    if template == COOLING_BAR_TEMPLATE:
        return output_dir / "cooling_bar_template.png"
    raise ValueError(f"Unbekanntes Barplot-Template: {template}")


def build_bar_template(
    datenbank_dir: str | Path = DATENBANK_DIR,
    output_root: str | Path | None = TEST_OUTPUT_DIR,
    selected_variants: list[str] | tuple[str, ...] | None = None,
    rooms: list[str] | tuple[str, ...] | None = None,
    template: str = HEATING_BAR_TEMPLATE,
    run_id: str | None = None,
    debug: bool = False,
) -> str | list[str]:
    """Erzeugt Heating-/Cooling-Barplot-Templates fuer eine oder mehrere Varianten."""
    errors = validate_bar_template_request(template, selected_variants, rooms)
    if errors:
        raise ValueError("; ".join(errors))

    spec = get_plot_template_spec(template)
    metric_module = BAR_TEMPLATE_MODULES[spec.metric]
    value_column = BAR_VALUE_COLUMNS[spec.metric]
    output_base = Path(output_root or TEST_OUTPUT_DIR)
    resolved_run_id = get_run_id("plot_template", run_id=run_id)
    output_files = []

    for variant_name in selected_variants:
        processed_variant_dir = _resolve_processed_variant_dir(datenbank_dir, variant_name)
        variant_display_name = get_variant_display_name(processed_variant_dir)
        data = metric_module.get_variant_data(processed_variant_dir, debug=debug, rooms=rooms)
        if not data:
            raise ValueError(f"Keine Barplot-Daten fuer {variant_display_name} gefunden.")

        plot_df = pd.DataFrame({"room": list(data.keys()), value_column: list(data.values())})
        output_dir = output_base / "PlotTemplates" / resolved_run_id / variant_display_name
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = _build_output_file(output_dir, template)

        if template == HEATING_BAR_TEMPLATE:
            _draw_heating_barplot(plot_df, variant_display_name, output_file)
        elif template == COOLING_BAR_TEMPLATE:
            _draw_cooling_barplot(plot_df, variant_display_name, output_file)
        else:
            raise ValueError(f"Unbekanntes Barplot-Template: {template}")

        if debug:
            print(f"Template: {template}")
            print(f"Template-Variante: {variant_display_name}")
            print(f"Template-Raeume: {len(plot_df)}")
        output_files.append(str(output_file))

    if len(output_files) == 1:
        return output_files[0]
    return output_files
