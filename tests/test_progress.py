from formats import (
    FormatRow,
    downloading_status_text,
    finished_status_text,
    progress_fraction,
    should_enable_analyze,
    ydl_format_selector,
)


def test_ydl_format_selector_includes_id_and_height_fallback():
    row = FormatRow("399", 1080, 60.0, 1000)
    selector = ydl_format_selector(row)
    assert selector.startswith("399+bestaudio/")
    assert "bestvideo[height=1080]+bestaudio" in selector
    assert selector.endswith("/best")


def test_progress_fraction_from_bytes():
    assert progress_fraction({
        "status": "downloading",
        "downloaded_bytes": 50,
        "total_bytes": 100,
    }) == 0.5


def test_progress_fraction_uses_estimate_when_total_missing():
    assert progress_fraction({
        "status": "downloading",
        "downloaded_bytes": 25,
        "total_bytes_estimate": 100,
    }) == 0.25


def test_progress_fraction_none_when_no_total():
    assert progress_fraction({
        "status": "downloading",
        "downloaded_bytes": 10,
    }) is None


def test_progress_fraction_ignores_percent_str():
    value = progress_fraction({
        "status": "downloading",
        "downloaded_bytes": 10,
        "total_bytes": 40,
        "_percent_str": "\x1b[0;94m  99.9%\x1b[0m",
    })
    assert value == 0.25


def test_progress_fraction_finished_is_one():
    assert progress_fraction({"status": "finished"}) == 1.0


def test_downloading_status_audio_and_video():
    assert downloading_status_text(None) == "Scaricando…"
    assert downloading_status_text({"vcodec": "none"}) == "Scaricando audio…"
    assert downloading_status_text({"vcodec": None}) == "Scaricando audio…"
    assert downloading_status_text({"vcodec": "avc1"}) == "Scaricando video…"


def test_finished_status_depends_on_mode():
    assert finished_status_text("mp4") == "Unione video e audio…"
    assert finished_status_text("mp3") == "Conversione in corso…"


def test_should_enable_analyze():
    assert should_enable_analyze("mp4", "https://youtu.be/x", False) is True
    assert should_enable_analyze("mp4", "  ", False) is False
    assert should_enable_analyze("mp3", "https://youtu.be/x", False) is False
    assert should_enable_analyze("mp4", "https://youtu.be/x", True) is False
