# Quality picker and graphical progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user analyze a YouTube URL, pick a real MP4 quality from a combo box, and watch download progress on the existing GUI bar instead of the console.

**Architecture:** Pure yt-dlp helpers live in `formats.py` (format list, labels, format selector, progress math) so they can be unit-tested without Tk. `main.py` keeps `YoutubeDownloaderApp`: analyze/download daemon threads, widget state, and `self.after(0, ...)` for UI updates.

**Tech Stack:** Python 3, customtkinter, yt-dlp, FFmpeg (existing), pytest for unit tests.

## Global Constraints

- Italian UI copy only (buttons, status, messagebox).
- Extractor args must stay `{'youtube': {'player_client': ['ios', 'android', 'web']}}` for both analyze and download.
- MP3: no quality picker; `bestaudio/best` + FFmpegExtractAudio mp3 192.
- Playlists are not supported: error, empty combo.
- All Tk widget updates from worker threads go through `self.after(0, ...)`.
- Do not parse `_percent_str`; use byte counts.
- Console progress off: `quiet`, `no_warnings`, `noprogress: True`.
- Do not add a wizard, popup, or audio bitrate menu.
- Do not change `get_ffmpeg_path()`.

## File structure

| File | Responsibility |
|------|----------------|
| `formats.py` | `FormatRow`, `PlaylistNotSupportedError`, `build_format_rows`, `format_row_label`, `ydl_format_selector`, `progress_fraction`, `downloading_status_text`, `finished_status_text`, `should_enable_analyze`, `EXTRACTOR_ARGS` |
| `main.py` | GUI, threads, yt-dlp `extract_info` / `download`, wiring |
| `tests/test_formats.py` | Unit tests for format list and labels |
| `tests/test_progress.py` | Unit tests for progress helpers and analyze-button enablement |
| `README.md` | Analyze + quality steps |

---

### Task 1: Format list helpers

**Files:**
- Create: `formats.py`
- Create: `tests/test_formats.py`
- Test: `tests/test_formats.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - `EXTRACTOR_ARGS: dict`
  - `class PlaylistNotSupportedError(ValueError)`
  - `class FormatRow` with fields `format_id: str`, `height: int`, `fps: float | None`, `estimated_bytes: int | None`
  - `build_format_rows(info: dict) -> list[FormatRow]` — raises `PlaylistNotSupportedError` if `info.get('_type') == 'playlist'`; otherwise video-only formats grouped by height
  - `format_row_label(row: FormatRow) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_formats.py`:

```python
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
    assert "23.976" not in label
    assert "23.9fps" in label or "24.0fps" in label or "24fps" in label
```

For `test_label_with_size_and_integer_fps`, the implementation must format MB as `bytes / (1024 * 1024)` with one decimal when `< 100`, so `11_500_000` → `~11.0 MB`. For fractional fps, show one decimal (`23.9fps` from `23.976`).

- [ ] **Step 2: Run tests to verify they fail**

Run from the project root:

```bash
python -m pip install pytest -q
python -m pytest tests/test_formats.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'formats'` (or import error for `build_format_rows`).

- [ ] **Step 3: Write minimal implementation**

Create `formats.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

EXTRACTOR_ARGS = {"youtube": {"player_client": ["ios", "android", "web"]}}


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
    return f"{fps:.1f}"


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
```

Note: `ydl_format_selector`, `progress_fraction`, `downloading_status_text`, `finished_status_text`, and `should_enable_analyze` are included here so Task 2 tests can import them without a second rewrite of `formats.py`. Task 1 tests do not cover them yet.

If `test_label_fractional_fps` is too strict about 23.9 vs 24.0, keep `_fps_text` as `f"{fps:.1f}"` (23.976 → `23.9`) and assert `"23.9fps" in label` only — **edit the test to**:

```python
def test_label_fractional_fps():
    label = format_row_label(FormatRow("1", 1080, 23.976, None))
    assert "23.9fps" in label
```

Do that edit in `tests/test_formats.py` before running Step 4 if Step 1 still has the looser assertion.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_formats.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add formats.py tests/test_formats.py
git commit -m "feat: build YouTube format rows and combo labels"
```

---

### Task 2: Progress helpers and format selector tests

