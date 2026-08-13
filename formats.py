from __future__ import annotations

from dataclasses import dataclass

# Do not pin ios/android/web: those clients often return only progressive 360p
# (YouTube SABR). Empty args let yt-dlp pick clients that still expose DASH.
EXTRACTOR_ARGS = {}


class PlaylistNotSupportedError(ValueError):
    """Raised when extract_info returns a playlist."""


@dataclass
class FormatRow:
    format_id: str
    height: int
    fps: float | None
    estimated_bytes: int | None


def _is_audio_only(fmt: dict) -> bool:
    vcodec = fmt.get("vcodec")
    acodec = fmt.get("acodec")
    return (vcodec is None or vcodec == "none") and acodec not in (None, "none")


def _is_video_format(fmt: dict) -> bool:
    vcodec = fmt.get("vcodec")
    height = fmt.get("height")
    return vcodec not in (None, "none") and isinstance(height, (int, float)) and height > 0


def _filesize(fmt: dict) -> int | None:
    for key in ("filesize", "filesize_approx"):
        val = fmt.get(key)
        if val:
            return int(val)
    return None


def _video_rank(fmt: dict) -> tuple:
    fps = float(fmt.get("fps") or 0)
    ext = (fmt.get("ext") or "").lower()
    vcodec = (fmt.get("vcodec") or "").lower()
    h264_bonus = 1 if ext in ("mp4", "m4v") and vcodec.startswith("avc") else 0
    tbr = float(fmt.get("tbr") or 0)
    size = float(_filesize(fmt) or 0)
    return (fps, h264_bonus, tbr, size)


def _best_audio_bytes(formats: list[dict]) -> int | None:
    audios = [f for f in formats if _is_audio_only(f)]
    if not audios:
        return None
    best = max(audios, key=lambda f: (float(f.get("tbr") or 0), float(_filesize(f) or 0)))
    return _filesize(best)


def build_format_rows(info: dict) -> list[FormatRow]:
    if info.get("_type") == "playlist":
        raise PlaylistNotSupportedError("playlist")

    formats = info.get("formats") or []
    audio_bytes = _best_audio_bytes(formats)
    best_by_height: dict[int, dict] = {}

    for fmt in formats:
        if not _is_video_format(fmt):
            continue
        height = int(fmt["height"])
        current = best_by_height.get(height)
        if current is None or _video_rank(fmt) > _video_rank(current):
            best_by_height[height] = fmt

    rows: list[FormatRow] = []
    for height in sorted(best_by_height, reverse=True):
        fmt = best_by_height[height]
        fps_raw = fmt.get("fps")
        fps = float(fps_raw) if fps_raw else None
        video_bytes = _filesize(fmt)
        estimated = None
        if video_bytes is not None or audio_bytes is not None:
            estimated = (video_bytes or 0) + (audio_bytes or 0)
            if estimated == 0:
                estimated = None
        rows.append(
            FormatRow(
                format_id=str(fmt["format_id"]),
                height=height,
                fps=fps,
                estimated_bytes=estimated,
            )
        )
    return rows


def _fps_text(fps: float | None) -> str | None:
    if fps is None or fps == 0:
        return None
    if float(fps).is_integer():
        return str(int(fps))
    truncated = int(fps * 10) / 10
    return f"{truncated:.1f}"


def _size_text(n: int | None) -> str | None:
    if n is None:
        return None
    mb = n / (1024 * 1024)
    return f"~{mb:.1f} MB"


def format_row_label(row: FormatRow) -> str:
    fps_part = _fps_text(row.fps)
    size_part = _size_text(row.estimated_bytes)
    parts = [f"{row.height}p"]
    if fps_part:
        parts.append(f"{fps_part}fps")
    if size_part:
        parts.append(size_part)
    else:
        parts.append("dimensione n/d")
    return " • ".join(parts)


def ydl_format_selector(row: FormatRow) -> str:
    return (
        f"{row.format_id}+bestaudio/"
        f"bestvideo[height={row.height}]+bestaudio/"
        "best"
    )


def progress_fraction(d: dict) -> float | None:
    status = d.get("status")
    if status == "finished":
        return 1.0
    if status != "downloading":
        return None
    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
    downloaded = d.get("downloaded_bytes") or 0
    if total <= 0:
        return None
    return min(1.0, downloaded / total)


def downloading_status_text(info_dict: dict | None) -> str:
    if not info_dict:
        return "Scaricando…"
    vcodec = info_dict.get("vcodec")
    if vcodec is None or vcodec == "none":
        return "Scaricando audio…"
    return "Scaricando video…"


def finished_status_text(fmt: str) -> str:
    if fmt == "mp4":
        return "Unione video e audio…"
    return "Conversione in corso…"


def should_enable_analyze(mode: str, url: str, busy: bool) -> bool:
    return mode == "mp4" and bool(url.strip()) and not busy
