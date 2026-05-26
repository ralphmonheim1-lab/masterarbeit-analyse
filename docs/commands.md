# Befehle

Standard-Einstieg ist:

```powershell
python -m ma_analyse <befehl> [optionen]
```

## Einmaliges Setup

```powershell
cd "C:\Users\ralph\Documents\Master\5.Semester\Masterarbeit - lokal\TEIL1_Fach-Anwendungskompetenz\260524_Masterarbeit_Analyse"
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Diesen Installationsbefehl brauchst du nur beim ersten Einrichten, nach dem Neuerstellen der virtuellen Umgebung oder wenn sich Abhaengigkeiten in `pyproject.toml` geaendert haben.

## Taeglicher Start

```powershell
cd "C:\Users\ralph\Documents\Master\5.Semester\Masterarbeit - lokal\TEIL1_Fach-Anwendungskompetenz\260524_Masterarbeit_Analyse"
.\.venv\Scripts\Activate.ps1
python -m ma_analyse gui
```

Relative Standardpfade:

- Rohdaten: `data/input/`
- Aufbereitete Daten: `data/database/`
- Ausgaben: `data/output/`
- Testausgaben: `data/test_output/`

## Hauptbefehle

| Befehl | Zweck | Beispiel |
|---|---|---|
| `gui` | Grafische Oberflaeche starten | `python -m ma_analyse gui` |
| `prepare` | Rohdaten aufbereiten | `python -m ma_analyse prepare --export-format both` |
| `comfort` | Komfortplots und Analyseausgaben | `python -m ma_analyse comfort --output-type plot_analysis_overview` |
| `analyze-data` | Excel-Auswertung erstellen | `python -m ma_analyse analyze-data --series-layout separate` |
| `heating` | Heizlastdiagramme | `python -m ma_analyse heating --view year --heating-mode single` |
| `cooling` | Kuehllastdiagramme | `python -m ma_analyse cooling --view year --variant-mode single` |
| `plot-template` | Manuell anpassbare Diagramm-Vorlagen | `python -m ma_analyse plot-template --template heating-year --variants Dimensionierung --rooms "101 lobby"` |
| `all` | Standardausgaben kombiniert erzeugen | `python -m ma_analyse all` |

Gemeinsame Optionen:

- `--variants "Dimensionierung,I_04_DIM_Heizleistung_60%"`
- `--rooms "101 lobby,109 office"`
- `--output-root "data/test_output/<testart>"`
- `--run-id "<Lauf-ID>"`
- `--debug` / `--no-debug`

`plot-template` nutzt standardmaessig `data/test_output/` und startet mit `heating-year`.
Die erste Vorlage ergaenzt den Heating-Jahresplot um Aussenlufttemperatur,
operative Temperatur und ein Sollwertband von 21 bis 26 °C.
Per CLI koennen die festen Overlays mit `--no-setpoint-band`,
`--no-outdoor-temperature` und `--no-operative-temperature` ausgeblendet werden.
Die Defaultwerte fuer Achsen, Sollwertband und Standard-Overlays liegen in
`src/ma_analyse/settings/plot_templates.toml`. Nach Aenderungen dort die GUI neu
starten oder ueber `GUI aktualisieren` neu laden.

## Logs

Analysebefehle wie `prepare`, `comfort`, `analyze-data`, `heating`, `cooling`, `plot-template` und `all` schreiben pro Lauf automatisch eine Logdatei nach `logs/`. Die Logdatei enthaelt die Konsolenausgabe, Laufzeiten je Schritt und die Gesamtlaufzeit.
## Settings

```powershell
python -m ma_analyse.settings.naming --dry-run
```

Naming-, Ausgabeformat- und Plot-Template-Einstellungen liegen neben der zugehoerigen Logik unter `src/ma_analyse/settings/`.