**Files:**
- Modify: `formats.py` (already complete after Task 1; only change if tests fail)
- Create: `tests/test_progress.py`
- Test: `tests/test_progress.py`

**Interfaces:**
- Consumes: `FormatRow`, `ydl_format_selector`, `progress_fraction`, `downloading_status_text`, `finished_status_text`, `should_enable_analyze` from Task 1
- Produces: the same functions, now covered by tests — signatures must not change

- [ ] **Step 1: Write the failing tests**

Create `tests/test_progress.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_progress.py -v
```

Expected: FAIL only if Task 1 omitted those functions. If Task 1 already added them, this step may PASS immediately — that is OK; do not delete the tests. If they fail with `ImportError` or `AssertionError`, fix `formats.py` to match the assertions above (do not change the test names or intended behavior).

- [ ] **Step 3: Adjust implementation only if tests fail**

If `progress_fraction` is missing or wrong, it must be exactly:

```python
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
```

- [ ] **Step 4: Run all unit tests**

```bash
python -m pytest tests -v
```

Expected: all tests in `test_formats.py` and `test_progress.py` PASS.

- [ ] **Step 5: Commit**

```bash
git add formats.py tests/test_progress.py
git commit -m "test: cover progress math and yt-dlp format selector"
```

---

### Task 3: GUI — analyze row and widget state

**Files:**
- Modify: `main.py`
- Test: manual (Tk); enablement logic already unit-tested via `should_enable_analyze`

**Interfaces:**
- Consumes: `should_enable_analyze`, `format_row_label`, `FormatRow` from `formats.py`
- Produces:
  - `YoutubeDownloaderApp.format_rows: list[FormatRow]`
  - `YoutubeDownloaderApp._busy: bool`
  - `YoutubeDownloaderApp._sync_controls()`
  - `YoutubeDownloaderApp._clear_format_rows()`
  - `YoutubeDownloaderApp._selected_format_row() -> FormatRow | None`
  - Widgets: `analyze_button`, `format_combo`
  - Geometry `600x520`

Do not wire yt-dlp analyze/download yet. Analyze button can call a stub that only shows a message, or `start_analyze_thread` can be a no-op `pass` until Task 4. Prefer: button `command=self.start_analyze_thread` with `start_analyze_thread` defined as:

```python
def start_analyze_thread(self):
    messagebox.showinfo("Analizza", "Analisi non ancora collegata.")
```

so the layout is clickable.

- [ ] **Step 1: Add imports, state, geometry, and format row widgets**

At the top of `main.py`, add:

```python
from formats import (
    EXTRACTOR_ARGS,
    FormatRow,
    PlaylistNotSupportedError,
    build_format_rows,
    downloading_status_text,
    finished_status_text,
    format_row_label,
    progress_fraction,
    should_enable_analyze,
    ydl_format_selector,
)
```

(`EXTRACTOR_ARGS`, `PlaylistNotSupportedError`, `build_format_rows`, `ydl_format_selector`, progress helpers are unused until Tasks 4–5; import them now so later tasks only touch methods.)

In `__init__`, after `self.download_path = ...`:

```python
self.format_rows: list[FormatRow] = []
self._busy = False
self.geometry("600x520")
```

Keep `self.title(...)`. Change geometry from `600x450` to `600x520`.

After `self.create_widgets()`, register traces (must be after widgets exist):

```python
self.url_var.trace_add("write", lambda *_: self._on_url_changed())
self.format_var.trace_add("write", lambda *_: self._on_mode_changed())
self._sync_controls()
```

- [ ] **Step 2: Insert analyze button + combo between radios and destination**

In `create_widgets`, after the MP3 radio `grid(...)` and before `# Percorso di salvataggio`, add:

```python
self.analyze_frame = ctk.CTkFrame(self, fg_color="transparent")
self.analyze_frame.pack(pady=10)

self.analyze_button = ctk.CTkButton(
    self.analyze_frame,
    text="Analizza video",
    command=self.start_analyze_thread,
    width=160,
)
self.analyze_button.grid(row=0, column=0, padx=8)

self.format_combo = ctk.CTkComboBox(
    self.analyze_frame,
    values=["Analizza il video per vedere i formati"],
    width=320,
    state="disabled",
)
self.format_combo.set("Analizza il video per vedere i formati")
self.format_combo.grid(row=0, column=1, padx=8)
```

