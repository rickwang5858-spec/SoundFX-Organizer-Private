import json, os, struct, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from categories import classify, is_generic, RULE_VERSION
from engine import Engine
from metadata_text import extract
from i18n import I18n

class ScreenshotRegressionV5(unittest.TestCase):
    CASES={
      'attach-metal-items-2025-08-27-06-33-29-utc/Attach Metal Item 02.wav':'Foley & Household/Metal Objects & Handling',
      'audiojungle-14645859-crystal/Crystal.mp3':'Designed & Cinematic/Shimmer, Sparkle & Crystal',
      'match-2025-08-27-06-33-29-utc/Match.mp3':'Foley & Household/Matches & Ignition',
      'Ocean Beach Sea/AmbienceUnderw UWT01_29.1.wav':'Nature & Weather/Ocean, Underwater & Waves',
      'Running Steps/Track 01.wav':'Foley & Household/Footsteps',
      'soda fizz/LiquidPourWFizzLiq AC019201.wav':'Foley & Household/Drinks, Pouring & Fizz',
      'pouring-soda/LG_Sound - Pouring Soda (Mp3).mp3':'Foley & Household/Drinks, Pouring & Fizz',
      'sparkle/Sparkle 1.mp3':'Designed & Cinematic/Shimmer, Sparkle & Crystal',
      'Sparkles/Sparkle Pop 01.wav':'Designed & Cinematic/Shimmer, Sparkle & Crystal',
      'Static Vinyl Crackling/Static Vinyl 1.wav':'Music & Seasonal/Vinyl & Turntables',
      'stone door/Stone Door 01.wav':'Foley & Household/Doors & Windows',
      'stone-insert-in-stone/Stone Insert in Stone 03.wav':'Foley & Household/Stone Objects & Mechanisms',
      'Underwater Atmosphere SFX/Vehicle_Window_ODY-1156-024.wav':'Transportation & Traffic/Vehicle Interior & Components',
      'Underwater Atmosphere SFX/Wndw Slide Close.wav':'Foley & Household/Doors & Windows',
      'Underwater Atmosphere SFX/Wood_Stick_Break_ODY-1169-018.wav':'Impacts & Destruction/Wood Breaks',
      'wooden-sticks-fighting/25664 wooden sticks fighting-full.wav':'Weapons & Combat/Staff & Stick Combat',
      'wooden-sticks-fighting/WoodRattle_DIGIJ08-59-03.wav':'Foley & Household/Wood Objects',
      '溫泉/SR019MS.WAV':'Nature & Weather/Hot Springs & Geothermal'}
    def test_all_readable_cases(self):
        for path,expected in self.CASES.items():
            with self.subTest(path=path):self.assertEqual(classify(Path(path))['cat'],expected)
    def test_inflections_separators_camelcase_and_tags(self):
        self.assertEqual(classify(Path('AttachMetalObjects/track-9.wav'))['cat'],'Foley & Household/Metal Objects & Handling')
        r=classify(Path('female-running_steps/Track_01.aif'));self.assertEqual(r['cat'],'Foley & Household/Footsteps');self.assertIn('Running',r['tags'])
        self.assertTrue(is_generic('SR019MS'))
    def test_explicit_filename_overrides_wrong_parent(self):
        cases={'Vehicle_Window.wav':'Transportation & Traffic/Vehicle Interior & Components','Wndw Slide Close.wav':'Foley & Household/Doors & Windows','Wood Stick Break.wav':'Impacts & Destruction/Wood Breaks'}
        for name,expected in cases.items():self.assertEqual(classify(Path('Underwater Atmosphere SFX')/name)['cat'],expected)
        self.assertEqual(classify(Path('Underwater Atmosphere SFX/SR019MS.wav'))['cat'],'Nature & Weather/Ocean, Underwater & Waves')
    def test_ambiguous_counterexamples_remain_unclassified(self):
        for name in ('Catalog_2026.wav','FX_001.wav','Track_09.mp3','final-final-02.aif'):self.assertIsNone(classify(Path(name)))

