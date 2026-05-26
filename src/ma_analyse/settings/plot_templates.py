"""Konfiguration fuer manuell anpassbare Plot-Templates."""

from __future__ import annotations

import copy
import tomllib
from pathlib import Path

from ..core.config import PLOT_TEMPLATES_CONFIG

HEATING_YEAR_KEY = "heating_year"
OUTDOOR_OVERLAY_ID = "outdoor_temperature"
OPERATIVE_OVERLAY_ID = "operative_temperature"

DEFAULT_PLOT_TEMPLATE_CONFIG = {
    HEATING_YEAR_KEY: {
        "setpoint_min": 21.0,
        "setpoint_max": 26.0,
        "temperature_ymin": -20.0,
        "temperature_ymax": 40.0,
        "show_setpoint_band": True,
        "show_outdoor_temperature": True,
        "show_operative_temperature": True,
        "outdoor_column": "tair",
        "default_overlays": [
            {
                "id": "outdoor_temperature",
                "label": "Außenlufttemperatur",
                "source": "aux",
                "column": "tair",
                "axis": "temperature",
                "enabled": True,
            },
            {
                "id": "operative_temperature",
                "label": "Operative Temperatur",
                "source": "csv",
                "column": "temperatures_top",
                "fallback_columns": ["local_de_comf_diag_t_top"],
                "axis": "temperature",
                "enabled": True,
            },
        ],
    }
}


def _as_float(value, fallback):
    try:
        return float(value)
    except TypeError, ValueError:
        return fallback


def _as_bool(value, fallback):
    if isinstance(value, bool):
        return value
    return fallback


def _as_text(value, fallback):
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _normalize_overlay(raw_overlay):
    if not isinstance(raw_overlay, dict):
        return None

    source = _as_text(raw_overlay.get("source"), "")
    column = _as_text(raw_overlay.get("column"), "")
    axis = _as_text(raw_overlay.get("axis"), "")
    if source not in {"csv", "aux"} or axis not in {"heat", "temperature"} or not column:
        return None

    overlay = {
        "id": _as_text(raw_overlay.get("id"), f"{source}:{column}"),
        "label": _as_text(raw_overlay.get("label"), column),
        "source": source,
        "column": column,
        "axis": axis,
        "enabled": _as_bool(raw_overlay.get("enabled"), True),
    }
    fallback_columns = raw_overlay.get("fallback_columns")
    if isinstance(fallback_columns, list):
        overlay["fallback_columns"] = [item for item in fallback_columns if isinstance(item, str) and item.strip()]
    return overlay


def _merge_heating_year_config(loaded):
    defaults = copy.deepcopy(DEFAULT_PLOT_TEMPLATE_CONFIG[HEATING_YEAR_KEY])
    if not isinstance(loaded, dict):
        return defaults

    config = defaults.copy()
    has_explicit_outdoor_column = "outdoor_column" in loaded
    config["setpoint_min"] = _as_float(loaded.get("setpoint_min"), defaults["setpoint_min"])
    config["setpoint_max"] = _as_float(loaded.get("setpoint_max"), defaults["setpoint_max"])
    config["temperature_ymin"] = _as_float(loaded.get("temperature_ymin"), defaults["temperature_ymin"])
    config["temperature_ymax"] = _as_float(loaded.get("temperature_ymax"), defaults["temperature_ymax"])
    config["show_setpoint_band"] = _as_bool(
        loaded.get("show_setpoint_band"),
        defaults["show_setpoint_band"],
    )
    config["show_outdoor_temperature"] = _as_bool(
        loaded.get("show_outdoor_temperature"),
        defaults["show_outdoor_temperature"],
    )
    config["show_operative_temperature"] = _as_bool(
        loaded.get("show_operative_temperature"),
        defaults["show_operative_temperature"],
    )
    config["outdoor_column"] = _as_text(loaded.get("outdoor_column"), defaults["outdoor_column"])

    loaded_overlays = loaded.get("default_overlays")
    if isinstance(loaded_overlays, list):
        overlays = [_normalize_overlay(item) for item in loaded_overlays]
        overlays = [item for item in overlays if item is not None]
        if overlays:
            config["default_overlays"] = overlays
            if not has_explicit_outdoor_column:
                outdoor_overlay = next(
                    (item for item in overlays if item.get("id") == OUTDOOR_OVERLAY_ID),
                    None,
                )
                if outdoor_overlay is not None:
                    config["outdoor_column"] = outdoor_overlay["column"]
    return config


def load_plot_template_config(config_path=PLOT_TEMPLATES_CONFIG):
    """Laedt die Plot-Template-Konfiguration mit stabilen Fallbacks."""
    path = Path(config_path)
    if not path.exists():
        return copy.deepcopy(DEFAULT_PLOT_TEMPLATE_CONFIG)

    try:
        loaded = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Plot-Template-Konfiguration ist ungueltig: {path}") from exc

    return {
        HEATING_YEAR_KEY: _merge_heating_year_config(loaded.get(HEATING_YEAR_KEY)),
    }


def get_heating_year_template_defaults(config_path=PLOT_TEMPLATES_CONFIG):
    return load_plot_template_config(config_path)[HEATING_YEAR_KEY]


__all__ = [
    "DEFAULT_PLOT_TEMPLATE_CONFIG",
    "HEATING_YEAR_KEY",
    "OPERATIVE_OVERLAY_ID",
    "OUTDOOR_OVERLAY_ID",
    "get_heating_year_template_defaults",
    "load_plot_template_config",
]
