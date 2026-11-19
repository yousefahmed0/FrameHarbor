"""YouTube download stage, isolated in a cancellable subprocess."""
from collections import deque
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from urllib.parse import parse_qs, urlparse

from engine import ExportError, binary, process_options, probe, thumbnail, extract


def normalize_url(value: str) -> str:
    value = value.strip()
    if not re.match(r'^https?://', value, re.I):
        value = 'https://' + value
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or '').lower()
        if parsed.username or parsed.password or parsed.port:
            raise ValueError()
        parts = parsed.path.strip('/').split('/')
        if host in ('youtu.be', 'www.youtu.be') and len(parts) == 1:
            video_id = parts[0]
        elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'):
            if parsed.path.rstrip('/') == '/watch':
                video_id = parse_qs(parsed.query).get('v', [''])[0]
            elif len(parts) == 2 and parts[0] in ('shorts', 'embed', 'live'):
                video_id = parts[1]
            else:
                raise ValueError()
        else:
            raise ValueError()
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            raise ValueError()
    except ValueError as exc:
        raise ExportError('Paste a YouTube video link (youtube.com/watch, youtu.be, or Shorts). Playlist-only links are not supported.') from exc
    return f'https://www.youtube.com/watch?v={video_id}'


def downloader_command():
    tools = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'tools'
    for location in (tools / 'yt-dlp.exe', Path(__file__).resolve().parents[1].parent / 'work' / 'vendor' / 'yt-dlp.exe'):
        if location.is_file():
            return [str(location)]
    installed = shutil.which('yt-dlp')
    if installed:
        return [installed]
    if not getattr(sys, 'frozen', False):
        return [sys.executable, '-m', 'yt_dlp']
    raise ExportError('The YouTube downloader is missing. Extract the entire app ZIP again.')


def stop_download(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        # Kill the downloader and its JavaScript worker together.
        taskkill = str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32' / 'taskkill.exe')
        subprocess.run([taskkill, '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                       timeout=10, **process_options())
    else:
        process.terminate()
    if process.poll() is None:
        process.kill()


def download(value: str, parent: Path, cancel: threading.Event, on_progress=lambda data: None):
    url = normalize_url(value)
    if cancel.is_set():
        return dict(status='cancelled', folder=None, frames=0, error=None)
    node = binary('node')
    command = downloader_command()
    parent = Path(parent).resolve()
    download_root = parent / 'YouTube downloads'
    download_root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=url.rsplit('=', 1)[-1] + '_', dir=download_root))
    command += ['--ignore-config', '--no-cache-dir', '--no-plugin-dirs', '--no-playlist',
                '--no-simulate', '--newline', '--no-colors', '--progress', '--progress-delta', '0.2',
                '--encoding', 'utf-8', '--socket-timeout', '20', '--retries', '2', '--fragment-retries', '2',
                '--js-runtimes', 'node:' + node, '--ffmpeg-location', str(Path(binary('ffmpeg')).parent),
                '--match-filters', '!is_live & !is_upcoming', '--format', 'bestvideo/best',
                '--output', 'source.%(ext)s', '--print', 'before_dl:TITLE %(title)j',
                '--print', 'after_move:FILE %(filepath)j',
                '--progress-template', 'download:PROGRESS %(progress.downloaded_bytes)s %(progress.total_bytes)s %(progress.total_bytes_estimate)s %(progress.speed)s %(progress.eta)s',
                '--', url]
    updates = queue.Queue()
    recent = deque(maxlen=12)
    title = 'YouTube video'
    source = None
    process = None
    error = None
    try:
        with (folder / 'download.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen(command, cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, **process_options())
            def reader():
                try:
                    for line in iter(process.stdout.readline, b''):
                        updates.put(line.decode('utf-8', errors='replace').strip())
                finally:
                    updates.put(None)
            thread = threading.Thread(target=reader, daemon=True)
            thread.start()
            ended = False
            while not ended:
                if cancel.is_set() and process.poll() is None:
                    stop_download(process)
                try:
                    line = updates.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line is None:
                    ended = True
                    continue
                log.write(line + '\n')
                if line.startswith('TITLE '):
                    title = json.loads(line[6:])
                    on_progress(dict(title=title, fraction=0, downloaded=0, total=0))
                elif line.startswith('FILE '):
                    candidate = Path(json.loads(line[5:]))
                    if not candidate.is_absolute():
                        candidate = folder / candidate
                    candidate = candidate.resolve()
                    if candidate.parent == folder.resolve() and candidate.is_file():
                        source = candidate
                elif line.startswith('PROGRESS '):
                    def number(value):
                        try:
                            return max(0, float(value))
                        except (ValueError, TypeError):
                            return 0
                    values = line.split()[1:]
                    if len(values) >= 5:
                        downloaded, total, estimate, speed, eta = map(number, values[:5])
                        total = total or estimate
                        on_progress(dict(title=title, fraction=min(1, downloaded / total) if total else 0,
                                         downloaded=downloaded, total=total, speed=speed, eta=eta))
                else:
                    recent.append(line)
            process.wait(timeout=10)
            thread.join(timeout=1)
            if not cancel.is_set() and (process.returncode or source is None):
                detail = next((line.removeprefix('ERROR: ').strip() for line in reversed(recent) if 'ERROR:' in line), '')
                error = ('YouTube download failed. ' + detail if detail else
                         'No downloadable video was returned. Live streams, private, unavailable, or sign-in-only videos are not supported.')
    except Exception as exc:
        error = f'YouTube download failed: {exc}'
    finally:
        if process:
            if process.poll() is None:
                stop_download(process)
            process.wait(timeout=10)
            process.stdout.close()
    return dict(status='cancelled' if cancel.is_set() else 'failed' if error else 'complete',
                folder=str(folder), video=str(source) if source else None, title=title,
                url=url, frames=0, error=error)


def download_and_extract(value, parent, image_format, step, cancel, on_event=lambda kind, data: None):
    downloaded = download(value, parent, cancel, lambda data: on_event('download_progress', data))
    if downloaded['status'] != 'complete':
        return downloaded
    if cancel.is_set():
        return dict(status='cancelled', folder=downloaded['folder'], frames=0, error=None)
    on_event('download_stage', 'Download complete. Reading video…')
    try:
        info = probe(Path(downloaded['video']))
        info.update(webpage_url=downloaded['url'], video_title=downloaded['title'])
        preview = thumbnail(info) if not cancel.is_set() else None
        if cancel.is_set():
            return dict(status='cancelled', folder=downloaded['folder'], frames=0, error=None)
        on_event('youtube_ready', (info, preview))
        result = extract(info, parent, image_format, step, cancel, lambda data: on_event('progress', data))
        result['folder'] = result.get('folder') or downloaded['folder']
        return result
    except Exception as exc:
        return dict(status='failed', folder=downloaded['folder'], frames=0, error=str(exc))
