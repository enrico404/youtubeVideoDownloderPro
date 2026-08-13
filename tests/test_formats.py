import pytest

from formats import (
    FormatRow,
    PlaylistNotSupportedError,
    build_format_rows,
    format_row_label,
)


def _fmt(**kwargs):
    base = {
        "format_id": "0",
        "vcodec": "avc1.640028",
        "acodec": "none",
        "ext": "mp4",
    }
    base.update(kwargs)
    return base


SAMPLE_FORMATS = [
    _fmt(format_id="18", height=360, fps=30, acodec="mp4a.40.2", tbr=500, filesize=1_000),
    _fmt(format_id="137", height=1080, fps=30, tbr=4000, filesize=8_000_000),
    _fmt(format_id="248", height=1080, fps=30, vcodec="vp9", ext="webm", tbr=5000, filesize=9_000_000),
    _fmt(format_id="399", height=1080, fps=60, vcodec="av01", tbr=6000, filesize=10_000_000),
    _fmt(format_id="140", height=None, vcodec="none", acodec="mp4a.40.2", ext="m4a", filesize=2_000_000, tbr=128),
    _fmt(format_id="251", height=None, vcodec="none", acodec="opus", ext="webm", filesize=1_500_000, tbr=160),
]


def test_playlist_raises():
    with pytest.raises(PlaylistNotSupportedError):
        build_format_rows({"_type": "playlist", "entries": [], "formats": SAMPLE_FORMATS})


def test_no_video_formats_returns_empty():
    assert build_format_rows({"_type": "video", "formats": []}) == []
    assert build_format_rows({"formats": [_fmt(format_id="140", vcodec="none", acodec="mp4a.40.2")]}) == []


def test_groups_by_height_prefers_higher_fps():
    rows = build_format_rows({"_type": "video", "formats": SAMPLE_FORMATS})
    by_height = {row.height: row for row in rows}
    assert set(by_height) == {360, 1080}
    assert by_height[1080].format_id == "399"
    assert by_height[1080].fps == 60
    assert rows[0].height == 1080


def test_prefers_h264_mp4_when_fps_equal():
    formats = [
        _fmt(format_id="vp9", height=720, fps=30, vcodec="vp9", ext="webm", tbr=2500),
        _fmt(format_id="avc", height=720, fps=30, vcodec="avc1.64001f", ext="mp4", tbr=2000),
    ]
    rows = build_format_rows({"formats": formats})
    assert len(rows) == 1
    assert rows[0].format_id == "avc"


def test_estimated_bytes_adds_best_audio():
    rows = build_format_rows({"formats": SAMPLE_FORMATS})
    row_1080 = next(r for r in rows if r.height == 1080)
    # best audio by tbr is 251 (160 > 128)
    assert row_1080.estimated_bytes == 10_000_000 + 1_500_000


def test_label_with_size_and_integer_fps():
    label = format_row_label(FormatRow("399", 1080, 60.0, 11_500_000))
    assert label == "1080p • 60fps • ~11.0 MB"


def test_label_without_fps():
    label = format_row_label(FormatRow("18", 360, None, 5_242_880))
    assert "360p" in label
    assert "fps" not in label
    assert "~" in label and "MB" in label


def test_label_without_size():
    label = format_row_label(FormatRow("137", 1080, 30.0, None))
    assert label == "1080p • 30fps • dimensione n/d"


def test_label_fractional_fps():
    label = format_row_label(FormatRow("1", 1080, 23.976, None))
    assert "23.9fps" in label
