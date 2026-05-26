# ma_analyse

Analysepipeline fuer Simulationsdaten der Masterarbeit.

## Setup

```powershell
python -m pip install -e ".[dev]"
```

## Ordnerstruktur

| Ordner | Zweck |
|---|---|
| `data/input/` | Rohdaten und Variantenordner |
| `data/database/` | aufbereitete Raumdaten |
| `data/output/` | regulaere Analyseausgaben |
| `data/test_output/` | lokale Test- und Smoke-Test-Ausgaben |
| `docs/` | Befehle und Architekturhinweise |
| `src/ma_analyse/app/` | CLI und Befehlssteuerung |
| `src/ma_analyse/core/` | zentrale Konfiguration und Logging |
| `src/ma_analyse/preprocessing/` | Datenvorbereitung aus Rohdaten |
| `src/ma_analyse/analysis/` | Datenverarbeitung, Auswertung und gemeinsame Analyse-Komponenten |
| `src/ma_analyse/settings/` | Naming- und Formatlogik plus zugehoerige Markdown-Dateien |
| `src/ma_analyse/gui/` | grafische Oberflaeche |
| `tests/` | automatisierte Code-Tests |
| `logs/` | automatisch erzeugte Laufprotokolle der Analysebefehle |

## Wichtige Befehle

```powershell
python -m ma_analyse --help
python -m ma_analyse gui
python -m ma_analyse prepare --export-format both
python -m ma_analyse comfort --output-type plot_analysis_overview
python -m ma_analyse analyze-data --series-layout separate
python -m ma_analyse heating --view year --heating-mode single
python -m ma_analyse cooling --view year --variant-mode single
python -m ma_analyse plot-template --template heating-year --variants Dimensionierung --rooms "101 lobby"
python -m ma_analyse all
```

## Qualitaetssicherung

```powershell
python -m ruff check src tests --no-cache
python -m ruff format --check src tests --no-cache
python -m pytest
```

Lokale Daten- und Ausgabeordner unter `data/` sind in `.gitignore` ausgeschlossen. Analysebefehle schreiben automatisch Logdateien mit Schritt- und Gesamtlaufzeiten nach `logs/`; die Logdateien selbst werden nicht versioniert.