class MetadataAndConsensus(unittest.TestCase):
    def _wav(self,text):
        payload=text.encode()+b'\0';chunk=b'bext'+struct.pack('<I',len(payload))+payload+(b'\0' if len(payload)&1 else b'')
        body=b'WAVE'+chunk
        return b'RIFF'+struct.pack('<I',len(body))+body
    def _id3(self,text):
        payload=b'\x03'+text.encode();frame=b'TIT2'+len(payload).to_bytes(4,'big')+b'\0\0'+payload;n=len(frame)
        safe=bytes([(n>>21)&127,(n>>14)&127,(n>>7)&127,n&127]);return b'ID3\x03\0\0'+safe+frame
    def test_bwf_and_id3_text_are_used_without_audio_decode(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);w=root/'X001.wav';m=root/'X002.mp3';w.write_bytes(self._wav('door opening wood'));m.write_bytes(self._id3('desert wind gust'))
            self.assertTrue(any('door opening' in t for _,t in extract(w)))
            e=Engine(root)
            try:
                self.assertEqual(e.classify_fast(w)['cat'],'Foley & Household/Doors & Windows')
                self.assertEqual(e.classify_fast(m)['cat'],'Nature & Weather/Wind')
            finally:e.close()
    def test_finder_tag_text_source(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'Q001.wav';p.write_bytes(b'x');e=Engine(root)
            try:
                with patch('engine.extract_metadata',return_value=[('Finder Tags','ocean underwater ambience')]):
                    self.assertEqual(e.classify_fast(p)['cat'],'Nature & Weather/Ocean, Underwater & Waves')
            finally:e.close()
    def test_package_consensus_only_for_generic_siblings(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pack=root/'Vendor Collection';pack.mkdir()
            files=[]
            for n in ('Door Open Wood 1.wav','Door Close Wood 2.wav','Opening Door 3.wav','Door Open 4.wav','Track 09.wav'):
                p=pack/n;p.write_bytes(b'x');files.append(p)
            e=Engine(root)
            try:
                rows=e.classify_batch(files);last=rows[-1]['result'];self.assertEqual(last['cat'],'Foley & Household/Doors & Windows');self.assertEqual(last['reason_code'],'package_consensus')
            finally:e.close()
    def test_mixed_pack_does_not_force_consensus(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pack=root/'Mixed FX Library';pack.mkdir();files=[]
            for n in ('Door Open.wav','Desert Wind.wav','Dog Bark.wav','Track 01.wav'):
                p=pack/n;p.write_bytes(b'x');files.append(p)
            e=Engine(root)
            try:self.assertIsNone(e.classify_batch(files)[-1]['result'])
            finally:e.close()
    def test_readme_context_only_helps_generic_track(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pack=root/'Vendor Pack';pack.mkdir();audio=pack/'Track 01.wav';readme=pack/'README.txt';audio.write_bytes(b'x');readme.write_text('A collection of rain and thunder recordings.')
            e=Engine(root)
            try:self.assertEqual(e.classify_batch([audio],[readme])[0]['result']['cat'],'Nature & Weather/Rain & Thunder')
            finally:e.close()
    def test_full_simulated_library_first_run_rerun_audit_and_undo(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);base=root/'Incoming Download'
            for rel in ScreenshotRegressionV5.CASES:
                p=base/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(rel.encode('utf-8'))
            meta=base/'Metadata Pack/Q001.wav';meta.parent.mkdir(parents=True);meta.write_bytes(self._wav('door opening'))
            (base/'Metadata Pack/license.txt').write_text('MIT-style sample license')
            e=Engine(root)
            try:
                first=e.fast();self.assertEqual(first['moved'],len(ScreenshotRegressionV5.CASES)+1);self.assertEqual(first['pending'],[]);self.assertEqual(first['attachments_moved'],1)
                audit=root/'.soundfx_organizer/分類判斷紀錄.csv';self.assertTrue(audit.exists());self.assertIn('規則版本',audit.read_text('utf-8-sig'))
                second=e.fast();self.assertEqual(second['moved'],0);self.assertEqual(second['skipped'],len(ScreenshotRegressionV5.CASES)+1)
                self.assertEqual(e.undo(),len(ScreenshotRegressionV5.CASES)+2);self.assertTrue(meta.exists())
            finally:e.close()

class LocalRulesAndLanguage(unittest.TestCase):
    def test_local_rule_roundtrip_enable_and_scope(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'Zappular Motion.wav';p.write_bytes(b'x');e=Engine(root)
            try:
                e.custom.add('zappular motion','Designed & Cinematic/Sci-Fi','SciFi_Motion')
                self.assertEqual(e.classify_fast(p)['reason_code'],'custom_rule')
                exported=root/'rules-export.json';e.custom.export_to(exported);self.assertIn('zappular motion',exported.read_text())
                e.custom.rows[0]['enabled']=False;e.custom.save();self.assertIsNone(e.classify_fast(p))
            finally:e.close()
    def test_external_language_resources_and_live_switch(self):
        i=I18n('en');self.assertEqual(i.t('choose'),'Choose Sound Library');i.set('zh-Hant');self.assertEqual(i.t('choose'),'選擇音效庫')
        self.assertTrue((i.base/'en.json').exists())
    def test_rule_version_upgraded(self):self.assertGreaterEqual(RULE_VERSION,6)

if __name__=='__main__':unittest.main()
