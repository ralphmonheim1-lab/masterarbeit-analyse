# Zentrale Ausgabeformate

Dieses Dokument steuert die Standardgroessen fuer erzeugte Diagramme, PDFs und Excel-Ausgaben.

Regeln:
- Aendere in der Tabelle `Ausgabe-Regeln` die Spalte `Format`.
- Erlaubte Werte stehen unten im `Formatkatalog`.
- Diagrammgroessen werden in Zentimetern angegeben und intern fuer Matplotlib umgerechnet.
- `Keine Größe` wird fuer Ausgaben ohne feste Bild- oder Seitengroesse verwendet.

## Ausgabe-Regeln

| ID | Befehl | Unterbefehl | Ausgabe | Format |
| --- | --- | --- | --- | --- |
| comfort.plot.png | comfort | plot | Einzelraum-Komfortdiagramm | 16x9 cm |
| comfort.plot_analysis.png | comfort | plot_analysis | Einzelraum-Analyse-Diagramm | 16x9 cm |
| comfort.plot_overview.pdf | comfort | plot_overview | Comfort-Uebersicht PDF | A4 Quer |
| comfort.plot_analysis_overview.pdf | comfort | plot_analysis_overview | Analyse-Uebersicht PDF | A4 Quer |
| heating.bar.png | heating | bar | Heating Balkendiagramm | 16x9 cm |
| heating.timeline.single.png | heating | timeline | Heating Zeitdiagramm single | 24x13.5 cm |
| heating.timeline.compare.png | heating | timeline | Heating Zeitdiagramm compare | 24x13.5 cm |
| cooling.bar.png | cooling | bar | Cooling Balkendiagramm | 16x9 cm |
| cooling.timeline.single.png | cooling | timeline | Cooling Zeitdiagramm single | 16x9 cm |
| cooling.timeline.compare.png | cooling | timeline | Cooling Zeitdiagramm compare | 24x13.5 cm |
| internal-loads.year.png | plot-template | internal-loads-year | Internal Loads Jahresverlauf | 12.8x7.2 cm |
| internal-loads.timeline.png | plot-template | internal-loads-month/week/day | Internal Loads Zeitverlauf | 12.8x7.2 cm |
| internal-loads.profile.png | plot-template | internal-loads-month/week/day | Internal Loads Profil | 12.8x7.2 cm |
| internal-loads.monthly-sum.png | plot-template | internal-loads-monthly-sum | Internal Loads Monatssummen | 11.6x6.6 cm |
| internal-loads.room-comparison.png | plot-template | internal-loads-room-comparison | Internal Loads Raumvergleich | 11.8x6.6 cm |
| energy-balance.template.png | plot-template | energy-balance | Energiebilanz Zeitdiagramm | 12.8x7.2 cm |
| thermal-room-climate.template.png | plot-template | thermal-room-climate | Raumklima-Zeitdiagramm | 12.8x7.2 cm |
| analyze_data.excel | analyze_data | - | Excel-Auswertung | Keine Größe |

## Formatkatalog

| Format | Breite cm | Hoehe cm | Verwendung |
| --- | ---: | ---: | --- |
| 16x9 cm | 16 | 9 | Standard fuer Einzel-Diagramme |
| 24x13.5 cm | 24 | 13.5 | Mehr Platz fuer Vergleichsdiagramme |
| 12.8x7.2 cm | 12.8 | 7.2 | Kompaktes 16:9-Format fuer Plot-Templates |
| 11.6x6.6 cm | 11.6 | 6.6 | Kompakter Balkendiagramm-Output |
| 11.8x6.6 cm | 11.8 | 6.6 | Kompakter Raumvergleichs-Output |
| A4 Hoch | 21 | 29.7 | PDF-Seite im Hochformat |
| A4 Quer | 29.7 | 21 | PDF-Seite im Querformat |
| Keine Größe |  |  | Fuer Ausgaben ohne feste Bildgroesse |


