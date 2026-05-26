"""Auswahl- und Listenhelfer fuer die GUI."""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..core.config import ROOMS


def format_cli_list(values):
    """Wandelt eine Liste zurueck in das CLI-Listenformat."""
    if not values:
        return None
    return ",".join(values)


def list_input_variants(input_root):
    """Listet Rohdatenvarianten fuer den prepare-Befehl."""
    if not os.path.isdir(input_root):
        return []
    return sorted(
        entry
        for entry in os.listdir(input_root)
        if os.path.isdir(os.path.join(input_root, entry))
        and any(os.path.isdir(os.path.join(input_root, entry, room_name)) for room_name in ROOMS)
    )


def list_datenbank_variants(datenbank_dir):
    """Listet Nutzdatenvarianten fuer Analyse- und Plotbefehle."""
    if not os.path.isdir(datenbank_dir):
        return []
    return sorted(
        entry
        for entry in os.listdir(datenbank_dir)
        if os.path.isdir(os.path.join(datenbank_dir, entry)) and entry.endswith("_nutzdaten")
    )


def strip_variant_suffix(variant_name):
    """Entfernt bekannte Varianten-Suffixe fuer GUI-Anzeigen."""
    for suffix in ("_rohdaten", "_nutzdaten"):
        if variant_name.endswith(suffix):
            return variant_name[: -len(suffix)]
    return variant_name


@dataclass(frozen=True)
class VariantListState:
    """Beschreibt den gewuenschten GUI-Zustand der Variantenliste."""

    selectmode: str
    selected_indices: tuple[int, ...]
    enabled: bool


def resolve_variant_list_state(variant_count, scope, current_selection=(), previous_scope=None):
    """Ermittelt Varianten-Listbox-Zustand ohne Tk-Abhaengigkeit."""
    if variant_count <= 0:
        return VariantListState(selectmode="multiple", selected_indices=(), enabled=False)

    valid_selection = tuple(index for index in current_selection if 0 <= index < variant_count)
    if previous_scope == "Alle Varianten" and scope != "Alle Varianten":
        valid_selection = ()

    if scope == "Eine Variante":
        return VariantListState(selectmode="browse", selected_indices=valid_selection[:1], enabled=True)

    if scope == "Mehrere Varianten":
        return VariantListState(selectmode="multiple", selected_indices=valid_selection, enabled=True)

    if scope == "Alle Varianten":
        return VariantListState(selectmode="multiple", selected_indices=tuple(range(variant_count)), enabled=False)

    return VariantListState(selectmode="multiple", selected_indices=(), enabled=True)
