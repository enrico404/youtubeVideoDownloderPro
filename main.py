import os
import sys
import threading
import customtkinter as ctk
from tkinter import messagebox, filedialog
import yt_dlp

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
    def __init__(self):
        super().__init__()

        self.title("YouTube Downloader Pro")
        self.geometry("600x450")

        # Variabili
        self.url_var = ctk.StringVar()
        self.format_var = ctk.StringVar(value="mp4")
        self.download_path = os.path.join(os.path.expanduser("~"), "Downloads")

        self.create_widgets()

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
