"""A failed figure/table swap must preserve the existing review pair."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'_shared'))
from managed import replace_pair


class ReplacementTests(unittest.TestCase):
    def make_dir(self, root, name, content):
        path = root/name
        path.mkdir()
        (path/'value').write_text(content)
        return path

    def test_success_replaces_both_and_removes_backups(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            images = self.make_dir(root, 'images', 'old image')
            data = self.make_dir(root, 'data', 'old data')
            new_images = self.make_dir(root, 'new_images', 'new image')
            new_data = self.make_dir(root, 'new_data', 'new data')
            replace_pair(new_images, new_data, images, data)
            self.assertEqual((images/'value').read_text(), 'new image')
            self.assertEqual((data/'value').read_text(), 'new data')
            self.assertEqual({p.name for p in root.iterdir()}, {'images', 'data'})

    def test_second_swap_failure_restores_both(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            images = self.make_dir(root, 'images', 'old image')
            data = self.make_dir(root, 'data', 'old data')
            new_images = self.make_dir(root, 'new_images', 'new image')
            with self.assertRaises(FileNotFoundError):
                replace_pair(new_images, root/'missing_stage', images, data)
            self.assertEqual((images/'value').read_text(), 'old image')
            self.assertEqual((data/'value').read_text(), 'old data')
            self.assertEqual({p.name for p in root.iterdir()}, {'images', 'data'})


if __name__ == '__main__':
    unittest.main()
