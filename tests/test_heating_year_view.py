from pathlib import Path

import pandas as pd

from ma_analyse.analysis import heating
from ma_analyse.analysis.components.heating_year_layout import draw_heating_year_line_plot


def test_draw_heating_year_line_plot_creates_png(tmp_path):
    plot_df = pd.DataFrame(
        {
            "time": list(range(48)),
            "series": ["Heizleistung"] * 48,
            "q_heat": [1000 if hour < 12 else 0 for hour in range(48)],
        }
    )
    output_file = tmp_path / "heating_year.png"

    draw_heating_year_line_plot(
        plot_df,
        x_col="time",
        group_col="series",
        title="Heating Jahresansicht - Dimensionierung / 101 lobby",
        subtitle="Von 01.01.2025 bis 31.12.2025",
        output_file=output_file,
        single_series_legend_label="Heizleistung",
    )

    assert output_file.exists()
    assert output_file.stat().st_size > 1000


def test_heating_year_single_room_routes_to_template_style_renderer(monkeypatch, tmp_path):
    calls = {}

    def fake_draw_heating_year_line_plot(
        plot_df,
        x_col,
        group_col,
        title,
        subtitle,
        output_file,
        line_colors=None,
        single_series_legend_label=None,
    ):
        calls.update(
            {
                "plot_df": plot_df,
                "x_col": x_col,
                "group_col": group_col,
                "title": title,
                "subtitle": subtitle,
                "output_file": Path(output_file),
                "line_colors": line_colors,
                "single_series_legend_label": single_series_legend_label,
            }
        )
        Path(output_file).write_bytes(b"png")

    monkeypatch.setattr(heating, "draw_heating_year_line_plot", fake_draw_heating_year_line_plot)
    room_df = pd.DataFrame({"time": [0, 1, 2], "zone_energy_q_heat": [100, 200, 0]})

    count = heating.plot_single_room_time_series(
        room_df,
        variant_name="Dimensionierung",
        room="101 lobby",
        output_dir=tmp_path,
        view="year",
    )

    assert count == 1
    assert calls["x_col"] == "time_axis"
    assert calls["group_col"] == "series"
    assert calls["title"] == "Heating Jahresansicht - Dimensionierung / 101 lobby"
    assert calls["subtitle"] == "Von 01.01.2025 bis 31.12.2025"
    assert calls["single_series_legend_label"] == "Heizleistung"
    assert calls["plot_df"]["q_heat"].to_list() == [100, 200, 0]


def test_heating_year_variant_room_plot_routes_to_template_style_renderer(monkeypatch, tmp_path):
    calls = {}

    def fake_draw_heating_year_line_plot(
        plot_df,
        x_col,
        group_col,
        title,
        subtitle,
        output_file,
        line_colors=None,
        single_series_legend_label=None,
    ):
        calls.update(
            {
                "plot_df": plot_df,
                "x_col": x_col,
                "group_col": group_col,
                "title": title,
                "subtitle": subtitle,
                "output_file": Path(output_file),
                "line_colors": line_colors,
                "single_series_legend_label": single_series_legend_label,
            }
        )
        Path(output_file).write_bytes(b"png")

    monkeypatch.setattr(heating, "draw_heating_year_line_plot", fake_draw_heating_year_line_plot)
    room_data = {
        "101 lobby": pd.DataFrame({"time": [0, 1], "zone_energy_q_heat": [100, 200]}),
        "102 office": pd.DataFrame({"time": [0, 1], "zone_energy_q_heat": [300, 400]}),
    }

    count = heating.plot_yearly_single_variant(room_data, "Dimensionierung", tmp_path)

    assert count == 1
    assert calls["x_col"] == "time"
    assert calls["group_col"] == "room"
    assert calls["title"] == "Heating Jahresansicht - Dimensionierung"
    assert calls["subtitle"] == "Von 01.01.2025 bis 31.12.2025"
    assert calls["single_series_legend_label"] is None
    assert calls["plot_df"]["room"].to_list() == ["101 lobby", "101 lobby", "102 office", "102 office"]


def test_heating_month_single_room_keeps_standard_renderer(monkeypatch, tmp_path):
    calls = {}

    def fail_year_renderer(*args, **kwargs):
        raise AssertionError("month view must not use the heating-year renderer")

    def fake_draw_technical_line_plot(plot_df, x_col, group_col, title, subtitle, axis_config, output_file):
        calls.update(
            {
                "plot_df": plot_df,
                "x_col": x_col,
                "group_col": group_col,
                "title": title,
                "subtitle": subtitle,
                "axis_config": axis_config,
                "output_file": Path(output_file),
            }
        )
        Path(output_file).write_bytes(b"png")

    monkeypatch.setattr(heating, "draw_heating_year_line_plot", fail_year_renderer)
    monkeypatch.setattr(heating, "draw_technical_line_plot", fake_draw_technical_line_plot)
    room_df = pd.DataFrame({"time": [0, 1, 24, 25], "zone_energy_q_heat": [100, 200, 300, 400]})

    count = heating.plot_single_room_time_series(
        room_df,
        variant_name="Dimensionierung",
        room="101 lobby",
        output_dir=tmp_path,
        view="month",
        month_name="Jan",
    )

    assert count == 1
    assert calls["x_col"] == "time_axis"
    assert calls["group_col"] == "series"
    assert calls["title"] == "Heizlastverlauf - Dimensionierung - 101 lobby"
    assert calls["subtitle"] == "Zeitraum: Monat Jan"
