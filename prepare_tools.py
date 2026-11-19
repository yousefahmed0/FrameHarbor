"""Download the official yt-dlp Windows release and verify its SHA256."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'FrameHarbor-build'}), timeout=120) as response:
        return response.read()


def prepare_downloader(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    executable = folder / 'yt-dlp.exe'
    metadata = folder / 'yt-dlp-release.json'
    cached = False
    if metadata.is_file() and executable.is_file():
        details = json.loads(metadata.read_text())
        cached = hashlib.sha256(executable.read_bytes()).hexdigest() == details['sha256']
    if not cached:
        release = json.loads(fetch('https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest'))
        assets = {asset['name']: asset['browser_download_url'] for asset in release['assets']}
        sums = fetch(assets['SHA2-256SUMS']).decode()
        expected = next(line.split()[0] for line in sums.splitlines() if line.split()[-1].lstrip('*') == 'yt-dlp.exe')
        data = fetch(assets['yt-dlp.exe'])
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError('Downloader checksum verification failed.')
        executable.write_bytes(data)
        details = {'version': release['tag_name'], 'url': assets['yt-dlp.exe'], 'sha256': expected}
        metadata.write_text(json.dumps(details, indent=2))
    for name in ('LICENSE', 'THIRD_PARTY_LICENSES.txt'):
        target = folder / f'yt-dlp-{name}'
        if not target.is_file():
            target.write_bytes(fetch(f'https://raw.githubusercontent.com/yt-dlp/yt-dlp/{details["version"]}/{name}'))
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js 22+ must be installed for the build.')
    version = subprocess.check_output([node, '--version'], text=True).strip()
    if int(version.lstrip('v').split('.')[0]) < 22:
        raise RuntimeError('Node.js 22+ is required.')
    (folder / 'Node-LICENSE.txt').write_bytes(fetch(f'https://raw.githubusercontent.com/nodejs/node/{version}/LICENSE'))
    return executable
