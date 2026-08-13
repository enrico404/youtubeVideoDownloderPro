# YouTube Downloader Pro 🚀

Un programma semplice e moderno per scaricare video da YouTube in formato MP4 o MP3.

## 🛠️ Cosa installare

Prima di far partire il programma, devi installare alcune librerie Python. Apri il terminale e digita:

```bash
pip install yt-dlp customtkinter pyinstaller
```

### Fondamentale: FFmpeg (dovrebbero essere già presenti nella cartella)
Per convertire i file in MP3 e scaricare video in alta qualità, il programma ha bisogno di `ffmpeg.exe` e `ffprobe.exe`.

1. Scarica lo zip da qui: [FFmpeg Essentials](https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip)
2. Estrai lo zip e vai nella cartella `bin`.
3. Copia `ffmpeg.exe` e `ffprobe.exe` nella cartella del progetto (accanto a `main.py`).

## 🚀 Come si usa

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

---
*Nota: Se un video non si scarica, prova ad aggiornare il motore di download con: `pip install -U yt-dlp`*
