import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from engine import Engine

class FinalSafety(unittest.TestCase):
    def test_resolved_root_accepts_equivalent_alias_path_but_rejects_escape(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);real=base/'private'/'library';real.mkdir(parents=True)
            alias=base/'library-alias';alias.symlink_to(real,target_is_directory=True)
            audio=alias/'door open.wav';audio.write_bytes(b'audio')
            e=Engine(alias,folder_style='en')
            try:
                self.assertEqual(str(e._relative(audio)),'door open.wav')
                with self.assertRaises(ValueError):e._relative(base/'outside.wav')
                self.assertEqual(e.fast()['moved'],1)
                self.assertTrue((real/'Foley & Household'/'Doors & Windows').is_dir())
            finally:e.close()
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
    def test_build_adds_missing_bundle_version_keys(self):
        build=(Path(__file__).parents[1]/'scripts/build_macos.sh').read_text(encoding='utf-8')
        self.assertIn('Print :${key}',build)
        self.assertIn('Add :${key} string ${value}',build)
        self.assertIn('set_plist_string CFBundleShortVersionString 5.0',build)
        self.assertIn('set_plist_string CFBundleVersion 100',build)
    def test_ci_preflights_native_architecture_dependencies_and_disk(self):
        workflow=(Path(__file__).parents[1]/'.github/workflows/macos-final.yml').read_text(encoding='utf-8')
        for required in ('macos-15-intel','actions/checkout@v5','actions/setup-python@v6',
                         'cache-dependency-path:', 'requirements-dev.txt', 'requirements-ai.txt',
                         'runner architecture mismatch','insufficient free disk',
                         'import torch, transformers, numpy, soundfile, scipy, PyInstaller'):
            self.assertIn(required,workflow)
        self.assertIn('- runner: macos-15\n',workflow)
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
