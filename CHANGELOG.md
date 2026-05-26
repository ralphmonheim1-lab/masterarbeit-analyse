# Changelog

Alle nennenswerten Aenderungen an `ma_analyse` werden in dieser Datei dokumentiert.

## Unreleased

### Added
- Keine aktuellen Unreleased-Änderungen.

## 0.3.1 - 2026-05-26

### Added
- `plot-template` um Comfort-PNGs, Comfort-PDF-Uebersichten, Heating-/Cooling-Barplots und Thermisches-Raumklima-Templates erweitert.
- Neuer CLI-Befehl `plot-template-examples` erzeugt die reproduzierbare Dokumentationsgalerie unter `docs/examples/plot_templates/` und aktualisiert `docs/plot_template_examples.md`.

### Changed
- GUI-Fenster bleibt unter Windows auch mit eigener Titelleiste in der Taskleiste sichtbar.

## 0.3.0 - 2026-05-26

### Added
- Plot-Templates fuer interne Lasten aus Licht, Belegung und Equipment ergaenzt.
- Plot-Templates fuer Energiebilanz-Uebersichten in Year/Month/Week/Day ergaenzt.

### Changed
- GUI-Plot-Template-Auswahl erlaubt fuer `internal-loads-room-comparison` mehrere Raeume.
- Internal-Loads-Templates auf drei sichtbare Datenreihen aus Personen, Geraeten und Beleuchtung ausgerichtet; Week/Day nutzen gestapelte Lastprofil-Balken.

## 0.2.3 - 2026-05-26

### Added
- `plot-template` um `heating-month`, `heating-week`, `heating-day`, `cooling-year`, `cooling-month`, `cooling-week` und `cooling-day` erweitert.
- Gemeinsamen Template-Katalog und Timeline-Template-Builder fuer Heating-/Cooling-Zeitansichten ergaenzt.
- Tests fuer neue Plot-Template-Auswahlwerte, Zeitvalidierung und PNG-Smoke-Laeufe ergaenzt.
- `docs/PLAN_STATUS.md` als persoenliche Planungssuebersicht ergaenzt.
- Archivordner `docs/plan_status/` fuer regelmaessige Planstatus-Staende ergaenzt.

### Changed
- GUI-Template-Auswahl zeigt alle Plot-Templates und blendet Zeitdetails fuer Monats-, Wochen- und Tages-Templates ein.
- Professor-Agent unter `.github/agents/Professor.md` auf die Masterarbeits-Auswertungssoftware und Dokumentationsregeln ausgerichtet.
- GUI-Reset springt nach dem Zuruecksetzen wieder auf den ersten Schritt `Befehl`.
- Planungsuebersicht nach `docs/PLAN_STATUS.md` verschoben; `CHANGELOG.md` bleibt im Projekt-Root.
- `docs/PLAN_STATUS.md` auf aktive offene Punkte reduziert; Vollstand nach `docs/plan_status/2026-05-26.md` archiviert.

### Docs
- Plot-Template-Promotion ueber geteilte Helper in `docs/architecture.md` dokumentiert.

## 0.2.2 - 2026-05-25

### Added
- CLI-Befehl `plot-template` fuer manuell anpassbare Diagramm-Vorlagen ergaenzt.
- Erste Vorlage `heating-year` fuer eine oder mehrere Varianten und genau einen Raum eingefuehrt.
- Neues Modul `analysis/templates/` fuer Plot-Templates und Overlay-Logik ergaenzt.
- Plot-Template-Defaults ueber `settings/plot_templates.toml` und Loader `settings.plot_templates` konfigurierbar gemacht.
- Heating-Year-Template um Aussenlufttemperatur, operative Temperatur, Sollwertband und freie Overlay-Linien aus Raum-CSV oder `REPORT-AUX.prn` erweitert.
- GUI um die Schritte `Template` und `Ueberlagerungen` fuer Plot-Templates ergaenzt.
- Rechten GUI-Bereich um einen `summary`-Kasten fuer abgeschlossene vorherige Schritte erweitert.
- Unteren GUI-Bereich um einen `log`-Button neben `settings` erweitert, der die bestehende Protokollansicht oeffnet oder ein laufendes Analyse-Logfenster fokussiert.
- Tests fuer Plot-Template-Validierung, PRN-Stundenaggregation, Overlay-Kataloge, freie Overlays, TOML-Defaults, CLI-Optionen und Logging ergaenzt.

