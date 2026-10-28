"""A failed data refresh must not replace any member of the current set."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'FigureCode/_shared'))
import preparation
import managed
from plastprior.result_storage import normalise_package

class PreparationTests(TestCase):
    def test_second_figure_failure_preserves_entire_result(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);result=root/'result'
            for name in ('Fig1','Fig2'):
                d=result/'figure_data'/name;d.mkdir(parents=True)
                (d/'counts.csv').write_text('n\n1\n')
            (result/'figures').mkdir();(result/'figures/Fig1.png').write_bytes(b'current figure')
            before=preparation.hashes(result)
            def run(command,**kwargs):
                stage=Path(command[-1])
                if stage.name=='Fig2':raise RuntimeError('second preparation failed')
                (stage/'source_data').mkdir()
                (stage/'source_data/counts.csv').write_text('n\n1\n')
                (stage/'source_data/plot_data.rds').write_bytes(b'new payload')
                (stage/'caption_facts.json').write_text('{}')
            with patch.object(preparation,'ROOT',root),patch.object(preparation,'RESULT',result), \
                 patch.object(preparation,'preparation_path',lambda n:result/'figure_data/_metadata'/n/'preparation.json'), \
                 patch.object(managed,'verify_sources',return_value={'files':{}}), \
                 patch.object(preparation,'code_hashes',return_value={}), \
                 patch.object(preparation.subprocess,'run',side_effect=run):
                with self.assertRaisesRegex(RuntimeError,'second preparation'):
                    preparation.prepare(('Fig1','Fig2'),check_existing=True)
            self.assertEqual(preparation.hashes(result),before)
            self.assertFalse((root/'.result-update.lock').exists())
            self.assertFalse(list(root.glob('.figure-prepare-*')))

    def test_corrupted_payload_is_rejected_before_render(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);result=root/'result';data=result/'figure_data/Fig1';data.mkdir(parents=True)
            (data/'plot_data.rds').write_bytes(b'valid payload')
            record={'source_data':preparation.hashes(data),'source':{'files':{}}}
            metadata=root/'preparation.json';metadata.write_text(json.dumps(record))
            (root/'FigureCode').mkdir();(root/'FigureCode/managed_sources.json').write_text('{"files":{}}')
            with patch.object(preparation,'ROOT',root),patch.object(preparation,'RESULT',result), \
                 patch.object(preparation,'preparation_path',return_value=metadata):
                preparation.verify_prepared('Fig1')
                (data/'plot_data.rds').write_bytes(b'corrupted payload')
                with self.assertRaisesRegex(ValueError,'inputs changed'):preparation.verify_prepared('Fig1')

    def test_manual_deck_name_survives_normalisation(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);deck=root/'Figures_rui_prepared.pptx';deck.write_bytes(b'edited deck')
            normalise_package(root)
            self.assertEqual(deck.read_bytes(),b'edited deck')
            self.assertEqual([p.name for p in root.iterdir()],[deck.name])
            (root/'Figures.pptx').write_bytes(b'duplicate')
            with self.assertRaisesRegex(ValueError,'one current presentation'):normalise_package(root)