Add `command` on the radios so mode changes fire even if `trace_add` on `StringVar` is enough (trace is enough; radios do not need `command` if `format_var.trace_add` is registered).

- [ ] **Step 3: Add control helpers and stub analyze**

Add these methods on `YoutubeDownloaderApp` (before `browse_path`):

```python
COMBO_PLACEHOLDER = "Analizza il video per vedere i formati"

def _on_url_changed(self):
    if self.format_rows:
        self._clear_format_rows()
    self._sync_controls()

def _on_mode_changed(self):
    if self.format_var.get() == "mp3":
        self._clear_format_rows()
    self._sync_controls()

def _clear_format_rows(self):
    self.format_rows = []
    self.format_combo.configure(values=[self.COMBO_PLACEHOLDER], state="disabled")
    self.format_combo.set(self.COMBO_PLACEHOLDER)

def _sync_controls(self):
    url = self.url_var.get()
    mode = self.format_var.get()
    analyze_state = "normal" if should_enable_analyze(mode, url, self._busy) else "disabled"
    self.analyze_button.configure(state=analyze_state)
    download_state = "disabled" if self._busy else "normal"
    self.download_button.configure(state=download_state)
    if self._busy or mode == "mp3" or not self.format_rows:
        self.format_combo.configure(state="disabled")
    else:
        self.format_combo.configure(state="readonly")

def _selected_format_row(self) -> FormatRow | None:
    label = self.format_combo.get()
    for row in self.format_rows:
        if format_row_label(row) == label:
            return row
    return None

def _set_busy(self, busy: bool):
    self._busy = busy
    self._sync_controls()

def start_analyze_thread(self):
    messagebox.showinfo("Analizza", "Analisi non ancora collegata.")
```

`COMBO_PLACEHOLDER` must be a class attribute on `YoutubeDownloaderApp`, not a free function. Place it immediately inside the class, before `__init__`:

```python
class YoutubeDownloaderApp(ctk.CTk):
    COMBO_PLACEHOLDER = "Analizza il video per vedere i formati"
```

and remove the stray module-level assignment if you copied it above `_on_url_changed`.

- [ ] **Step 4: Manual check (no yt-dlp)**

Run:

```bash
python main.py
```

Expected:
- Window taller than before; **Analizza video** and combo visible under the radios.
- Combo disabled with placeholder text.
- **Analizza video** disabled while URL is empty; enabled after pasting text (MP4).
- Switching to MP3 disables Analizza; switching back to MP4 re-enables it if URL is non-empty.
- Clicking Analizza shows the stub dialog.

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: add analyze button and quality combo to the UI"
```

---

### Task 4: Wire analyze to yt-dlp

**Files:**
- Modify: `main.py` (`start_analyze_thread`, new `analyze`, `_on_analyze_ok`, `_on_analyze_error`)

**Interfaces:**
- Consumes: `build_format_rows`, `format_row_label`, `PlaylistNotSupportedError`, `EXTRACTOR_ARGS`
- Produces: `analyze(self) -> None` running on a daemon thread; fills `self.format_rows` and combo values on the UI thread

- [ ] **Step 1: Replace the analyze stub with a real worker**

Replace `start_analyze_thread` and add worker + UI callbacks:

```python
def start_analyze_thread(self):
    url = self.url_var.get().strip()
    if not url:
        messagebox.showerror("Errore", "Per favore inserisci un link valido.")
        return
    if self.format_var.get() != "mp4":
        return
    self._set_busy(True)
    self._ui_status("Analisi in corso…", "gray")
    threading.Thread(target=self.analyze, args=(url,), daemon=True).start()

def analyze(self, url: str):
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "extractor_args": EXTRACTOR_ARGS,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        rows = build_format_rows(info)
        self.after(0, lambda: self._on_analyze_ok(url, rows))
    except PlaylistNotSupportedError:
        self.after(0, lambda: self._on_analyze_error(
            "Le playlist non sono supportate. Incolla il link di un singolo video."
        ))
    except Exception as e:
        self.after(0, lambda: self._on_analyze_error(str(e)))

