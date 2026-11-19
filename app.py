"""FrameHarbor — local videos and YouTube videos to frames."""
import ctypes
import io
import math
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk
from engine import probe, thumbnail, extract
from youtube import normalize_url, download_and_extract

BG = '#101719'
PANEL = '#192326'
TEXT = '#edf4ef'
MUTED = '#9aafaa'
ACCENT = '#b5f3cd'
EDGE = '#31423e'


def duration_label(seconds):
    seconds = int(seconds)
    return f'{seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}' if seconds >= 3600 else f'{seconds // 60}:{seconds % 60:02}'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('FrameHarbor · Video to frames')
        self.geometry('940x870')
        self.minsize(820, 840)
        self.configure(bg=BG)
        icon = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'assets' / 'app.ico'
        if icon.exists():
            self.iconbitmap(str(icon))
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.events = queue.Queue()
        self.cancel_event = threading.Event()
        self.info = None
        self.busy = False
        self.loading = False
        self.closing = False
        self.last_output = None
        self.photo = None
        self.source = tk.StringVar(value='Choose a video to begin')
        self.source_mode = tk.StringVar(value='Local file')
        self.youtube_url = tk.StringVar()
        self.destination = tk.StringVar(value=str(Path.home() / 'Pictures' / 'FrameHarbor'))
        self.image_format = tk.StringVar(value='PNG')
        self.step = tk.StringVar(value='1')
        self.style_ui()
        self.build_ui()
        self.after(100, self.poll)

    def style_ui(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background=BG, foreground=TEXT)
        style.configure('TEntry', fieldbackground='#0e1517', foreground=TEXT, bordercolor=EDGE, padding=9,
                        insertcolor=TEXT, lightcolor=EDGE, darkcolor=EDGE)
        style.configure('TCombobox', fieldbackground='#0e1517', background=EDGE, foreground=TEXT,
                        arrowcolor=TEXT, padding=8, bordercolor=EDGE)
        style.map('TCombobox', fieldbackground=[('readonly', '#0e1517')], selectbackground=[('readonly', '#0e1517')],
                  selectforeground=[('readonly', TEXT)])
        style.configure('TButton', padding=(15, 10), background=EDGE, foreground=TEXT, borderwidth=0)
        style.map('TButton', background=[('active', '#455c54'), ('disabled', '#24312d')],
                  foreground=[('disabled', '#798b84')])
        style.configure('Accent.TButton', background=ACCENT, foreground='#10271a', font=('Segoe UI Semibold', 11))
        style.map('Accent.TButton', background=[('active', '#d4ffe4'), ('disabled', '#3a5245')],
                  foreground=[('disabled', '#819b8a')])
        style.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor='#2a3934',
                        bordercolor='#2a3934', lightcolor=ACCENT, darkcolor=ACCENT, thickness=7)

    def label(self, parent, text, size=10, color=TEXT, bold=False, bg=BG, **kwargs):
        return tk.Label(parent, text=text, fg=color, bg=bg, anchor='w',
                        font=('Segoe UI Semibold' if bold else 'Segoe UI', size), **kwargs)

    def build_ui(self):
        page = tk.Frame(self, bg=BG, padx=32, pady=20)
        page.pack(fill='both', expand=True)
        self.label(page, 'FRAMEHARBOR   /   VIDEO TO FRAMES', 9, ACCENT, True).pack(anchor='w')
        self.label(page, 'Every frame. Ready to use.', 25, bold=True).pack(anchor='w', pady=(10, 2))
        self.label(page, 'Choose a local video or paste a YouTube link. Save every frame as an image.', 11, MUTED).pack(anchor='w')

        source_row = tk.Frame(page, bg=BG)
        source_row.pack(fill='x', pady=(18, 10))
        self.label(source_row, '01   SOURCE VIDEO', 9, MUTED, True).pack(side='left')
        self.mode_select = ttk.Combobox(source_row, textvariable=self.source_mode, values=('Local file', 'YouTube URL'), state='readonly', width=13)
        self.mode_select.pack(side='left', padx=(15, 10))
        self.mode_select.bind('<<ComboboxSelected>>', lambda event: self.change_source_mode())
        self.browse = ttk.Button(source_row, text='Choose video…', command=self.choose_video)
        self.browse.pack(side='right')
        self.source_label = self.label(source_row, '', textvariable=self.source, wraplength=360)
        self.source_label.pack(side='left', padx=(8, 8))
        self.url_row = tk.Frame(page, bg=BG)
        self.url_row.pack(fill='x', pady=(0, 10))
        self.url_entry = ttk.Entry(self.url_row, textvariable=self.youtube_url)
        self.url_entry.pack(fill='x')
        self.url_hint = self.label(self.url_row, 'Paste a YouTube video URL. The video downloads first, then frames are exported.', 9, MUTED)
        self.url_hint.pack(anchor='w', pady=(4, 0))
        self.url_row.pack_forget()

        card = tk.Frame(page, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        self.preview_card = card
        card.pack(fill='x')
        preview_frame = tk.Frame(card, bg='#0d1214', width=300, height=136)
        preview_frame.pack(side='left', padx=12, pady=12)
        preview_frame.pack_propagate(False)
        self.preview = tk.Label(preview_frame, text='▶', bg='#0d1214', fg='#496259', font=('Segoe UI', 38))
        self.preview.pack(fill='both', expand=True)
        details = tk.Frame(card, bg=PANEL, padx=15)
        details.pack(side='left', fill='both', expand=True, pady=17)
        self.video_title = self.label(details, 'Your video, frame by frame', 12, bold=True, bg=PANEL, wraplength=390)
        self.video_title.pack(anchor='w')
        self.metadata = self.label(details, 'MP4, MOV, MKV, AVI, WebM and more\nOriginal frame dimensions\nSequential, easy-to-sort filenames', 10, MUTED, bg=PANEL, justify='left')
        self.metadata.pack(anchor='w', pady=(12, 0))

        self.label(page, '02   SAVE LOCATION', 9, MUTED, True).pack(anchor='w', pady=(16, 9))
        dest_row = tk.Frame(page, bg=BG)
        dest_row.pack(fill='x')
        self.dest_entry = ttk.Entry(dest_row, textvariable=self.destination)
        self.dest_entry.pack(side='left', fill='x', expand=True)
        self.dest_browse = ttk.Button(dest_row, text='Browse…', command=self.choose_destination)
        self.dest_browse.pack(side='left', padx=(10, 0))
        self.label(page, 'A new subfolder is created for each export.', 9, MUTED).pack(anchor='w', pady=(5, 0))

        self.label(page, '03   EXPORT SETTINGS', 9, MUTED, True).pack(anchor='w', pady=(16, 10))
        options = tk.Frame(page, bg=BG)
        options.pack(fill='x')
        fmt = tk.Frame(options, bg=BG)
        fmt.pack(side='left', fill='x', expand=True)
        self.label(fmt, 'Image format', 10).pack(anchor='w', pady=(0, 6))
        self.format_select = ttk.Combobox(fmt, textvariable=self.image_format, values=('PNG', 'JPG'), state='readonly', width=15)
        self.format_select.pack(anchor='w')
        sampling = tk.Frame(options, bg=BG)
        sampling.pack(side='left', fill='x', expand=True)
        self.label(sampling, 'Save every Nth frame', 10).pack(anchor='w', pady=(0, 6))
        self.step_entry = ttk.Entry(sampling, textvariable=self.step, width=12)
        self.step_entry.pack(anchor='w')
        self.label(options, 'PNG · lossless, larger files\nJPG · high quality, smaller files\nN = 1 saves every frame', 9, MUTED, justify='left').pack(side='right', anchor='s')
        self.step.trace_add('write', lambda *_: self.update_estimate())
        self.estimate = self.label(page, 'Choose a video to see its frame count.', 9, MUTED)
        self.estimate.pack(anchor='w', pady=(11, 15))

        actions = tk.Frame(page, bg=BG)
        actions.pack(fill='x')
        self.start_button = ttk.Button(actions, text='Export frames  →', style='Accent.TButton', command=self.start, state='disabled')
        self.start_button.pack(side='left')
        self.cancel_button = ttk.Button(actions, text='Cancel', command=self.cancel, state='disabled')
        self.cancel_button.pack(side='left', padx=10)
        self.open_button = ttk.Button(actions, text='Open output folder', command=self.open_output, state='disabled')
        self.open_button.pack(side='right')
        self.progress = ttk.Progressbar(page, maximum=100, mode='determinate')
        self.progress.pack(fill='x', pady=(18, 9))
        self.status = self.label(page, 'Ready when you are.', 10, MUTED, wraplength=850, justify='left')
        self.status.pack(fill='x')

    def change_source_mode(self):
        youtube = self.source_mode.get() == 'YouTube URL'
        if youtube:
            self.url_row.pack(fill='x', pady=(0, 10), before=self.preview_card)
            self.browse.pack_forget()
            self.source_label.pack_forget()
            self.photo = None
            self.preview.configure(image='', text='▶')
            self.video_title.configure(text='YouTube → frames')
            self.metadata.configure(text='Paste a video link above\nDownload, then export automatically\nSource video is kept in YouTube downloads')
            self.estimate.configure(text='Frame count will be available after the video downloads.')
            self.status.configure(text='Choose a save location and click Download & export.', fg=MUTED)
        else:
            self.url_row.pack_forget()
            self.browse.pack(side='right')
            self.source_label.pack(side='left', padx=(8, 8))
            if self.info:
                self.render_video(self.info, None)
            else:
                self.photo = None
                self.preview.configure(image='', text='▶')
                self.video_title.configure(text='Your video, frame by frame')
                self.metadata.configure(text='Choose a local video to begin')
            self.update_estimate()
            self.status.configure(text='Ready when you are.', fg=MUTED)
        self.start_button.configure(text='Download & export  →' if youtube else 'Export frames  →',
                                    state='normal' if youtube or self.info else 'disabled')

    def render_video(self, info, data):
        self.video_title.configure(text=info.get('video_title') or Path(info['source']).name)
        fps = f"{info['fps']:.3f}".rstrip('0').rstrip('.')
        self.metadata.configure(text=f"{info['width']} × {info['height']} pixels\n{fps} fps  ·  {duration_label(info['duration'])}\n{info['codec'].upper()}  ·  Original frame order")
        self.photo = None
        self.preview.configure(image='', text='▶')
        if data:
            image = Image.open(io.BytesIO(data))
            image.thumbnail((285, 130), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(image)
            self.preview.configure(image=self.photo, text='')

    def choose_video(self):
        filename = filedialog.askopenfilename(title='Choose a video', filetypes=[('Video files', '*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.wmv *.mts *.m2ts *.mpg *.mpeg *.gif'), ('All files', '*.*')])
        if not filename:
            return
        self.info = None
        self.loading = True
        self.browse.configure(state='disabled')
        self.mode_select.configure(state='disabled')
        self.start_button.configure(state='disabled')
        self.source.set(Path(filename).name)
        self.photo = None
        self.preview.configure(image='', text='…')
        self.status.configure(text='Reading video…', fg=MUTED)
        self.video_title.configure(text='Reading video…')
        self.metadata.configure(text='')
        self.update_estimate()
        def worker():
            try:
                info = probe(Path(filename))
                self.events.put(('loaded', (info, thumbnail(info))))
            except Exception as exc:
                self.events.put(('load_error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def choose_destination(self):
        folder = filedialog.askdirectory(title='Choose where to save frames', mustexist=True)
        if folder:
            self.destination.set(folder)

    def update_estimate(self):
        if self.source_mode.get() == 'YouTube URL':
            self.estimate.configure(text='Frame count will be available after the video downloads.')
            return
        if not self.info:
            self.estimate.configure(text='Choose a video to see its frame count.')
            return
        try:
            step = int(self.step.get())
            if step < 1:
                raise ValueError()
            frames = self.info['frames'] or round(self.info['fps'] * self.info['duration'])
            prefix = '' if self.info['frames'] else 'About '
            count = f'{prefix}{math.ceil(frames / step):,} images' if frames else 'Frame count unavailable'
            self.estimate.configure(text=f'{count}  ·  Full resolution  ·  Long videos can use significant disk space.')
        except ValueError:
            self.estimate.configure(text='Enter a whole number of 1 or more for the frame interval.')

    def set_busy(self, busy):
        self.busy = busy
        for widget in (self.browse, self.dest_browse, self.dest_entry, self.step_entry, self.url_entry):
            widget.configure(state='disabled' if busy else 'normal')
        self.format_select.configure(state='disabled' if busy else 'readonly')
        self.mode_select.configure(state='disabled' if busy else 'readonly')
        ready = self.source_mode.get() == 'YouTube URL' or self.info
        self.start_button.configure(state='normal' if not busy and ready else 'disabled')
        self.cancel_button.configure(state='normal' if busy else 'disabled')

    def start(self):
        youtube = self.source_mode.get() == 'YouTube URL'
        if self.busy or (not youtube and not self.info):
            return
        url = None
        if youtube:
            try:
                url = normalize_url(self.youtube_url.get())
            except Exception as exc:
                messagebox.showerror('Invalid YouTube link', str(exc))
                return
        try:
            step = int(self.step.get())
            if step < 1:
                raise ValueError()
        except ValueError:
            messagebox.showerror('Invalid frame interval', 'Enter a whole number of 1 or more.')
            return
        if not self.destination.get().strip():
            messagebox.showerror('Choose a save location', 'Select a folder for your frames.')
            return
        parent = Path(self.destination.get().strip()).expanduser()
        if not parent.is_absolute():
            messagebox.showerror('Invalid save location', 'Choose a full folder path, such as C:\\Videos\\Frames.')
            return
        self.set_busy(True)
        self.cancel_event.clear()
        self.progress['value'] = 0
        self.last_output = None
        self.open_button.configure(state='disabled')
        self.status.configure(text='Connecting to YouTube…' if youtube else 'Preparing export…', fg=MUTED)
        info, fmt = dict(self.info) if self.info else None, self.image_format.get().lower()
        def worker():
            try:
                if youtube:
                    result = download_and_extract(url, parent, fmt, step, self.cancel_event,
                                                  lambda kind, data: self.events.put((kind, data)))
                else:
                    result = extract(info, parent, fmt, step, self.cancel_event,
                                     lambda value: self.events.put(('progress', value)))
                self.events.put(('finished', result))
            except Exception as exc:
                self.events.put(('export_error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def cancel(self):
        if self.busy:
            self.cancel_event.set()
            self.cancel_button.configure(state='disabled')
            self.status.configure(text='Stopping… keeping files already saved.', fg=MUTED)

    def open_output(self):
        if self.last_output:
            try:
                os.startfile(self.last_output)
            except OSError as exc:
                messagebox.showerror('Cannot open folder', str(exc))

    def poll(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == 'loaded':
                    self.loading = False
                    self.info, data = payload
                    self.browse.configure(state='normal')
                    self.mode_select.configure(state='readonly')
                    self.start_button.configure(state='normal')
                    self.render_video(self.info, data)
                    self.update_estimate()
                    self.status.configure(text='Video ready. Choose your settings and export.', fg=MUTED)
                elif kind == 'load_error':
                    self.loading = False
                    self.browse.configure(state='normal')
                    self.mode_select.configure(state='readonly')
                    self.video_title.configure(text='Unable to open video')
                    self.preview.configure(text='!')
                    self.status.configure(text=payload, fg='#ffb4a8')
                elif kind == 'download_progress':
                    if not self.cancel_event.is_set():
                        self.video_title.configure(text=payload['title'])
                        self.metadata.configure(text='Downloading from YouTube…\nFrames will export automatically when ready.')
                        self.progress['value'] = payload['fraction'] * 100
                        amount = payload['downloaded'] / 1024**2
                        total = payload['total'] / 1024**2
                        size = f'{amount:.1f} / {total:.1f} MB' if total else f'{amount:.1f} MB'
                        self.status.configure(text=f'Downloading video  ·  {size}', fg=MUTED)
                elif kind == 'download_stage':
                    if not self.cancel_event.is_set():
                        self.status.configure(text=payload, fg=MUTED)
                        self.progress['value'] = 0
                elif kind == 'youtube_ready':
                    info, data = payload
                    self.render_video(info, data)
                    self.progress['value'] = 0
                    self.status.configure(text='Video downloaded. Exporting frames…', fg=MUTED)
                elif kind == 'progress':
                    self.progress['value'] = payload['fraction'] * 100
                    if not self.cancel_event.is_set():
                        self.status.configure(text=f"Exporting  ·  {payload['frames']:,} frames saved  ·  {duration_label(payload['elapsed'])} elapsed")
                elif kind == 'finished':
                    self.set_busy(False)
                    self.last_output = payload['folder']
                    self.open_button.configure(state='normal' if self.last_output else 'disabled')
                    if payload['status'] == 'complete':
                        self.progress['value'] = 100
                        self.status.configure(text=f"Done! {payload['frames']:,} frames saved in {duration_label(payload['elapsed'])}. Open the output folder to view them.", fg=ACCENT)
                    elif payload['status'] == 'cancelled':
                        self.status.configure(text=f"Cancelled. {payload['frames']:,} frames saved. Completed files and any partial download are kept.", fg=MUTED)
                    else:
                        self.status.configure(text=payload['error'], fg='#ffb4a8')
                    if self.closing:
                        self.destroy()
                        return
                elif kind == 'export_error':
                    self.set_busy(False)
                    self.status.configure(text=payload, fg='#ffb4a8')
                    if self.closing:
                        self.destroy()
                        return
        except queue.Empty:
            pass
        if self.closing and not self.busy and not self.loading:
            self.destroy()
            return
        self.after(100, self.poll)

    def close(self):
        if self.busy or self.loading:
            self.closing = True
            self.cancel()
            self.withdraw()
        else:
            self.destroy()


if __name__ == '__main__':
    if os.name == 'nt':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    App().mainloop()
