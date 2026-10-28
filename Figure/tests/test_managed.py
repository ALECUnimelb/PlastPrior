"""Reject invalid destinations/staging before any current result mutation."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'_shared'))
import managed

class ReplacementTests(TestCase):
    def test_arbitrary_destinations_cannot_touch_current_results(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);images=root/'images';data=root/'data'
            images.mkdir();data.mkdir()
            (images/'value').write_text('old image');(data/'value').write_text('old data')
            with self.assertRaisesRegex(ValueError,'fixed current'):
                managed.replace_pair(root/'stage',root/'tables',images,data)
            self.assertEqual((images/'value').read_text(),'old image')
            self.assertEqual((data/'value').read_text(),'old data')

    def test_missing_staging_cannot_start_publication(self):
        with TemporaryDirectory() as temp:
            result=Path(temp)/'result';result.mkdir()
            (result/'sentinel').write_text('keep')
            with patch.object(managed,'RESULT',result),self.assertRaises(FileNotFoundError):
                managed.replace_pair(Path(temp)/'missing',Path(temp)/'tables',result/'figures',result/'figure_data/Fig1')
            self.assertEqual([p.name for p in result.iterdir()],['sentinel'])
