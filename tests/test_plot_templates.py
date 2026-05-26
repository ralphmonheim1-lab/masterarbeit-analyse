from pathlib import Path

import pandas as pd

from ma_analyse.analysis.components.time_windows import (
    MONTH_BOUNDARIES,
    MONTH_START_HOURS,
    build_energy_time_axis_config,
)
from ma_analyse.analysis.templates import (
    build_heating_year_template,
    list_heating_year_overlay_sources,
    load_hourly_prn_series,
    validate_template_request,
)
from ma_analyse.settings.plot_templates import get_heating_year_template_defaults


def test_validate_template_request_requires_variant_and_single_room():
    errors = validate_template_request(
        "heating-year",
        [],
        ["101 lobby", "109 office"],
        26,
        21,
        -20,
        40,
    )

    assert "plot-template erwartet mindestens eine Variante." in errors
    assert "plot-template erwartet genau einen Raum." in errors
    assert "setpoint-min muss kleiner als setpoint-max sein." in errors


def test_load_hourly_prn_series_aggregates_subhourly_values(tmp_path):
    prn_file = tmp_path / "REPORT-AUX.prn"
    prn_file.write_text(
        "\n".join(
            [
                "#      time         order        tair",
                "0.0 1.0 6.0",
                "0.5 1.0 8.0",
                "1.0 1.0 10.0",
                "1.5 1.0 14.0",
            ]
        ),
        encoding="utf-8",
    )

    result = load_hourly_prn_series(prn_file, "tair")

    assert result.to_dict("records") == [
        {"time": 0, "tair": 7.0},
        {"time": 1, "tair": 12.0},
    ]


def test_heating_year_axis_config_separates_grid_and_1000h_ticks():
    axis_config = build_energy_time_axis_config("year")

    assert axis_config["grid_ticks"] == [0] + MONTH_START_HOURS[1:] + [MONTH_BOUNDARIES[-1]]
    assert axis_config["ticks"] == list(range(0, 9000, 1000))
    assert MONTH_BOUNDARIES[-1] in axis_config["grid_ticks"]
    assert MONTH_BOUNDARIES[-1] not in axis_config["ticks"]


def test_build_heating_year_template_creates_png(tmp_path):
    datenbank_dir = tmp_path / "database"
    input_dir = tmp_path / "input"
    output_root = tmp_path / "output"
    variant_database = datenbank_dir / "Dimensionierung_nutzdaten"
    variant_input = input_dir / "Dimensionierung"
    variant_database.mkdir(parents=True)
    variant_input.mkdir(parents=True)

    hours = list(range(48))
    room_df = pd.DataFrame(
        {
            "time": hours,
            "zone_energy_q_heat": [1000 if hour < 12 else 0 for hour in hours],
            "temperatures_tairmean": [20.0 + (hour % 24) * 0.03 for hour in hours],
            "temperatures_top": [21.0 + (hour % 24) * 0.05 for hour in hours],
        }
    )
    room_df.to_csv(variant_database / "101_lobby.csv", index=False)

    report_lines = ["#      time         order        tair        tout"]
    for hour in hours:
        report_lines.append(f"{hour}.0 1.0 {5 + hour * 0.1} {3 + hour * 0.2}")
    (variant_input / "REPORT-AUX.prn").write_text("\n".join(report_lines), encoding="utf-8")

    output_file = build_heating_year_template(
        datenbank_dir=datenbank_dir,
        input_dir=input_dir,
        output_root=output_root,
        selected_variants=["Dimensionierung"],
        rooms=["101 lobby"],
        run_id="test-run",
    )

    output_path = Path(output_file)
    assert output_path.exists()
    assert output_path.stat().st_size > 1000
    assert output_path.parts[-4:] == (
        "PlotTemplates",
        "test-run",
        "Dimensionierung",
        "101_lobby_heating_year_template.png",
    )


def test_build_heating_year_template_creates_png_for_multiple_variants(tmp_path):
    datenbank_dir = tmp_path / "database"
    input_dir = tmp_path / "input"
    output_root = tmp_path / "output"
    hours = list(range(48))

    for variant_name, heat_offset in [("Dimensionierung", 0), ("Variante A", 100)]:
        variant_database = datenbank_dir / f"{variant_name}_nutzdaten"
        variant_input = input_dir / variant_name
        variant_database.mkdir(parents=True)
        variant_input.mkdir(parents=True)

        pd.DataFrame(
            {
                "time": hours,
                "zone_energy_q_heat": [1000 + heat_offset if hour < 12 else 0 for hour in hours],
                "temperatures_top": [21.0 + (hour % 24) * 0.05 for hour in hours],
            }
        ).to_csv(variant_database / "101_lobby.csv", index=False)

        report_lines = ["#      time         order        tair"]
        for hour in hours:
            report_lines.append(f"{hour}.0 1.0 {5 + hour * 0.1}")
        (variant_input / "REPORT-AUX.prn").write_text("\n".join(report_lines), encoding="utf-8")

    output_files = build_heating_year_template(
        datenbank_dir=datenbank_dir,
        input_dir=input_dir,
        output_root=output_root,
        selected_variants=["Dimensionierung", "Variante A"],
        rooms=["101 lobby"],
        run_id="multi-variants",
    )

    assert isinstance(output_files, list)
    assert len(output_files) == 2
    for output_file in output_files:
        output_path = Path(output_file)
        assert output_path.exists()
        assert output_path.stat().st_size > 1000