def _on_analyze_ok(self, analyzed_url: str, rows: list[FormatRow]):
    try:
        if self.url_var.get().strip() != analyzed_url:
            return
        if not rows:
            self._clear_format_rows()
            self._ui_status("Nessun formato video disponibile", "#e74c3c")
            messagebox.showerror(
                "Errore",
                "Nessun formato video disponibile per questo link.",
            )
            return
        self.format_rows = rows
        labels = [format_row_label(row) for row in rows]
        self.format_combo.configure(values=labels, state="readonly")
        self.format_combo.set(labels[0])
        self._ui_status("Scegli la qualità e premi Scarica Ora", "gray")
    finally:
        self._set_busy(False)

def _on_analyze_error(self, message: str):
    self._clear_format_rows()
    self._ui_status("Errore durante l'analisi", "#e74c3c")
    messagebox.showerror("Errore di analisi", f"Dettagli errore:\n{message}")
    self._set_busy(False)

def _ui_status(self, text: str, color: str):
    self.status_label.configure(text=text, text_color=color)
```

- [ ] **Step 2: Run unit tests to ensure GUI changes did not break helpers**

```bash
python -m pytest tests -v
```

Expected: PASS.

- [ ] **Step 3: Manual analyze check**

Run `python main.py`, paste a single-video YouTube URL, click **Analizza video**.

Expected:
- Status shows `Analisi in corso…`; Analizza and Scarica disabled while busy.
- Combo fills with labels like `1080p • 30fps • ~45.0 MB` (size may be `dimensione n/d`).
- Highest resolution is selected.
- Changing the URL clears the combo back to the placeholder.
- A playlist URL or garbage URL shows an error; buttons work again.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: analyze YouTube URL and list available qualities"
```

---

### Task 5: Download selected format and GUI progress

**Files:**
- Modify: `main.py` (`start_download_thread`, `download`, `progress_hook`, `_apply_progress`)
- Modify: `README.md`

**Interfaces:**
- Consumes: `ydl_format_selector`, `progress_fraction`, `downloading_status_text`, `finished_status_text`, `_selected_format_row`
- Produces: MP4 downloads using `{format_id}+bestaudio/bestvideo[height={height}]+bestaudio/best`; progress bar driven by bytes on the UI thread

- [ ] **Step 1: Guard MP4 downloads and use the selected selector**

Replace `start_download_thread` with:

```python
def start_download_thread(self):
    url = self.url_var.get().strip()
    if not url:
        messagebox.showerror("Errore", "Per favore inserisci un link valido.")
        return
    if self.format_var.get() == "mp4" and self._selected_format_row() is None:
        messagebox.showerror(
            "Errore",
            "Analizza il video e scegli un formato prima di scaricare.",
        )
        return
    self._set_busy(True)
    self.progress_bar.set(0)
    self.progress_label.configure(text="0%")
    threading.Thread(target=self.download, daemon=True).start()
```

Replace the body of `download` so UI updates use `self.after`, `noprogress` is True, extractor args come from `EXTRACTOR_ARGS`, and MP4 uses `ydl_format_selector`.

```python
def download(self):
    url = self.url_var.get().strip()
    fmt = self.format_var.get()
    ffmpeg_path = get_ffmpeg_path()

    if ffmpeg_path is None:
        def _no_ffmpeg():
            self._ui_status("Errore: ffmpeg.exe mancante", "#e74c3c")
            messagebox.showerror(
                "Errore FFmpeg",
                "Non trovo ffmpeg.exe nella cartella del programma.\n\n"
                "Assicurati di aver scaricato e copiato ffmpeg.exe e ffprobe.exe "
                "nella stessa cartella di questo script.",
            )
            self._set_busy(False)
        self.after(0, _no_ffmpeg)
        return

    ydl_opts = {
        "progress_hooks": [self.progress_hook],
        "outtmpl": os.path.join(self.download_path, "%(title)s.%(ext)s"),
        "ffmpeg_location": ffmpeg_path,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "extractor_args": EXTRACTOR_ARGS,
    }

    if fmt == "mp3":
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    else:
        row = self._selected_format_row()
        if row is None:
            def _no_row():
                messagebox.showerror(
                    "Errore",
                    "Analizza il video e scegli un formato prima di scaricare.",
                )
                self._set_busy(False)
            self.after(0, _no_row)
            return
        ydl_opts["format"] = ydl_format_selector(row)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        def _ok():
            self._ui_status("Download completato!", "#2ecc71")
            messagebox.showinfo("Successo", "Download completato con successo!")
        self.after(0, _ok)
    except Exception as e:
        error_msg = str(e)
        print(f"Debug Errore yt-dlp: {error_msg}")
        def _err(msg=error_msg):
            self._ui_status("Errore durante il download", "#e74c3c")
            messagebox.showerror("Errore di Download", f"Dettagli errore:\n{msg}")
        self.after(0, _err)
    finally:
        def _done():
            self.progress_bar.set(0)
            self.progress_label.configure(text="0%")
            self._set_busy(False)
        self.after(0, _done)
```

