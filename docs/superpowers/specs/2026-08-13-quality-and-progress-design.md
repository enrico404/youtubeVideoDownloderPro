# Quality picker and graphical progress — design

Date: 2026-08-13  
Scope: extend the existing CustomTkinter YouTube downloader (`main.py`) so the user can pick a real video format after analysis, and so download progress updates in the GUI instead of only in the console.

Out of scope: playlist handling, audio bitrate picker for MP3, rewriting the UI as a wizard or popup, changing how FFmpeg is located.

## Goal

1. For **Video (MP4)**, show only formats that exist for the pasted URL, labeled as `1080p • 30fps • ~45 MB`, then download that video merged with the best audio.
2. For **Audio (MP3)**, keep current behavior: best audio converted to MP3 at 192 kbps, no quality menu.
3. Drive the existing progress bar and percent label from real byte counts, on the UI thread, with no console progress.

## Architecture

Keep a single `YoutubeDownloaderApp` in `main.py`. No new windows, no extra modules unless a helper function in the same file stays clearer than inlining.

Two background operations, each on a daemon thread:

| Operation | Trigger | Worker | UI result |
|-----------|---------|--------|-----------|
| Analyze | **Analizza video** | `yt_dlp.YoutubeDL.extract_info(url, download=False)` | Combo filled with format rows |
| Download | **Scarica Ora** | `yt_dlp.YoutubeDL.download` | File on disk, progress bar, status |

All widget reads/writes from worker threads go through `self.after(0, ...)` so Tkinter stays on the main thread.

## UI

Window height increases enough to fit the new row (about `600x520`). Order from top to bottom stays:

1. Title  
2. URL entry  
3. MP4 / MP3 radios  
4. **Analizza video** button + format `CTkComboBox` (new)  
5. Destination folder button + path label  
6. **Scarica Ora**  
7. Percent label + `CTkProgressBar` (already present)  
8. Status label  

### Widget states

- Format combo starts disabled, placeholder like `Analizza il video per vedere i formati`.
- **Analizza video** is enabled only when format is MP4 and an URL is present. Disabled during analyze and during download.
- When the user switches to MP3: disable analyze and combo; download does not require a selected format.
- When the user switches back to MP4: enable analyze; combo stays empty until a new analysis.
- Changing the URL text after a successful analysis clears the combo and the stored format list. Download on MP4 then requires analyze again.
- **Scarica Ora** is disabled during analyze and during download; re-enabled in `finally`.

## Analyze: building the format list

Use the same extractor args already in the app (`player_client`: ios, android, web) so analysis and download see the same catalog.

Keep a format only if it has video (`vcodec` not `none`) and a numeric `height`.

Group by `height`. For each height keep one representative format:

1. Prefer higher `fps` (missing fps treated as 0).  
2. Prefer `ext` in `mp4` / `m4v` and `vcodec` starting with `avc` (H.264) when fps is equal.  
3. Otherwise prefer the larger `tbr` / `filesize` / `filesize_approx`.

Store internally, for each row:

- `format_id` of that video stream  
- `height`, `fps`  
- estimated size: video `filesize` or `filesize_approx`, plus the best audio stream’s `filesize` or `filesize_approx` (audio = `acodec` not `none` and `vcodec` is `none`). If both unknown, size is missing.

Combo label:

- With size: `{height}p • {fps}fps • ~{MB} MB` (`fps` as integer if whole, else one decimal).  
- Without fps: `{height}p • ~{MB} MB`.  
- Without size: `{height}p • {fps}fps • dimensione n/d`.

Sort rows by height descending. Default selection: highest row.

The combo shows labels only. The app keeps a parallel list of rows and maps the selected index to `format_id` / `height`.

If `extract_info` returns a playlist (`_type == playlist`), do not list entries: show an error that playlists are not supported and leave the combo empty.

If analysis returns no video formats, show an error and leave the combo empty.

## Download: yt-dlp options

Shared options stay: `outtmpl` in the chosen folder, `ffmpeg_location`, `extractor_args`, `progress_hooks`. Add `noprogress: True` (and keep `quiet` / `no_warnings`) so the console does not print a progress bar.

**MP4:** `'format': '{format_id}+bestaudio/bestvideo[height={height}]+bestaudio/best'`. FFmpeg merges into MP4 as today. No extra postprocessor beyond what yt-dlp already does for merge.

**MP3:** unchanged — `bestaudio/best` + `FFmpegExtractAudio` to mp3 preferredquality `192`.

## Progress

Do not parse `_percent_str` (it can contain ANSI color codes and breaks `float()`).

In `progress_hook`:

- `status == 'downloading'`:  
  `total = total_bytes or total_bytes_estimate`  
  `progress = downloaded_bytes / total` when total > 0, else leave bar unchanged.  
  Percent label = rounded percent.  
  Status = `Scaricando audio…` when the current file is audio-only (`info_dict.vcodec` is missing or `none`); `Scaricando video…` when it has a video codec; otherwise `Scaricando…`.
- `status == 'finished'`: bar at 100%, status `Unione video e audio…` for MP4 or `Conversione in corso…` for MP3.

Video+audio means the bar may run 0→100 twice (one file after the other). That is accepted.

After success: status `Download completato!` (green), info dialog, then reset bar and percent to 0 in `finally` as today.

## Errors

Always restore buttons in `finally`. Status line + `messagebox`:

| Case | Message |
|------|---------|
| Empty URL | Ask for a valid link (existing). |
| MP4 download with no selected format | Ask to analyze and pick a format. |
| Analyze failure | Show yt-dlp error text. |
| Missing `ffmpeg.exe` | Existing FFmpeg dialog. |
| Download / merge failure | Show yt-dlp error text (existing pattern). |

## Testing (manual)

1. Paste a normal YouTube URL, MP4, Analizza → combo lists several resolutions with fps and size when known.  
2. Pick 720p, download → file plays with audio; GUI bar and percent move; console has no progress spam.  
3. Change URL after analyze → combo clears; download refused until new analyze.  
4. Switch to MP3 → combo/analyze disabled; download produces mp3 without analyze.  
5. MP4 download without analyze → error, no download.  
6. Invalid URL on analyze → error, buttons usable again.  
7. During download, window stays responsive (cancel not required).
