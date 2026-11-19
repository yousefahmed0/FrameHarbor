"""Build a portable Windows folder; FFmpeg must be on PATH."""
from pathlib import Path
import shutil
import subprocess
import sys
from prepare_tools import prepare_downloader

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT.parent
WORK = OUTPUTS.parent / 'work' / 'build'
assets = ROOT / 'assets'
assets.mkdir(exist_ok=True)
icon = Image.new('RGBA', (256, 256), '#101719')
draw = ImageDraw.Draw(icon)
draw.rounded_rectangle((20, 20, 236, 236), radius=48, fill='#192326')
draw.rounded_rectangle((51, 65, 205, 191), radius=14, outline='#b5f3cd', width=8)
for y in (82, 112, 142, 172):
    for x in (63, 180):
        draw.rectangle((x, y, x + 11, y + 10), fill='#b5f3cd')
draw.polygon(((109, 98), (109, 158), (153, 128)), fill='#b5f3cd')
icon.save(assets / 'app.ico', sizes=[(16, 16), (32, 32), (48, 48), (128, 128), (256, 256)])
args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed',
        '--name', 'FrameHarbor', '--icon', str(assets / 'app.ico'), '--add-data', f'{assets}:assets',
        '--distpath', str(OUTPUTS), '--workpath', str(WORK), '--specpath', str(WORK)]
downloader = prepare_downloader(OUTPUTS.parent / 'work' / 'vendor')
args += ['--add-binary', f'{downloader}:tools']
node = shutil.which('node')
if not node:
    raise SystemExit('Node.js 22+ must be on PATH to build YouTube support.')
args += ['--add-binary', f'{Path(node).resolve()}:tools']
for name in ('ffmpeg', 'ffprobe'):
    found = shutil.which(name)
    if not found:
        raise SystemExit(f'{name} is missing from PATH.')
    args += ['--add-binary', f'{Path(found).resolve()}:tools']
args.append(str(ROOT / 'app.py'))
subprocess.run(args, check=True, cwd=ROOT)
destination = OUTPUTS / 'FrameHarbor'
shutil.copy2(ROOT / 'README.md', destination / 'README.txt')
licenses = destination / 'licenses'
licenses.mkdir(exist_ok=True)
ffmpeg_root = Path(shutil.which('ffmpeg')).resolve().parent.parent
for filename in ('LICENSE', 'README.txt'):
    source = ffmpeg_root / filename
    if source.is_file():
        shutil.copy2(source, licenses / f'FFmpeg-{filename}')
shutil.copy2(Path(sys.base_prefix) / 'LICENSE.txt', licenses / 'Python-LICENSE.txt')
vendor = downloader.parent
for name in ('yt-dlp-LICENSE', 'yt-dlp-THIRD_PARTY_LICENSES.txt', 'yt-dlp-release.json', 'Node-LICENSE.txt'):
    shutil.copy2(vendor / name, licenses / name)
print(f'Application ready: {destination / "FrameHarbor.exe"}')
