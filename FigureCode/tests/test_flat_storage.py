"""Publication must keep neighbouring figures and the image/data pair intact."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'FigureCode/_shared'))
import managed
import result_paths
from plastprior.result_storage import replace_directory

class FlatStorageTests(TestCase):
    def test_one_figure_update_preserves_other_figures_and_databases(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);result=root/'result'
            (result/'figures').mkdir(parents=True)
            (result/'figures/Fig1.png').write_bytes(b'old image')
            (result/'figures/Fig2.png').write_bytes(b'neighbour')
            (result/'PlastPrior_results.sqlite').write_bytes(b'unchanged database')
            data=result/'figure_data/Fig1';data.mkdir(parents=True)
            (data/'counts.csv').write_text('old table')
            meta=result/'figure_data/_metadata/Fig1';meta.mkdir(parents=True)
            (meta/'manifest.json').write_text(json.dumps({'outputs':{'Fig1.png':'old'}}))
            images=root/'new-images';images.mkdir()
            (images/'Fig1.png').write_bytes(b'new image')
            (images/'manifest.json').write_text(json.dumps({'outputs':{'Fig1.png':'new'},'status':'review'}))
            tables=root/'new-data';tables.mkdir();(tables/'counts.csv').write_text('new table')
            with patch.object(managed,'ROOT',root),patch.object(managed,'RESULT',result),patch.object(result_paths,'RESULT',result):
                managed.replace_pair(images,tables,result/'figures',data)
            self.assertEqual((result/'figures/Fig2.png').read_bytes(),b'neighbour')
            self.assertEqual((result/'PlastPrior_results.sqlite').read_bytes(),b'unchanged database')
            self.assertEqual((result/'figures/Fig1.png').read_bytes(),b'new image')
            self.assertEqual((data/'counts.csv').read_text(),'new table')
            self.assertEqual(json.loads((meta/'manifest.json').read_text())['status'],'review')
            self.assertFalse((result/'figures/manifest.json').exists())
            self.assertFalse(list(root.glob('.figure-install-*')))
            self.assertFalse(list(root.glob('.result-*')))

    def test_post_install_failure_restores_complete_previous_set(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);old=root/'result';new=root/'stage'
            old.mkdir();new.mkdir()
            (old/'data').write_text('old');(new/'data').write_text('new')
            def reject():raise ValueError('failed validation')
            with self.assertRaises(ValueError):replace_directory(new,old,validate=reject)
            self.assertEqual((old/'data').read_text(),'old')
            self.assertFalse((root/'.result-previous').exists())
