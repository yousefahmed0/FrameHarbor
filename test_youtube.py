import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from engine import ExportError, binary, process_options
from youtube import normalize_url, download, download_and_extract


class UrlTests(unittest.TestCase):
    def test_supported_links_and_playlist_removal(self):
        for value in ['https://www.youtube.com/watch?v=BaW_jenozKc&list=abc',
                      'youtu.be/BaW_jenozKc?t=3', 'https://m.youtube.com/shorts/BaW_jenozKc',
                      'https://youtube.com/embed/BaW_jenozKc', 'https://youtube.com/live/BaW_jenozKc']:
            self.assertEqual(normalize_url(value), 'https://www.youtube.com/watch?v=BaW_jenozKc')

    def test_reject_non_video_and_lookalike_links(self):
        for value in ['', 'https://youtube.com/playlist?list=123', 'https://youtube.com.evil.com/watch?v=BaW_jenozKc',
                      'https://youtube.com@evil.com/watch?v=BaW_jenozKc', 'file:///C:/video.mp4',
                      'https://youtube.com/watch?v=bad', 'https://youtu.be/BaW_jenozKc/other',
                      'https://youtube.com:443/watch?v=BaW_jenozKc']:
            with self.assertRaises(ExportError, msg=value):
                normalize_url(value)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='frameharbor-youtube-')
        self.root = Path(self.temp.name)
        self.video = self.root / 'fixture.mp4'
        subprocess.run([binary('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=96x64:rate=10:duration=1', '-c:v', 'mpeg4', str(self.video)],
                       check=True, capture_output=True, **process_options())
        self.fake = self.root / 'downloader.py'

    def tearDown(self):
        self.temp.cleanup()

    def fake_downloader(self, content):
        self.fake.write_text(content, encoding='utf-8')
        return patch('youtube.downloader_command', return_value=[sys.executable, str(self.fake), str(self.video)])

    def test_download_to_extraction_pipeline(self):
        code = '''import json, shutil, sys
from pathlib import Path
print('TITLE ' + json.dumps('Test video'), flush=True)
print('PROGRESS 50 100 NA 20 3', flush=True)
shutil.copyfile(sys.argv[1], 'source.mp4')
print('FILE ' + json.dumps(str(Path('source.mp4').resolve())), flush=True)
'''
        events = []
        with self.fake_downloader(code):
            result = download_and_extract('youtu.be/BaW_jenozKc', self.root / 'out % اختبار', 'png', 1,
                                          threading.Event(), lambda kind, data: events.append((kind, data)))
        self.assertEqual(result['status'], 'complete', result)
        self.assertEqual(result['frames'], 10)
        self.assertIn('download_progress', [event[0] for event in events])
        self.assertIn('youtube_ready', [event[0] for event in events])
        self.assertTrue(list((self.root / 'out % اختبار' / 'YouTube downloads').glob('*/source.mp4')))
        manifest = json.loads((Path(result['folder']) / 'export.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['source_info']['webpage_url'], 'https://www.youtube.com/watch?v=BaW_jenozKc')

    def test_cancel_download_stops_before_extraction(self):
        code = "import time\nprint('PROGRESS 5 100 NA 1 99', flush=True)\ntime.sleep(30)\n"
        event = threading.Event()
        with self.fake_downloader(code):
            result = download_and_extract('youtu.be/BaW_jenozKc', self.root, 'png', 1, event,
                                          lambda kind, data: event.set() if kind == 'download_progress' else None)
        self.assertEqual(result['status'], 'cancelled', result)
        self.assertEqual(result['frames'], 0)
        self.assertFalse(list(self.root.glob('*_frames_*')))

    def test_download_failure_reports_cause(self):
        with self.fake_downloader("import sys\nprint('ERROR: Video unavailable', flush=True)\nsys.exit(1)\n"):
            result = download('youtu.be/BaW_jenozKc', self.root, threading.Event())
        self.assertEqual(result['status'], 'failed')
        self.assertIn('Video unavailable', result['error'])
        self.assertTrue((Path(result['folder']) / 'download.log').exists())

    def test_cancel_before_start_does_not_create_folders(self):
        event = threading.Event()
        event.set()
        result = download('youtu.be/BaW_jenozKc', self.root / 'unused', event)
        self.assertEqual(result['status'], 'cancelled')
        self.assertFalse((self.root / 'unused').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
