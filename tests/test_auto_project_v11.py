"""Run: python -m unittest discover -s tests -p 'test_auto_project_v11.py'"""
import tempfile
import unittest
from pathlib import Path
from auto_project_v11 import discover

class AutoProjectTests(unittest.TestCase):
    def test_shared_folder_and_nested_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("01 - Opening.mp3", "01 - Opening.txt",
                         "02 - Florence Ballard.wav", "02 - Florence Ballard.txt",
                         "photos/random_name.jpg", "footage/downloaded.mp4"):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"test")
            found = discover(root)
            self.assertEqual(sorted(found["voice"]), [1, 2])
            self.assertEqual(sorted(found["txt"]), [1, 2])
            self.assertEqual(len(found["images"]), 1)
            self.assertEqual(len(found["videos"]), 1)

    def test_missing_script_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "01 Opening.mp3").write_bytes(b"x")
            (root / "02 Next.mp3").write_bytes(b"x")
            (root / "01 Opening.txt").write_text("hi")
            (root / "image.jpg").write_bytes(b"x")
            with self.assertRaisesRegex(ValueError, "không khớp"):
                discover(root)

    def test_duplicate_voice_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("01 a.mp3", "01 b.wav", "01 a.txt", "image.jpg"):
                (root / name).write_bytes(b"x")
            found = discover(root)
            self.assertEqual(len(found["voice"]), 1)
            self.assertEqual(len(found["duplicates"]), 1)
            self.assertEqual(len(found["duplicates"][0]["ignored"]), 1)

if __name__ == "__main__":
    unittest.main()