- [ ] **Step 2: Replace `progress_hook` so it never touches widgets directly**

```python
def progress_hook(self, d):
    info = d.get("info_dict") or {}
    payload = {
        "status": d.get("status"),
        "downloaded_bytes": d.get("downloaded_bytes"),
        "total_bytes": d.get("total_bytes"),
        "total_bytes_estimate": d.get("total_bytes_estimate"),
        "info_dict": {"vcodec": info.get("vcodec")},
    }
    self.after(0, lambda p=payload: self._apply_progress(p))

def _apply_progress(self, d: dict):
    fraction = progress_fraction(d)
    if fraction is not None:
        self.progress_bar.set(fraction)
        self.progress_label.configure(text=f"{int(round(fraction * 100))}%")
    if d.get("status") == "downloading":
        self._ui_status(downloading_status_text(d.get("info_dict")), "gray")
    elif d.get("status") == "finished":
        self.progress_bar.set(1)
        self.progress_label.configure(text="100%")
        self._ui_status(finished_status_text(self.format_var.get()), "gray")
```

Delete the old `_percent_str` / `except: pass` implementation entirely.

- [ ] **Step 3: Update README usage**

In `README.md`, replace the "Come si usa" numbered list with:

```markdown
1. Avvia il programma:
   ```bash
   python main.py
   ```
2. Incolla il link di YouTube nel campo di testo.
3. Scegli **Video (MP4)** o **Audio (MP3)**.
4. Se hai scelto MP4, clicca **Analizza video**, poi scegli qualità dal menu (`1080p • 30fps • ~45 MB`).
5. (Opzionale) Scegli la cartella di destinazione.
6. Clicca **Scarica Ora**. Il progresso si vede sulla barra nella finestra.
7. Il file verrà salvato nella cartella **Download** (o in quella che hai scelto).
```

Keep the FFmpeg and `pip install` sections. Add `pytest` only as an optional line under install, not required to run the app:

```bash
pip install yt-dlp customtkinter pyinstaller
```

Do not add pytest to the user install command.

- [ ] **Step 4: Run unit tests then a real download**

```bash
python -m pytest tests -v
python main.py
```

Manual (spec checklist):
1. MP4 + Analizza → several resolutions in the combo.
2. Pick a mid quality (e.g. 720p), download → file has audio; bar and percent move; console has no progress bar spam.
3. Change URL after analyze → combo clears; Scarica Ora on MP4 shows the analyze error.
4. MP3 → analyze/combo disabled; download works without analyze.
5. MP4 without analyze → error, no download.
6. Invalid URL on analyze → error, buttons usable.
7. Window stays responsive during download.

- [ ] **Step 5: Commit**

```bash
git add main.py README.md
git commit -m "feat: download chosen quality and update the GUI progress bar"
```

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| Analyze button, fetch real formats | 4 |
| Combo labels `height • fps • size` | 1, 4 |
| Group by height, prefer fps then H.264 | 1 |
| Auto-merge best audio via `format_id+bestaudio` + fallback | 2, 5 |
| MP3 unchanged, no quality menu | 3, 5 |
| Combo/analyze disabled for MP3 | 3 |
| URL change clears formats | 3 |
| Playlist error | 1, 4 |
| Empty format list error | 4 |
| Progress from bytes, UI thread, no `_percent_str` | 2, 5 |
| `noprogress` + quiet | 4, 5 |
| Dual 0→100 accepted; video/audio status text | 2, 5 |
| FFmpeg missing dialog unchanged | 5 |
| Restore buttons in finally | 5 |
| Window ~600x520, widget order | 3 |
| Manual test list | Task 5 Step 4 |
