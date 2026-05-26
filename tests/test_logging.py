from datetime import datetime

from ma_analyse.core.logging import build_log_file_path, command_log, format_duration, should_log_command, timed_step


def test_log_file_path_uses_command_and_timestamp(tmp_path):
    timestamp = datetime(2026, 5, 24, 12, 30, 5)

    path = build_log_file_path("analyze_data", log_root=tmp_path, timestamp=timestamp)

    assert path == tmp_path / "2026-05-24_123005_analyze-data.log"


def test_command_log_writes_console_output_and_durations_to_file(tmp_path):
    with command_log("heating", log_root=tmp_path) as log_file:
        print("Analyse gestartet")
        with timed_step("Testschritt"):
            print("Schritt laeuft")

    content = log_file.read_text(encoding="utf-8")
    assert "ma_analyse Log: heating" in content
    assert "Analyse gestartet" in content
    assert "Laufzeit Schritt 'Testschritt':" in content
    assert "Gesamtlaufzeit:" in content
    assert "Ende:" in content


def test_only_analysis_commands_are_logged():
    assert should_log_command("heating")
    assert should_log_command("analyze-data")
    assert should_log_command("plot-template")
    assert not should_log_command("gui")


def test_format_duration_is_readable():
    assert format_duration(1.234).endswith(" s")
    assert format_duration(61.5) == "1 min 1.50 s"
    assert format_duration(3661.5) == "1 h 1 min 1.50 s"
