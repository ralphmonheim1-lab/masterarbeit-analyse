"""Katalog der verfuegbaren Plot-Template-Namen."""

from __future__ import annotations

from dataclasses import dataclass

HEATING_YEAR_TEMPLATE = "heating-year"
HEATING_MONTH_TEMPLATE = "heating-month"
HEATING_WEEK_TEMPLATE = "heating-week"
HEATING_DAY_TEMPLATE = "heating-day"
COOLING_YEAR_TEMPLATE = "cooling-year"
COOLING_MONTH_TEMPLATE = "cooling-month"
COOLING_WEEK_TEMPLATE = "cooling-week"
COOLING_DAY_TEMPLATE = "cooling-day"
HEATING_BAR_TEMPLATE = "heating-bar"
COOLING_BAR_TEMPLATE = "cooling-bar"
COMFORT_PLOT_TEMPLATE = "comfort-plot"
COMFORT_PLOT_OVERVIEW_TEMPLATE = "comfort-plot-overview"
COMFORT_ANALYSIS_TEMPLATE = "comfort-analysis"
COMFORT_ANALYSIS_OVERVIEW_TEMPLATE = "comfort-analysis-overview"
INTERNAL_LOADS_YEAR_TEMPLATE = "internal-loads-year"
INTERNAL_LOADS_MONTH_TEMPLATE = "internal-loads-month"
INTERNAL_LOADS_WEEK_TEMPLATE = "internal-loads-week"
INTERNAL_LOADS_DAY_TEMPLATE = "internal-loads-day"
INTERNAL_LOADS_MONTHLY_SUM_TEMPLATE = "internal-loads-monthly-sum"
INTERNAL_LOADS_ROOM_COMPARISON_TEMPLATE = "internal-loads-room-comparison"
ENERGY_BALANCE_YEAR_TEMPLATE = "energy-balance-year"
ENERGY_BALANCE_MONTH_TEMPLATE = "energy-balance-month"
ENERGY_BALANCE_WEEK_TEMPLATE = "energy-balance-week"
ENERGY_BALANCE_DAY_TEMPLATE = "energy-balance-day"
THERMAL_ROOM_CLIMATE_YEAR_TEMPLATE = "thermal-room-climate-year"
THERMAL_ROOM_CLIMATE_MONTH_TEMPLATE = "thermal-room-climate-month"
THERMAL_ROOM_CLIMATE_WEEK_TEMPLATE = "thermal-room-climate-week"
THERMAL_ROOM_CLIMATE_DAY_TEMPLATE = "thermal-room-climate-day"


@dataclass(frozen=True)
class PlotTemplateSpec:
    """Beschreibt ein auswaehlbares Plot-Template."""

    name: str
    metric: str
    view: str
    supports_overlays: bool = False
    requires_single_room: bool = True


