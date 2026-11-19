import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

from PIL import Image
from engine import binary, probe, thumbnail, extract, ExportError, process_options


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='frameharbor-')
        cls.root = Path(cls.temp.name)
        cls.video = cls.root / 'clip % with spaces اختبار.mp4'
        cls.run_ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=160x96:rate=12:duration=2',
                       '-c:v', 'mpeg4', str(cls.video))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @staticmethod
    def run_ffmpeg(*args):
        subprocess.run([binary('ffmpeg'), '-v', 'error', '-y', *args], check=True,
                       capture_output=True, **process_options())

    def test_png_every_frame_and_jpg_sampling(self):
        info = probe(self.video)
        self.assertEqual(info['frames'], 24)
        self.assertEqual((info['width'], info['height']), (160, 96))
        self.assertTrue(thumbnail(info).startswith(b'\x89PNG'))
        for fmt, step, expected in [('png', 1, 24), ('jpg', 5, 5)]:
            progress = []
            result = extract(info, self.root / 'output % اختبار', fmt, step, threading.Event(), progress.append)
            self.assertEqual(result['status'], 'complete', result)
            self.assertEqual(result['frames'], expected)
            files = sorted(Path(result['folder']).glob(f'frame_*.{fmt}'))
            self.assertEqual(files[0].name, f'frame_00000001.{fmt}')
            self.assertEqual(files[-1].name, f'frame_{expected:08d}.{fmt}')
            for image in files:
                with Image.open(image) as decoded:
                    self.assertEqual(decoded.size, (160, 96))
                    decoded.verify()
            self.assertTrue(progress)
            manifest = json.loads((Path(result['folder']) / 'export.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['frames'], expected)

    def test_unique_folders_preserve_previous_export(self):
        info = probe(self.video)
        first = extract(info, self.root, 'jpg', 30, threading.Event())
        marker = Path(first['folder']) / 'keep.txt'
        marker.write_text('keep')
        second = extract(info, self.root, 'jpg', 30, threading.Event())
        self.assertNotEqual(first['folder'], second['folder'])
        self.assertEqual(marker.read_text(), 'keep')

    def test_variable_frame_rate_no_duplicates(self):
        source = self.root / 'variable.mkv'
        self.run_ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=96x64:rate=10:duration=2',
                        '-vf', 'select=not(mod(n\\,3))', '-fps_mode', 'vfr', '-c:v', 'ffv1', str(source))
        info = probe(source)
        result = extract(info, self.root, 'png', 1, threading.Event())
        self.assertEqual(result['status'], 'complete', result)
        self.assertEqual(result['frames'], 7)

    def test_cancel_during_export_keeps_valid_frames(self):
        source = self.root / 'long.mp4'
        self.run_ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=1280x720:rate=30:duration=20',
                        '-c:v', 'mpeg4', str(source))
        event = threading.Event()
        result = extract(probe(source), self.root, 'png', 1, event, lambda _: event.set())
        self.assertEqual(result['status'], 'cancelled', result)
        self.assertGreater(result['frames'], 0)
        self.assertLess(result['frames'], 600)
        for file in Path(result['folder']).glob('frame_*.png'):
            with Image.open(file) as image:
                image.verify()

    def test_cancel_before_start_creates_nothing(self):
        event = threading.Event()
        event.set()
        result = extract(probe(self.video), self.root / 'unused', 'png', 1, event)
        self.assertIsNone(result['folder'])
        self.assertFalse((self.root / 'unused').exists())

    def test_invalid_video_audio_only_and_unwritable_destination(self):
        corrupt = self.root / 'broken.mp4'
        corrupt.write_text('not a video')
        with self.assertRaises(ExportError):
            probe(corrupt)
        audio = self.root / 'audio.wav'
        self.run_ffmpeg('-f', 'lavfi', '-i', 'sine=duration=0.1', str(audio))
        with self.assertRaisesRegex(ExportError, 'video stream'):
            probe(audio)
        with self.assertRaises(OSError):
            extract(probe(self.video), corrupt, 'png', 1, threading.Event())


if __name__ == '__main__':
    unittest.main(verbosity=2)
