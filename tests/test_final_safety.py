import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from engine import Engine

class FinalSafety(unittest.TestCase):
    def test_release_audio_stage_never_creates_venv_or_installs_packages(self):
        gui=(Path(__file__).parents[1]/'src/gui.py').read_text(encoding='utf-8')
        analyzer=gui[gui.index('    def bundled_ai_worker'):gui.index('    def work(')]
        self.assertNotIn("'-m','venv'",analyzer)
        self.assertNotIn("'-m','pip'",analyzer)
        self.assertIn("Resources/ai_worker/ai_worker",analyzer)
    def test_packaged_app_has_non_destructive_launch_self_test(self):
        gui=(Path(__file__).parents[1]/'src/gui.py').read_text(encoding='utf-8')
        verify=(Path(__file__).parents[1]/'scripts/verify_delivery.sh').read_text(encoding='utf-8')
        self.assertIn("'--release-self-test' in sys.argv",gui)
        self.assertIn('--release-self-test',verify)
    def test_appledouble_is_not_an_attachment_and_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);audio=root/'wind.wav';audio.write_bytes(b'audio')
            side=root/'._wind.wav';side.write_bytes(b'metadata')
            e=Engine(root,folder_style='en')
            try:
                result=e.fast();self.assertEqual(result['moved'],1);self.assertEqual(result['attachments_moved'],0)
                backups=list((e.ctl/'Metadata_Backups').rglob('._wind.wav'))
                self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_bytes(),b'metadata')
                self.assertFalse(side.exists())
            finally:e.close()

    def test_missing_source_after_scan_is_reported_without_crash(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'wind.wav';p.write_bytes(b'audio');e=Engine(root)
            original=e.classify_batch
            def remove_after_classify(*args,**kwargs):
                rows=original(*args,**kwargs);p.unlink();return rows
            try:
                with patch.object(e,'classify_batch',side_effect=remove_after_classify):
                    result=e.fast()
                self.assertEqual(result['moved'],0);self.assertTrue(result['extras'])
            finally:e.close()

    def test_rejected_second_lock_closes_cleanly(self):
        with tempfile.TemporaryDirectory() as d:
            first=Engine(d)
            try:
                with self.assertRaises(BlockingIOError):Engine(d)
            finally:first.close()