def test_heating_year_overlay_catalog_lists_csv_and_aux_columns(tmp_path):
    datenbank_dir = tmp_path / "database"
    input_dir = tmp_path / "input"
    variant_database = datenbank_dir / "Dimensionierung_nutzdaten"
    variant_input = input_dir / "Dimensionierung"
    variant_database.mkdir(parents=True)
    variant_input.mkdir(parents=True)

    pd.DataFrame(
        {
            "time": [0, 1],
            "room": ["101 lobby", "101 lobby"],
            "zone_energy_order": [1, 1],
            "zone_energy_q_heat": [100, 120],
            "temperatures_top": [21, 22],
            "iaq_relhum": [40, 41],
        }
    ).to_csv(variant_database / "101_lobby.csv", index=False)
    (variant_input / "REPORT-AUX.prn").write_text(
        "\n".join(["# time order tair tout", "0 1 5 3", "1 1 6 4"]),
        encoding="utf-8",
    )

    catalog = list_heating_year_overlay_sources(datenbank_dir, input_dir, "Dimensionierung", "101 lobby")

    assert "temperatures_top" in catalog["csv"]
    assert "iaq_relhum" in catalog["csv"]
    assert "zone_energy_order" not in catalog["csv"]
    assert "zone_energy_q_heat" not in catalog["csv"]
    assert "tout" in catalog["aux"]
    assert "tair" not in catalog["aux"]


def test_build_heating_year_template_accepts_free_csv_and_aux_overlays(tmp_path):
    datenbank_dir = tmp_path / "database"
    input_dir = tmp_path / "input"
    output_root = tmp_path / "output"
    variant_database = datenbank_dir / "Dimensionierung_nutzdaten"
    variant_input = input_dir / "Dimensionierung"
    variant_database.mkdir(parents=True)
    variant_input.mkdir(parents=True)

    hours = list(range(48))
    pd.DataFrame(
        {
            "time": hours,
            "zone_energy_q_heat": [1000 if hour < 12 else 0 for hour in hours],
            "zone_energy_q_occ": [50 + hour for hour in hours],
            "temperatures_top": [21.0 + (hour % 24) * 0.05 for hour in hours],
            "temperatures_tairmean": [20.0 + (hour % 24) * 0.04 for hour in hours],
        }
    ).to_csv(variant_database / "101_lobby.csv", index=False)
    report_lines = ["#      time         order        tair        tout"]
    for hour in hours:
        report_lines.append(f"{hour}.0 1.0 {5 + hour * 0.1} {3 + hour * 0.2}")
    (variant_input / "REPORT-AUX.prn").write_text("\n".join(report_lines), encoding="utf-8")

    output_file = build_heating_year_template(
        datenbank_dir=datenbank_dir,
        input_dir=input_dir,
        output_root=output_root,
        selected_variants=["Dimensionierung"],
        rooms=["101 lobby"],
        overlay_lines=[
            {
                "source": "csv",
                "column": "temperatures_tairmean",
                "label": "Raumlufttemperatur",
                "axis": "temperature",
            },
            {
                "source": "aux",
                "column": "tout",
                "label": "Außentemperatur tout",
                "axis": "temperature",
            },
            {
                "source": "csv",
                "column": "zone_energy_q_occ",
                "label": "Personenlast",
                "axis": "heat",
            },
        ],
        run_id="free-overlays",
    )

    output_path = Path(output_file)
    assert output_path.exists()
    assert output_path.stat().st_size > 1000


def test_plot_template_defaults_are_loaded_from_toml(tmp_path):
    config_file = tmp_path / "plot_templates.toml"
    config_file.write_text(
        "\n".join(
            [
                "[heating_year]",
                "setpoint_min = 20.0",
                "setpoint_max = 25.0",
                "temperature_ymin = -15.0",
                "temperature_ymax = 35.0",
                "show_setpoint_band = false",
                "show_outdoor_temperature = true",
                "show_operative_temperature = false",
                'outdoor_column = "tout"',
            ]
        ),
        encoding="utf-8",
    )

    defaults = get_heating_year_template_defaults(config_file)

    assert defaults["setpoint_min"] == 20
    assert defaults["setpoint_max"] == 25
    assert defaults["temperature_ymin"] == -15
    assert defaults["temperature_ymax"] == 35
    assert defaults["show_setpoint_band"] is False
    assert defaults["show_operative_temperature"] is False
    assert defaults["outdoor_column"] == "tout"