### Changed
- GUI im Wizard-Stil ueberarbeitet: linke Schritt-Navigation, rechter Inhaltsbereich und getrennte Kaesten fuer `summary` und aktuellen Schritt.
- GUI startet ohne vorausgewaehlte sichtbare Auswahl; Pflichtauswahlen werden erst beim Start validiert.
- Aktiver GUI-Schritt wird mit kleinem Punkt markiert, ohne blaue Flaechenmarkierung.
- Nach Auswahl eines Befehls springt die GUI automatisch zum naechsten sichtbaren Schritt.
- Automatisches Weitergehen auf weitere Einzelauswahl-Schritte erweitert; bei mehrteiligen Optionen wartet die GUI bis die Pflichtauswahl vollstaendig ist.
- Drei-Punkte-Menue aus der Titelleiste entfernt; Tools-Menue wird ueber `settings` geoeffnet.
- Rechte GUI-Scrollbar wird nur eingeblendet und per Mausrad genutzt, wenn der rechte Inhalt ueber das sichtbare Feld hinausgeht.
- Temperaturachsen-Eingaben in den Schritt `Ueberlagerungen` verschoben.
- `plot-template` kann nun mehrere Varianten aus der GUI-/CLI-Auswahl verarbeiten und erzeugt pro Variante ein eigenes Template-PNG.
- Heating-Year-Plot-Layout verfeinert: X-Achse naeher am Zeitstrahl, Abstand zur Monatsbeschriftung auf ca. 5 mm gesetzt und Abstand zwischen Zeitstrahl-Beschriftung und `Stunden [h]` auf ca. 3 mm reduziert.
- Positionen von Legende und `Stunden [h]` im Heating-Year-Plot getauscht.
- Jahres-Zeitstrahl trennt Grid-Markierungen oberhalb der Hauptlinie von 1000er-Stundenticks unterhalb der Hauptlinie.
- `plot-template` in die Laufprotokollierung aufgenommen.

### Docs
- `README.md`, `docs/commands.md` und `docs/architecture.md` um `plot-template`, Plot-Template-Config und Setup-/Start-Hinweise erweitert.
- `*.toml` als Package-Daten fuer `ma_analyse.settings` aufgenommen.
- Pytest-Testpfad in `pyproject.toml` dokumentiert.

## 0.2.1 - 2026-05-25

### Changed
- Analysecode weiter modularisiert: gemeinsame Energy-Logik fuer Heating/Cooling, Tabellenpaket fuer Excel-Berichte und Comfort-Module fuer Daten, Zonen, Tabellen und Plots ergaenzt.

## 0.2.0 - 2026-05-24

### Added
- `CHANGELOG.md` als zentrale Aenderungshistorie eingefuehrt.
- Laufprotokolle mit Schritt- und Gesamtlaufzeiten fuer Analysebefehle ergaenzt.
- `data/`-Ordnerstruktur mit versionierten Platzhalterdateien vorbereitet.
- Minimale Tests fuer CLI, Konfiguration, Logging, Varianten und Zeitfenster ergaenzt.

### Changed
- Projekt von losen Skripten zu einem Paket mit `src/ma_analyse` umgebaut.
- Code fachlich in `app`, `core`, `preprocessing`, `analysis`, `analysis/components`, `gui` und `settings` strukturiert.
- CLI-Einstieg auf `python -m ma_analyse ...` und `ma-analyse ...` ausgerichtet.
- Datenordner auf `data/input`, `data/database`, `data/output` und `data/test_output` umgestellt.
- `requirements.txt` auf direkte Runtime-Abhaengigkeiten reduziert.
- GUI so angepasst, dass der `all`-Befehl automatisch alle Raeume auswaehlt.

### Removed
- Alte Skriptstruktur unter `Skripte/` als Hauptschnittstelle entfernt.
- Uebergangsmodul `pipeline.py` entfernt, nachdem CLI, Commands und GUI ausgelagert wurden.
- Alte Root-Module wie `config.py`, `commands.py`, `heating.py`, `cooling.py`, `prepare.py`, `comfort.py` und `analyze.py` durch Paketmodule ersetzt.

## 0.1.0 - 2026-05-24

### Added
- Erster Paketstand fuer `ma_analyse` mit zentralem CLI-Einstieg.

