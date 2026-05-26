from ma_analyse.app.cli import build_parser


def test_cli_parser_accepts_main_commands():
    parser = build_parser()

    assert parser.parse_args(["prepare"]).command == "prepare"
    assert parser.parse_args(["comfort"]).command == "comfort"
    assert parser.parse_args(["analyze-data"]).command == "analyze-data"
    assert parser.parse_args(["heating", "--view", "year"]).command == "heating"
    assert parser.parse_args(["cooling", "--view", "year"]).command == "cooling"
    assert parser.parse_args(["plot-template"]).command == "plot-template"
    assert parser.parse_args(["all"]).command == "all"


def test_cli_parser_accepts_plot_template_options():
    parser = build_parser()

    args = parser.parse_args(
        [
            "plot-template",
            "--template",
            "heating-year",
            "--setpoint-min",
            "21",
            "--setpoint-max",
            "26",
            "--temperature-ymin",
            "-20",
            "--temperature-ymax",
            "40",
            "--outdoor-column",
            "tair",
            "--no-setpoint-band",
            "--no-outdoor-temperature",
            "--no-operative-temperature",
        ]
    )

    assert args.template == "heating-year"
    assert args.setpoint_min == 21
    assert args.setpoint_max == 26
    assert args.temperature_ymin == -20
    assert args.temperature_ymax == 40
    assert args.outdoor_column == "tair"
    assert args.show_setpoint_band is False
    assert args.show_outdoor_temperature is False
    assert args.show_operative_temperature is False
    assert args.output_root == "data/test_output"