PLOT_TEMPLATE_SPECS = {
    HEATING_YEAR_TEMPLATE: PlotTemplateSpec(HEATING_YEAR_TEMPLATE, "heating", "year", supports_overlays=True),
    HEATING_MONTH_TEMPLATE: PlotTemplateSpec(HEATING_MONTH_TEMPLATE, "heating", "month"),
    HEATING_WEEK_TEMPLATE: PlotTemplateSpec(HEATING_WEEK_TEMPLATE, "heating", "week"),
    HEATING_DAY_TEMPLATE: PlotTemplateSpec(HEATING_DAY_TEMPLATE, "heating", "day"),
    HEATING_BAR_TEMPLATE: PlotTemplateSpec(HEATING_BAR_TEMPLATE, "heating_bar", "bar", requires_single_room=False),
    COOLING_YEAR_TEMPLATE: PlotTemplateSpec(COOLING_YEAR_TEMPLATE, "cooling", "year"),
    COOLING_MONTH_TEMPLATE: PlotTemplateSpec(COOLING_MONTH_TEMPLATE, "cooling", "month"),
    COOLING_WEEK_TEMPLATE: PlotTemplateSpec(COOLING_WEEK_TEMPLATE, "cooling", "week"),
    COOLING_DAY_TEMPLATE: PlotTemplateSpec(COOLING_DAY_TEMPLATE, "cooling", "day"),
    COOLING_BAR_TEMPLATE: PlotTemplateSpec(COOLING_BAR_TEMPLATE, "cooling_bar", "bar", requires_single_room=False),
    COMFORT_PLOT_TEMPLATE: PlotTemplateSpec(COMFORT_PLOT_TEMPLATE, "comfort", "plot"),
    COMFORT_PLOT_OVERVIEW_TEMPLATE: PlotTemplateSpec(
        COMFORT_PLOT_OVERVIEW_TEMPLATE,
        "comfort",
        "plot-overview",
        requires_single_room=False,
    ),
    COMFORT_ANALYSIS_TEMPLATE: PlotTemplateSpec(COMFORT_ANALYSIS_TEMPLATE, "comfort", "analysis"),
    COMFORT_ANALYSIS_OVERVIEW_TEMPLATE: PlotTemplateSpec(
        COMFORT_ANALYSIS_OVERVIEW_TEMPLATE,
        "comfort",
        "analysis-overview",
        requires_single_room=False,
    ),
    INTERNAL_LOADS_YEAR_TEMPLATE: PlotTemplateSpec(INTERNAL_LOADS_YEAR_TEMPLATE, "internal_loads", "year"),
    INTERNAL_LOADS_MONTH_TEMPLATE: PlotTemplateSpec(INTERNAL_LOADS_MONTH_TEMPLATE, "internal_loads", "month"),
    INTERNAL_LOADS_WEEK_TEMPLATE: PlotTemplateSpec(INTERNAL_LOADS_WEEK_TEMPLATE, "internal_loads", "week"),
    INTERNAL_LOADS_DAY_TEMPLATE: PlotTemplateSpec(INTERNAL_LOADS_DAY_TEMPLATE, "internal_loads", "day"),
    INTERNAL_LOADS_MONTHLY_SUM_TEMPLATE: PlotTemplateSpec(
        INTERNAL_LOADS_MONTHLY_SUM_TEMPLATE,
        "internal_loads",
        "monthly-sum",
    ),
    INTERNAL_LOADS_ROOM_COMPARISON_TEMPLATE: PlotTemplateSpec(
        INTERNAL_LOADS_ROOM_COMPARISON_TEMPLATE,
        "internal_loads",
        "room-comparison",
        requires_single_room=False,
    ),
    ENERGY_BALANCE_YEAR_TEMPLATE: PlotTemplateSpec(ENERGY_BALANCE_YEAR_TEMPLATE, "energy_balance", "year"),
    ENERGY_BALANCE_MONTH_TEMPLATE: PlotTemplateSpec(ENERGY_BALANCE_MONTH_TEMPLATE, "energy_balance", "month"),
    ENERGY_BALANCE_WEEK_TEMPLATE: PlotTemplateSpec(ENERGY_BALANCE_WEEK_TEMPLATE, "energy_balance", "week"),
    ENERGY_BALANCE_DAY_TEMPLATE: PlotTemplateSpec(ENERGY_BALANCE_DAY_TEMPLATE, "energy_balance", "day"),
    THERMAL_ROOM_CLIMATE_YEAR_TEMPLATE: PlotTemplateSpec(
        THERMAL_ROOM_CLIMATE_YEAR_TEMPLATE,
        "thermal_room_climate",
        "year",
    ),
    THERMAL_ROOM_CLIMATE_MONTH_TEMPLATE: PlotTemplateSpec(
        THERMAL_ROOM_CLIMATE_MONTH_TEMPLATE,
        "thermal_room_climate",
        "month",
    ),
    THERMAL_ROOM_CLIMATE_WEEK_TEMPLATE: PlotTemplateSpec(
        THERMAL_ROOM_CLIMATE_WEEK_TEMPLATE,
        "thermal_room_climate",
        "week",
    ),
    THERMAL_ROOM_CLIMATE_DAY_TEMPLATE: PlotTemplateSpec(
        THERMAL_ROOM_CLIMATE_DAY_TEMPLATE,
        "thermal_room_climate",
        "day",
    ),
}
PLOT_TEMPLATE_CHOICES = tuple(PLOT_TEMPLATE_SPECS)
TIMELINE_TEMPLATE_CHOICES = tuple(
    template_name for template_name, spec in PLOT_TEMPLATE_SPECS.items() if not spec.supports_overlays
)


def get_plot_template_spec(template: str) -> PlotTemplateSpec | None:
    """Gibt die Template-Spezifikation fuer einen Namen zurueck."""
    return PLOT_TEMPLATE_SPECS.get(template)


def is_time_filtered_template(template: str) -> bool:
    """Prueft, ob das Template eine Monats-, Wochen- oder Tagesauswahl braucht."""
    spec = get_plot_template_spec(template)
    return spec is not None and spec.view in {"month", "week", "day"}


def template_uses_overlay_options(template: str) -> bool:
    """Prueft, ob fuer das Template Overlay-Optionen sichtbar sein sollen."""
    spec = get_plot_template_spec(template)
    return spec is not None and spec.supports_overlays


def template_requires_single_room(template: str) -> bool:
    """Prueft, ob das Template genau einen Raum erwartet."""
    spec = get_plot_template_spec(template)
    return spec is None or spec.requires_single_room


def is_internal_loads_template(template: str) -> bool:
    """Prueft, ob ein Template interne Lasten visualisiert."""
    spec = get_plot_template_spec(template)
    return spec is not None and spec.metric == "internal_loads"


def is_energy_balance_template(template: str) -> bool:
    """Prueft, ob ein Template eine Energiebilanz visualisiert."""
    spec = get_plot_template_spec(template)
    return spec is not None and spec.metric == "energy_balance"


def is_comfort_template(template: str) -> bool:
    """Prueft, ob ein Template Comfort-Ausgaben visualisiert."""
    spec = get_plot_template_spec(template)
    return spec is not None and spec.metric == "comfort"


def is_bar_template(template: str) -> bool:
    """Prueft, ob ein Template Heating-/Cooling-Barplots visualisiert."""
    spec = get_plot_template_spec(template)
    return spec is not None and spec.metric in {"heating_bar", "cooling_bar"}


def is_thermal_room_climate_template(template: str) -> bool:
    """Prueft, ob ein Template das thermische Raumklima visualisiert."""
    spec = get_plot_template_spec(template)
    return spec is not None and spec.metric == "thermal_room_climate"
