from pathlib import Path

import pandas as pd
import pytest

from ma_analyse.analysis.components.time_windows import (
    MONTH_BOUNDARIES,
    MONTH_START_HOURS,
    build_energy_time_axis_config,
)
from ma_analyse.analysis.templates import (
    build_heating_year_template,
    build_plot_template,
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
    assert "Dieses plot-template erwartet genau einen Raum." in errors
    assert "setpoint-min muss kleiner als setpoint-max sein." in errors


def test_validate_template_request_requires_time_selection_for_filtered_templates():
    month_errors = validate_template_request(
        "heating-month",
        ["Dimensionierung"],
        ["101 lobby"],
        21,
        26,
        -20,
        40,
    )
    week_errors = validate_template_request(
        "cooling-week",
        ["Dimensionierung"],
        ["101 lobby"],
        21,
        26,
        -20,
        40,
    )
    day_errors = validate_template_request(
        "cooling-day",
        ["Dimensionierung"],
        ["101 lobby"],
        21,
        26,
        -20,
        40,
        month="Feb",
    )

    assert "plot-template month erwartet --month." in month_errors
    assert "plot-template week erwartet --week." in week_errors
    assert "plot-template day erwartet --day." in day_errors


def test_validate_template_request_allows_multiple_rooms_for_internal_room_comparison():
    errors = validate_template_request(
        "internal-loads-room-comparison",
        ["Dimensionierung"],
        ["101 lobby", "109 office"],
        21,
        26,
        -20,
        40,
    )

    assert errors == []


def test_validate_template_request_allows_multiple_rooms_for_overview_and_bar_templates():
    for template in ["comfort-plot-overview", "comfort-analysis-overview", "heating-bar", "cooling-bar"]:
        errors = validate_template_request(
            template,
            ["Dimensionierung"],
            ["101 lobby", "109 office"],
            21,
            26,
            -20,
            40,
        )

        assert errors == []


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


@pytest.mark.parametrize(
    ("template", "expected_name", "kwargs"),
    [
        ("heating-month", "101_lobby_heating_month_template.png", {"month": "Jan"}),
        ("heating-week", "101_lobby_heating_week_template.png", {"week": 7}),
        ("heating-day", "101_lobby_heating_day_template.png", {"month": "Feb", "day": 15}),
        ("cooling-year", "101_lobby_cooling_year_template.png", {}),
        ("cooling-month", "101_lobby_cooling_month_template.png", {"month": "Jan"}),
        ("cooling-week", "101_lobby_cooling_week_template.png", {"week": 7}),
        ("cooling-day", "101_lobby_cooling_day_template.png", {"month": "Feb", "day": 15}),
    ],
)
def test_build_plot_template_creates_timeline_pngs(tmp_path, template, expected_name, kwargs):
    datenbank_dir = tmp_path / "database"
    output_root = tmp_path / "output"
    variant_database = datenbank_dir / "Dimensionierung_nutzdaten"
    variant_database.mkdir(parents=True)

    hours = list(range(1200))
    pd.DataFrame(
        {
            "time": hours,
            "zone_energy_q_heat": [1000 if hour % 24 < 12 else 0 for hour in hours],
            "zone_energy_q_cool": [700 if 10 <= hour % 24 < 18 else 0 for hour in hours],
        }
    ).to_csv(variant_database / "101_lobby.csv", index=False)

    output_file = build_plot_template(
        datenbank_dir=datenbank_dir,
        output_root=output_root,
        selected_variants=["Dimensionierung"],
        rooms=["101 lobby"],
        template=template,
        run_id="timeline-templates",
        **kwargs,
    )

    output_path = Path(output_file)
    assert output_path.exists()
    assert output_path.stat().st_size > 1000
    assert output_path.parts[-4:] == (
        "PlotTemplates",
        "timeline-templates",
        "Dimensionierung",
        expected_name,
    )


@pytest.mark.parametrize(
    ("template", "expected_name", "kwargs"),
    [
        ("energy-balance-year", "101_lobby_energy_balance_year_template.png", {}),
        ("energy-balance-month", "101_lobby_energy_balance_month_template.png", {"month": "Jan"}),
        ("energy-balance-week", "101_lobby_energy_balance_week_template.png", {"week": 7}),
        ("energy-balance-day", "101_lobby_energy_balance_day_template.png", {"month": "Feb", "day": 15}),
    ],
)
def test_build_plot_template_creates_energy_balance_pngs(tmp_path, template, expected_name, kwargs):
    datenbank_dir = tmp_path / "database"
    input_dir = tmp_path / "input"
    output_root = tmp_path / "output"
    variant_database = datenbank_dir / "Dimensionierung_nutzdaten"
    variant_input = input_dir / "Dimensionierung"
    variant_database.mkdir(parents=True)
    variant_input.mkdir(parents=True)

    hours = list(range(1200))
    pd.DataFrame(
        {
            "time": hours,
            "zone_energy_q_heat": [600 if hour % 24 < 7 else 0 for hour in hours],
            "zone_energy_qventil": [-80 if hour % 24 < 6 else 120 for hour in hours],
            "zone_energy_q_light": [90 if 7 <= hour % 24 < 19 else 0 for hour in hours],
            "zone_energy_qwcb": [-160 + (hour % 24) * 4 for hour in hours],
            "zone_energy_ql_a": [-50 if hour % 24 < 8 else 20 for hour in hours],
            "zone_energy_q_cool": [-350 if 12 <= hour % 24 < 18 else 0 for hour in hours],
            "zone_energy_qintw": [-120 if hour % 24 < 10 else 180 for hour in hours],
            "zone_energy_q_occ": [70 if 8 <= hour % 24 < 17 else 0 for hour in hours],
            "zone_energy_qwind": [240 if 9 <= hour % 24 < 16 else -20 for hour in hours],
            "zone_energy_q_equip": [60 if 6 <= hour % 24 < 22 else 15 for hour in hours],
            "temperatures_tairmean": [21 + (hour % 24) * 0.2 for hour in hours],
        }
    ).to_csv(variant_database / "101_lobby.csv", index=False)
    report_lines = ["# time order tair tout"]
    for hour in hours:
        report_lines.append(f"{hour}.0 1.0 {5 + (hour % 24) * 0.5} {4 + (hour % 24) * 0.4}")
    (variant_input / "REPORT-AUX.prn").write_text("\n".join(report_lines), encoding="utf-8")

    output_file = build_plot_template(
        datenbank_dir=datenbank_dir,
        input_dir=input_dir,
        output_root=output_root,
        selected_variants=["Dimensionierung"],
        rooms=["101 lobby"],
        template=template,
        run_id="energy-balance",
        **kwargs,
    )

    output_path = Path(output_file)
    assert output_path.exists()
    assert output_path.stat().st_size > 1000
    assert output_path.parts[-4:] == (
        "PlotTemplates",
        "energy-balance",
        "Dimensionierung",
        expected_name,
    )


@pytest.mark.parametrize(
    ("template", "expected_name", "kwargs"),
    [
        ("internal-loads-year", "101_lobby_internal_loads_year_template.png", {}),
        ("internal-loads-month", "101_lobby_internal_loads_month_template.png", {"month": "Jan"}),
        ("internal-loads-week", "101_lobby_internal_loads_week_template.png", {"week": 7}),
        ("internal-loads-day", "101_lobby_internal_loads_day_template.png", {"month": "Feb", "day": 15}),
        ("internal-loads-monthly-sum", "101_lobby_internal_loads_monthly_sum_template.png", {}),
    ],
)
def test_build_plot_template_creates_internal_loads_single_room_pngs(tmp_path, template, expected_name, kwargs):
    datenbank_dir = tmp_path / "database"
    output_root = tmp_path / "output"
    variant_database = datenbank_dir / "Dimensionierung_nutzdaten"
    variant_database.mkdir(parents=True)

    hours = list(range(1200))
    pd.DataFrame(
        {
            "time": hours,
            "zone_energy_q_light": [120 if 7 <= hour % 24 < 19 else 0 for hour in hours],
            "zone_energy_q_occ": [80 if 8 <= hour % 24 < 17 else 0 for hour in hours],
            "zone_energy_q_equip": [60 if 6 <= hour % 24 < 22 else 15 for hour in hours],
        }
    ).to_csv(variant_database / "101_lobby.csv", index=False)

    output_file = build_plot_template(
        datenbank_dir=datenbank_dir,
        output_root=output_root,
        selected_variants=["Dimensionierung"],
        rooms=["101 lobby"],
        template=template,
        run_id="internal-loads",
        **kwargs,
    )

    output_path = Path(output_file)
    assert output_path.exists()
    assert output_path.stat().st_size > 1000
    assert output_path.parts[-4:] == (
        "PlotTemplates",
        "internal-loads",
        "Dimensionierung",
        expected_name,
    )


def test_build_plot_template_creates_internal_loads_room_comparison_png(tmp_path):
    datenbank_dir = tmp_path / "database"
    output_root = tmp_path / "output"
    variant_database = datenbank_dir / "Dimensionierung_nutzdaten"
    variant_database.mkdir(parents=True)

    hours = list(range(48))
    for room_stub, offset in [("101_lobby", 0), ("109_office", 30)]:
        pd.DataFrame(
            {
                "time": hours,
                "zone_energy_q_light": [100 + offset if 7 <= hour % 24 < 19 else 0 for hour in hours],
                "zone_energy_q_occ": [70 + offset if 8 <= hour % 24 < 17 else 0 for hour in hours],
                "zone_energy_q_equip": [50 + offset for _ in hours],
            }
        ).to_csv(variant_database / f"{room_stub}.csv", index=False)

    output_file = build_plot_template(
        datenbank_dir=datenbank_dir,
        output_root=output_root,
        selected_variants=["Dimensionierung"],
        rooms=["101 lobby", "109 office"],
        template="internal-loads-room-comparison",
        run_id="internal-loads-rooms",
    )

    output_path = Path(output_file)
    assert output_path.exists()
    assert output_path.stat().st_size > 1000
    assert output_path.parts[-4:] == (
        "PlotTemplates",
        "internal-loads-rooms",
        "Dimensionierung",
        "internal_loads_room_comparison_template.png",
    )


@pytest.mark.parametrize(
    ("template", "expected_name", "rooms"),
    [
        ("comfort-plot", "101_lobby_comfort_plot_template.png", ["101 lobby"]),
        ("comfort-analysis", "101_lobby_comfort_analysis_template.png", ["101 lobby"]),
        ("comfort-plot-overview", "comfort_plot_overview_template.pdf", ["101 lobby", "109 office"]),
        ("comfort-analysis-overview", "comfort_analysis_overview_template.pdf", ["101 lobby", "109 office"]),
    ],
)
def test_build_plot_template_creates_comfort_outputs(tmp_path, template, expected_name, rooms):
    datenbank_dir = tmp_path / "database"
    output_root = tmp_path / "output"
    variant_database = datenbank_dir / "Dimensionierung_nutzdaten"
    variant_database.mkdir(parents=True)

    hours = list(range(48))
    for room_stub, offset in [("101_lobby", 0), ("109_office", 1)]:
        pd.DataFrame(
            {
                "time": hours,
                "local_de_comf_diag_t_top": [21 + offset + (hour % 24) * 0.05 for hour in hours],
                "iaq_relhum": [45 + (hour % 24) * 0.2 for hour in hours],
            }
        ).to_csv(variant_database / f"{room_stub}.csv", index=False)

    output_file = build_plot_template(
        datenbank_dir=datenbank_dir,
        output_root=output_root,
        selected_variants=["Dimensionierung"],
        rooms=rooms,
        template=template,
        run_id="comfort-templates",
    )

    output_path = Path(output_file)
    assert output_path.exists()
    assert output_path.stat().st_size > 1000
    assert output_path.parts[-4:] == (
        "PlotTemplates",
        "comfort-templates",
        "Dimensionierung",
        expected_name,
    )


@pytest.mark.parametrize(
    ("template", "expected_name"),
    [
        ("heating-bar", "heating_bar_template.png"),
        ("cooling-bar", "cooling_bar_template.png"),
    ],
)
def test_build_plot_template_creates_barplot_pngs(tmp_path, template, expected_name):
    datenbank_dir = tmp_path / "database"
    output_root = tmp_path / "output"
    variant_database = datenbank_dir / "Dimensionierung_nutzdaten"
    variant_database.mkdir(parents=True)

    hours = list(range(48))
    for room_stub, offset in [("101_lobby", 0), ("109_office", 100)]:
        pd.DataFrame(
            {
                "time": hours,
                "zone_energy_q_heat": [400 + offset if hour % 24 < 12 else 20 for hour in hours],
                "zone_energy_q_cool": [300 + offset if 10 <= hour % 24 < 18 else 0 for hour in hours],
            }
        ).to_csv(variant_database / f"{room_stub}.csv", index=False)

    output_file = build_plot_template(
        datenbank_dir=datenbank_dir,
        output_root=output_root,
        selected_variants=["Dimensionierung"],
        rooms=["101 lobby", "109 office"],
        template=template,
        run_id="bar-templates",
    )

    output_path = Path(output_file)
    assert output_path.exists()
    assert output_path.stat().st_size > 1000
    assert output_path.parts[-4:] == (
        "PlotTemplates",
        "bar-templates",
        "Dimensionierung",
        expected_name,
    )


@pytest.mark.parametrize(
    ("template", "expected_name", "kwargs"),
    [
        ("thermal-room-climate-year", "101_lobby_thermal_room_climate_year_template.png", {}),
        ("thermal-room-climate-month", "101_lobby_thermal_room_climate_month_template.png", {"month": "Jan"}),
        ("thermal-room-climate-week", "101_lobby_thermal_room_climate_week_template.png", {"week": 7}),
        (
            "thermal-room-climate-day",
            "101_lobby_thermal_room_climate_day_template.png",
            {"month": "Feb", "day": 15},
        ),
    ],
)
def test_build_plot_template_creates_thermal_room_climate_pngs(tmp_path, template, expected_name, kwargs):
    datenbank_dir = tmp_path / "database"
    input_dir = tmp_path / "input"
    output_root = tmp_path / "output"
    variant_database = datenbank_dir / "Dimensionierung_nutzdaten"
    variant_input = input_dir / "Dimensionierung"
    variant_database.mkdir(parents=True)
    variant_input.mkdir(parents=True)

    hours = list(range(1200))
    pd.DataFrame(
        {
            "time": hours,
            "zone_energy_q_light": [120 if 7 <= hour % 24 < 19 else 0 for hour in hours],
            "zone_energy_q_occ": [80 if 8 <= hour % 24 < 17 else 0 for hour in hours],
            "zone_energy_q_equip": [60 if 6 <= hour % 24 < 22 else 15 for hour in hours],
            "zone_energy_qventil": [-80 if hour % 24 < 6 else 120 for hour in hours],
            "zone_energy_q_cool": [280 if 12 <= hour % 24 < 18 else 0 for hour in hours],
            "temperatures_tairmean": [21 + (hour % 24) * 0.15 for hour in hours],
        }
    ).to_csv(variant_database / "101_lobby.csv", index=False)
    report_lines = ["# time order tair tout"]
    for hour in hours:
        report_lines.append(f"{hour}.0 1.0 {6 + (hour % 24) * 0.6} {5 + (hour % 24) * 0.4}")
    (variant_input / "REPORT-AUX.prn").write_text("\n".join(report_lines), encoding="utf-8")

    output_file = build_plot_template(
        datenbank_dir=datenbank_dir,
        input_dir=input_dir,
        output_root=output_root,
        selected_variants=["Dimensionierung"],
        rooms=["101 lobby"],
        template=template,
        run_id="thermal-room-climate",
        **kwargs,
    )

    output_path = Path(output_file)
    assert output_path.exists()
    assert output_path.stat().st_size > 1000
    assert output_path.parts[-4:] == (
        "PlotTemplates",
        "thermal-room-climate",
        "Dimensionierung",
        expected_name,
    )


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


def test_build_heating_year_template_uses_configured_fixed_overlays(tmp_path):
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
            "custom_operativ": [21.0 + (hour % 24) * 0.05 for hour in hours],
        }
    ).to_csv(variant_database / "101_lobby.csv", index=False)
    report_lines = ["# time order tamb"]
    for hour in hours:
        report_lines.append(f"{hour}.0 1.0 {4 + hour * 0.1}")
    (variant_input / "REPORT-AUX.prn").write_text("\n".join(report_lines), encoding="utf-8")

    fixed_overlays = [
        {
            "id": "outdoor_temperature",
            "label": "Aussenluft konfiguriert",
            "source": "aux",
            "column": "tamb",
            "axis": "temperature",
            "enabled": True,
        },
        {
            "id": "operative_temperature",
            "label": "Operativ konfiguriert",
            "source": "csv",
            "column": "custom_operativ",
            "axis": "temperature",
            "enabled": True,
        },
    ]

    output_file = build_heating_year_template(
        datenbank_dir=datenbank_dir,
        input_dir=input_dir,
        output_root=output_root,
        selected_variants=["Dimensionierung"],
        rooms=["101 lobby"],
        outdoor_column="tair",
        fixed_overlays=fixed_overlays,
        run_id="fixed-overlays",
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
