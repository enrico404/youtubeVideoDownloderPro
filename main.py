import os
import sys
import threading
import customtkinter as ctk
from tkinter import messagebox, filedialog
import yt_dlp

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

# Impostazioni tema
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

def get_ffmpeg_path():
    """Restituisce la cartella che contiene ffmpeg.exe e ffprobe.exe."""
    if getattr(sys, 'frozen', False):
        # Se siamo in un eseguibile PyInstaller
        base_path = sys._MEIPASS
    else:
        # Se siamo in script normale, cerca nella cartella corrente
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    ffmpeg_exe = os.path.join(base_path, "ffmpeg.exe")
    print(f"Debug: Cerco ffmpeg in -> {ffmpeg_exe}")
    
    if os.path.exists(ffmpeg_exe):
        print("Debug: ffmpeg.exe TROVATO!")
        return base_path
    
    print("Debug: ffmpeg.exe NON TROVATO.")
    return None

class YoutubeDownloaderApp(ctk.CTk):
    COMBO_PLACEHOLDER = "Analizza il video per vedere i formati"

    def __init__(self):
        super().__init__()

        self.title("YouTube Downloader Pro")

        # Variabili
        self.url_var = ctk.StringVar()
        self.format_var = ctk.StringVar(value="mp4")
        self.download_path = os.path.join(os.path.expanduser("~"), "Downloads")
        self.format_rows: list[FormatRow] = []
        self._busy = False
        self.geometry("600x520")

        self.create_widgets()
        self.url_var.trace_add("write", lambda *_: self._on_url_changed())
        self.format_var.trace_add("write", lambda *_: self._on_mode_changed())
        self._sync_controls()

    def create_widgets(self):
        # Titolo
        self.label_title = ctk.CTkLabel(self, text="YouTube Downloader", font=ctk.CTkFont(size=24, weight="bold"))
        self.label_title.pack(pady=(20, 20))

        # Input URL
        self.entry_url = ctk.CTkEntry(self, placeholder_text="Incolla qui il link di YouTube...", 
                                      textvariable=self.url_var, width=450)
        self.entry_url.pack(pady=10)

        # Selezione Formato
        self.format_frame = ctk.CTkFrame(self)
        self.format_frame.pack(pady=10)
        
        self.radio_mp4 = ctk.CTkRadioButton(self.format_frame, text="Video (MP4)", 
                                           variable=self.format_var, value="mp4")
        self.radio_mp4.grid(row=0, column=0, padx=20, pady=10)
        
        self.radio_mp3 = ctk.CTkRadioButton(self.format_frame, text="Audio (MP3)", 
                                           variable=self.format_var, value="mp3")
        self.radio_mp3.grid(row=0, column=1, padx=20, pady=10)

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
        self.format_combo.configure(state="normal")
        self.format_combo.set("Analizza il video per vedere i formati")
        self.format_combo.configure(state="disabled")
        self.format_combo.grid(row=0, column=1, padx=8)

        # Percorso di salvataggio
        self.path_button = ctk.CTkButton(self, text="Scegli cartella di destinazione", command=self.browse_path)
        self.path_button.pack(pady=5)
        self.label_path = ctk.CTkLabel(self, text=f"Destinazione: {self.download_path}", font=ctk.CTkFont(size=10))
        self.label_path.pack()

        # Bottone Download
        self.download_button = ctk.CTkButton(self, text="Scarica Ora", command=self.start_download_thread,
                                             fg_color="#2ecc71", hover_color="#27ae60")
        self.download_button.pack(pady=20)

        # Barra di avanzamento
        self.progress_label = ctk.CTkLabel(self, text="0%")
        self.progress_label.pack()
        
        self.progress_bar = ctk.CTkProgressBar(self, width=400)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=10)

        # Status
        self.status_label = ctk.CTkLabel(self, text="Pronto", text_color="gray")
        self.status_label.pack(pady=10)

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
        self.format_combo.configure(values=[self.COMBO_PLACEHOLDER], state="normal")
        self.format_combo.set(self.COMBO_PLACEHOLDER)
        self.format_combo.configure(state="disabled")

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

    def browse_path(self):
        path = filedialog.askdirectory()
        if path:
            self.download_path = path
            self.label_path.configure(text=f"Destinazione: {self.download_path}")

    def progress_hook(self, d):
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0%').replace('%', '')
            try:
                progress = float(p) / 100
                self.progress_bar.set(progress)
                self.progress_label.configure(text=f"{p.strip()}%")
                self.status_label.configure(text=f"Scaricando: {d.get('filename', '...')[:50]}...")
            except:
                pass
        elif d['status'] == 'finished':
            self.progress_bar.set(1)
            self.progress_label.configure(text="100%")
            self.status_label.configure(text="Conversione in corso...")

    def start_download_thread(self):
        url = self.url_var.get()
        if not url:
            messagebox.showerror("Errore", "Per favore inserisci un link valido.")
            return
        
        self.download_button.configure(state="disabled")
        threading.Thread(target=self.download, daemon=True).start()

    def download(self):
        url = self.url_var.get()
        fmt = self.format_var.get()
        ffmpeg_path = get_ffmpeg_path()

        if ffmpeg_path is None:
            self.status_label.configure(text="Errore: ffmpeg.exe mancante", text_color="#e74c3c")
            messagebox.showerror("Errore FFmpeg", "Non trovo ffmpeg.exe nella cartella del programma.\n\nAssicurati di aver scaricato e copiato ffmpeg.exe e ffprobe.exe nella stessa cartella di questo script.")
            self.download_button.configure(state="normal")
            return

        ydl_opts = {
            'progress_hooks': [self.progress_hook],
            'outtmpl': os.path.join(self.download_path, '%(title)s.%(ext)s'),
            'ffmpeg_location': ffmpeg_path,
            'quiet': True,
            'no_warnings': True,
            # Compatibilità per video musicali
            'extractor_args': {'youtube': {'player_client': ['ios', 'android', 'web']}},
        }

        if fmt == 'mp3':
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            # Formato video più flessibile per evitare "format not available"
            ydl_opts.update({
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            })

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            self.status_label.configure(text="Download completato!", text_color="#2ecc71")
            messagebox.showinfo("Successo", "Download completato con successo!")
        except Exception as e:
            error_msg = str(e)
            print(f"Debug Errore yt-dlp: {error_msg}")
            self.status_label.configure(text="Errore durante il download", text_color="#e74c3c")
            messagebox.showerror("Errore di Download", f"Dettagli errore:\n{error_msg}")
        finally:
            self.download_button.configure(state="normal")
            self.progress_bar.set(0)
            self.progress_label.configure(text="0%")

if __name__ == "__main__":
    app = YoutubeDownloaderApp()
    app.mainloop()
