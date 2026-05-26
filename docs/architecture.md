# Architektur

`ma_analyse` ist als Python-Paket unter `src/ma_analyse` aufgebaut. Die CLI und GUI nutzen dieselben fachlichen Funktionen, damit Ergebnisse reproduzierbar bleiben.

## Datenfluss

1. `prepare` liest Varianten aus `data/input/` und schreibt Raumtabellen nach `data/database/`.
2. `comfort`, `heating`, `cooling` und `analyze-data` lesen aus `data/database/`.
3. Regulaere Ergebnisse landen in `data/output/`, Smoke-Tests und Experimente in `data/test_output/`.
4. CLI-Analysebefehle spiegeln Konsolenausgaben automatisch nach `logs/`.

## Zentrale Pakete

| Paket/Modul | Aufgabe |
|---|---|
| `app/cli.py` | CLI-Parser und Paket-Einstieg |
| `app/commands.py` | Befehlsausfuehrung und Schritt-Orchestrierung |
| `core/config.py` | Pfade, Raeume, Dateinamen und gemeinsame Konstanten |
| `core/logging.py` | automatische Logdateien fuer Analyse-CLI-Laeufe |
| `preprocessing/prepare.py` | Rohdaten aus PRN-Dateien in Raumtabellen ueberfuehren |
| `analysis/excel.py` | Ablauf fuer Kennzahlen- und Excel-Berichte |
| `analysis/heating.py` | Ablauf fuer Heizlast-Zeitreihen und Vergleichsplots |
| `analysis/cooling.py` | Ablauf fuer Kuehllast-Zeitreihen und Vergleichsplots |
| `analysis/templates/` | Manuell anpassbare Diagramm-Vorlagen fuer Plot-Experimente |
| `analysis/comfort/` | Comfort-Ablauf, Datenladen, Zonen, Tabellen und Plotmodule |
| `analysis/components/` | gemeinsame Analyse-Komponenten fuer Raeume, Varianten, Zeitfenster, Laufordner und Figures |
| `analysis/energy/` | gemeinsame Ausgabe-, Zeit- und Dateinamenlogik fuer Heating und Cooling |
| `analysis/tables/` | Schema, Kennwertberechnung und Excel-Schreiben fuer Tabellenberichte |
| `gui/` | Grafische Oberflaeche, Dialoge, GUI-Worker und Singleton-Steuerung |
| `settings.naming` | Namensmapping lesen und anwenden; Dokument liegt daneben als `naming.md` |
| `settings.formats` | Ausgabeformate lesen und bereitstellen; Dokument liegt daneben als `output_formats.md` |
| `settings.plot_templates` | Plot-Template-Defaults aus `plot_templates.toml` lesen |

## Plot-Template Promotion

`plot-template` ist der Experimentierpfad fuer neue Plot-Ideen. Diese Ausgaben
laufen standardmaessig nach `data/test_output/PlotTemplates/...` und duerfen
schneller veraendert werden als die Hauptbefehle.

Wenn eine Template-Idee in eine Hauptfunktion uebernommen wird, gilt die Methode
**Geteilte Helper**:

1. Neue Darstellung oder Datenlogik zuerst im Template sichtbar testen.
2. Verhalten mit einem fokussierten Test oder Smoke-Test absichern.
3. Wiederverwendbare Logik in ein neutrales Modul auslagern, bevorzugt unter
   `analysis/components/` oder einem passenden Fachpaket.
4. Template und Hauptfunktion nutzen danach denselben Helper.
5. Keine experimentellen Overlay-, CLI- oder GUI-Optionen automatisch in
   Hauptfunktionen uebernehmen; solche Optionen brauchen eine eigene bewusste
   Promotion.

Aktuelle Beispiele:

- `analysis/components/heating_year_layout.py` enthaelt die geteilte
  Jahreslayoutbasis fuer `plot-template heating-year` und die regulaere
  Heating-Jahresansicht.
- `analysis/templates/catalog.py` und `analysis/templates/timeline.py`
  strukturieren die Template-Sandbox fuer Heating-/Cooling-Zeitansichten.

## Naechste Modularisierung

- Heating und Cooling weiter in Energy-Runner, Datenladen und Plotmodule zerlegen.
- Comfort-Runner weiter verkleinern, falls Auswahl- und Prozesslogik wachsen.
- GUI weiter in kleinere Komponenten fuer Layout, Dialoge und Laufsteuerung aufteilen.
