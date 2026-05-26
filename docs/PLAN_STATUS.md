# Plan Status

Stand: 2026-05-26

Diese Hauptdatei enthaelt nur aktive, noch nicht abgeschlossene Punkte. Vollstaendige archivierte Planstaende liegen unter `docs/plan_status/`.

## Teilweise umgesetzt

- Overlays als konfigurierbare Standardlinien: Funktioniert fuer `heating-year` im Plot-Template. Es fehlt noch die bewusste Uebernahme auf Hauptfunktionen und auf weitere Template-Zeitansichten. Betroffen: `src/ma_analyse/analysis/heating.py`, `src/ma_analyse/analysis/cooling.py`, `src/ma_analyse/gui/app.py`, `src/ma_analyse/app/cli.py`.
- Jahresplot-Layout: Heating-Hauptfunktion nutzt die gemeinsame Jahreslayoutbasis. Cooling-Jahresansicht nutzt weiterhin das Cooling-spezifische technische Layout. Betroffen: `src/ma_analyse/analysis/heating.py`, `src/ma_analyse/analysis/cooling.py`, `src/ma_analyse/analysis/components/heating_year_layout.py`.
- Dokumentationspflege: `CHANGELOG.md` und `docs/PLAN_STATUS.md` sind getrennt. Neu ist das Archiv unter `docs/plan_status/`; die Routine fuer regelmaessiges Archivieren muss weiter eingehalten werden. Betroffen: `CHANGELOG.md`, `docs/PLAN_STATUS.md`, `docs/plan_status/`.
- Interne Lasten: Erste Diagrammideen sind als `plot-template` umgesetzt. Year/Month bleiben Liniendiagramme; Week/Day nutzen gestapelte Lastprofil-Balken. Sichtbar sind nur Personen, Geraete und Beleuchtung. Es fehlt noch die Entscheidung, ob daraus eine eigene Hauptfunktion, ein Unterbefehl oder ein Bestandteil von `analyze-data` werden soll. Betroffen: `src/ma_analyse/analysis/templates/internal_loads.py`, `src/ma_analyse/app/cli.py`, `src/ma_analyse/gui/app.py`.
- Energiebilanz: Erste Uebersicht ist als `plot-template` fuer Year/Month/Week/Day umgesetzt. Es fehlt noch die visuelle Pruefung mit realen Projektdaten und die Entscheidung, welche Bilanzspalten fachlich final zusammengefasst werden. Betroffen: `src/ma_analyse/analysis/templates/energy_balance.py`.
- Plot-Template-Katalog: Comfort-PNGs, Comfort-PDFs, Heating-/Cooling-Barplots und thermisches Raumklima sind als Template-Ausgaben umgesetzt. Die Beispielbild-Galerie unter `docs/examples/` wurde angelegt; `docs/plot_template_examples.md` dokumentiert die stabilen Beispielwege. Betroffen: `src/ma_analyse/analysis/templates/`, `docs/commands.md`, `docs/plot_template_examples.md`.

## Noch offen

- Overlay-Uebernahme in Hauptfunktionen planen und implementieren: zuerst klaeren, ob nur `heating --view year` oder auch Month/Week/Day und Cooling Overlays bekommen sollen. Betroffen: `src/ma_analyse/analysis/heating.py`, `src/ma_analyse/analysis/cooling.py`, `src/ma_analyse/gui/app.py`, `src/ma_analyse/app/cli.py`.
- Heating und Cooling weiter zerlegen in Datenladen, Runner und Plotmodule. Betroffen: `src/ma_analyse/analysis/heating.py`, `src/ma_analyse/analysis/cooling.py`, `src/ma_analyse/analysis/energy/`.
- Comfort-Runner bei weiterem Wachstum verkleinern. Betroffen: `src/ma_analyse/analysis/comfort/`.
- GUI weiter in kleinere Komponenten fuer Layout, Dialoge, Auswahl- und Laufsteuerung aufteilen. Betroffen: `src/ma_analyse/gui/app.py`.
- Cooling-Jahreslayout entscheiden: Soll Cooling ebenfalls eine eigene gemeinsame Template-Layoutbasis bekommen oder bewusst beim aktuellen technischen Layout bleiben?
- Internal-Loads-Templates mit realen Projektdaten visuell pruefen und entscheiden, welche Variante wissenschaftlich in die Hauptauswertung uebernommen wird.
- Fuer spezifische interne Lasten `[W/m²]` klaeren, wo die Raumflaechen hinterlegt werden sollen. Aktuell plotten die Templates absolute Leistung `[W]`.
- Thermische Raumklima-Templates sind als festes Overlay-Experiment umgesetzt; die Leistungsachse verwendet derzeit bewusst `[W]` wegen fehlender Raumflaechen.
- Energiebilanz-Templates mit realen Projektdaten visuell pruefen und ggf. Spaltenmapping fuer Huelle, Lueftung, Infiltration, Fenster/Solar und Innenmassen fachlich schaerfen.
- Beispielbild-Galerie fuer alle Plot-Template-Befehle anlegen und bei geaendertem Aussehen reproduzierbar ersetzen. Betroffen: `docs/examples/`, `docs/plot_template_examples.md`.

## Unklare Punkte

- Welche Overlays sollen spaeter in die Hauptfunktionen uebernommen werden: nur feste Standard-Overlays oder auch freie Nutzer-Overlays?
- Sollen Overlay-Optionen in der GUI fuer Hauptfunktionen sichtbar werden, oder nur ueber CLI/Config steuerbar sein?
- Soll aus den Internal-Loads-Templates spaeter ein eigener Befehl `internal-loads` entstehen oder sollen die Diagramme in bestehende Energie-/Excel-Auswertungen integriert werden?
- Soll die Energiebilanz spaeter absolute Leistung `[W]` behalten oder auf spezifische Leistung `[W/m²]` umgerechnet werden?

## Kommentare und Hinweise

- Versionierung am 2026-05-26 geklaert: Aktueller Paketstand ist `0.3.1`. `CHANGELOG.md` trennt `0.2.3` fuer Aenderungen vor `internal-loads-*` und `0.3.0` fuer Internal-Loads- sowie darauf folgende Template-Erweiterungen.

## Archiv

- `docs/plan_status/2026-05-26.md`: Vollstand vor der Reduktion der Hauptdatei auf aktive offene Punkte.
