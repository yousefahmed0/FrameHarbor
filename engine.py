"""Local video decoding. No GUI dependencies and no network requests."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from fractions import Fraction


class ExportError(RuntimeError):
    pass


def binary(name: str) -> str:
    suffix = '.exe' if os.name == 'nt' else ''
    bundled = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'tools' / (name + suffix)
    found = str(bundled) if bundled.is_file() else shutil.which(name)
    if not found:
        raise ExportError(f'{name} was not found. Keep the application folder together, or install FFmpeg for source use.')
    return found


def process_options():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def probe(video: Path) -> dict:
    video = video.resolve(strict=True)
    command = [binary('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(video)]
    try:
        result = subprocess.run(command, capture_output=True, timeout=60, **process_options())
    except subprocess.TimeoutExpired as exc:
        raise ExportError('Reading this video took too long. Try a local copy of the file.') from exc
    if result.returncode:
        raise ExportError('Cannot read this video. It may be damaged or use an unsupported format.')
    data = json.loads(result.stdout)
    streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'video'
               and not s.get('disposition', {}).get('attached_pic')]
    if not streams:
        raise ExportError('This file does not contain a video stream.')
    stream = streams[0]
    def number(value):
        try:
            result = float(value)
            return result if math.isfinite(result) and result > 0 else 0.0
        except (TypeError, ValueError):
            return 0.0
    try:
        fps = float(Fraction(stream.get('avg_frame_rate', '0/1')))
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    duration = number(stream.get('duration')) or number(data.get('format', {}).get('duration'))
    frames = int(number(stream.get('nb_frames')))
    return dict(source=str(video), stream_index=stream['index'], width=stream.get('width', 0),
                height=stream.get('height', 0), fps=fps, duration=duration, frames=frames,
                codec=stream.get('codec_name', 'unknown'))


def thumbnail(info: dict) -> bytes | None:
    try:
        result = subprocess.run([binary('ffmpeg'), '-v', 'error', '-i', info['source'],
                                 '-map', f"0:{info['stream_index']}", '-frames:v', '1',
                                 '-vf', 'scale=640:360:force_original_aspect_ratio=decrease',
                                 '-f', 'image2pipe', '-c:v', 'png', 'pipe:1'],
                                capture_output=True, timeout=20, **process_options())
        return result.stdout if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError):
        return None


def create_output(parent: Path, source: Path, name: str | None = None) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r'[<>:"/\\|?*%\x00-\x1f]', '_', name or source.stem).strip(' .')[:70] or 'video'
    label = f'{safe_stem}_frames_{datetime.now():%Y%m%d_%H%M%S}'
    for count in range(10000):
        folder = parent / (label if not count else f'{label}_{count + 1}')
        try:
            folder.mkdir()
            return folder.resolve()
        except FileExistsError:
            continue
    raise ExportError('Could not create a unique export folder.')


def extract(info: dict, parent: Path, image_format: str, step: int,
            cancel: threading.Event, on_progress=lambda value: None) -> dict:
    if image_format not in ('png', 'jpg') or not isinstance(step, int) or step < 1:
        raise ValueError('Choose PNG or JPG and a frame interval of at least 1.')
    if cancel.is_set():
        return dict(status='cancelled', folder=None, frames=0, elapsed=0)
    tool = binary('ffmpeg')
    output = create_output(Path(parent), Path(info['source']), info.get('video_title'))
    command = [tool, '-hide_banner', '-loglevel', 'warning', '-stats_period', '0.1', '-n', '-i', info['source'],
               '-map', f"0:{info['stream_index']}", '-an', '-sn', '-dn']
    if step > 1:
        command += ['-vf', f'select=not(mod(n\\,{step}))']
    command += ['-fps_mode', 'passthrough']
    command += ['-c:v', 'png', '-compression_level', '3'] if image_format == 'png' else ['-c:v', 'mjpeg', '-q:v', '2']
    command += ['-start_number', '1', '-progress', 'pipe:1', '-nostats', f'frame_%08d.{image_format}']
    started = time.monotonic()
    updates = queue.Queue()
    stopped_at = None
    process = None
    error = None
    try:
        with (output / 'export.log').open('wb') as log:
            process = subprocess.Popen(command, cwd=output, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=log, **process_options())
            def read_progress():
                for line in iter(process.stdout.readline, b''):
                    updates.put(line.decode('utf-8', errors='replace').strip())
                updates.put(None)
            reader = threading.Thread(target=read_progress, daemon=True)
            reader.start()
            frame = 0
            seconds = 0.0
            ended = False
            while not ended:
                if cancel.is_set() and stopped_at is None:
                    stopped_at = time.monotonic()
                    try:
                        process.stdin.write(b'q\n')
                        process.stdin.flush()
                    except (OSError, ValueError):
                        pass
                if stopped_at is not None and time.monotonic() - stopped_at > 3 and process.poll() is None:
                    process.kill()
                try:
                    line = updates.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line is None:
                    ended = True
                    continue
                key, _, value = line.partition('=')
                if key == 'frame':
                    try:
                        frame = int(value)
                    except ValueError:
                        pass
                elif key == 'out_time_us':
                    try:
                        seconds = max(0, int(value) / 1000000)
                    except ValueError:
                        pass
                elif key == 'progress':
                    estimate = math.ceil(info['frames'] / step) if info['frames'] else 0
                    fraction = frame / estimate if estimate else seconds / info['duration'] if info['duration'] else 0
                    on_progress(dict(frames=frame, fraction=min(0.99, max(0, fraction)),
                                     elapsed=time.monotonic() - started))
            process.wait(timeout=10)
            reader.join(timeout=1)
            if process.returncode and not cancel.is_set():
                error = 'FFmpeg could not finish the export. See export.log in the export folder for details.'
    except Exception as exc:
        error = str(exc)
    finally:
        if process:
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdin:
                process.stdin.close()
            if process.stdout:
                process.stdout.close()
    count = sum(1 for file in output.glob(f'frame_*.{image_format}') if file.stat().st_size)
    status = 'failed' if error else 'cancelled' if cancel.is_set() else 'complete'
    if status == 'complete' and not count:
        error, status = 'The video produced no frames. See export.log for details.', 'failed'
    result = dict(status=status, folder=str(output), frames=count, elapsed=round(time.monotonic() - started, 2),
                  image_format=image_format, every_nth_frame=step, source=info['source'],
                  source_info=info, error=error, created_at=datetime.now().astimezone().isoformat())
    try:
        (output / 'export.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    except OSError as exc:
        result['error'] = f'Could not save export details: {exc}'
        if result['status'] == 'complete':
            result['status'] = 'failed'
    return result
