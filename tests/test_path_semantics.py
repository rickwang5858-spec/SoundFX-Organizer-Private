import errno, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from categories import classify, standardized_stem, RULE_VERSION
from engine import Engine, signature, DOC_ROOT
from low_quality import candidates as quality_candidates

class PathSemantics(unittest.TestCase):
    CASES={
      'audiojungle-23727863-desert-wind/Track_01.wav':'Nature & Weather/Wind',
      'battling-knights-2026-05-18-18-45-48-utc/Track_01.wav':'Weapons & Combat/Blades & Combat',
      'Bike bells/Bike Bell 1.wav':'Transportation & Traffic/Bicycle & Motorcycle',
      'chimes-2025-08-27-06-41-41-utc/Track_01.wav':'Bells, Alarms & Technology/Bells & Chimes',
      'Christmas Urban Street Ambience/Track_01.wav':'Ambience & Environments/City & Street',
      'christmas/Christmas Transition.mp3':'Music & Seasonal/Christmas',
      'christmas-bell-tree/Christmas Bell Tree.mp3':'Music & Seasonal/Christmas',
      'city people talking/Track_01.wav':'People & Crowds/People & Reactions',
      'correct-answer-chime-01/Track_01.wav':'Bells, Alarms & Technology/UI & Notifications',
      'Door Bell/BELL-DOOR_GEN-HDF-03339.wav':'Bells, Alarms & Technology/Doorbells',
      'door-opening/opening-door.wav':'Foley & Household/Doors & Windows',
      'droplet/Droplet 1.mp3':'Nature & Weather/Water',
      'fire/Track 01.wav':'Nature & Weather/Fire',
      'heartbeat/Heartbeat.mp3':'People & Crowds/Body & Heartbeat',
      'Leaves/Autumn Leaves Rustle 01.wav':'Nature & Weather/Leaves & Vegetation',
      'light-a-match/Light A Match.mp3':'Foley & Household/Matches & Ignition',
      'Magic Whoosh/Track_01.wav':'Designed & Cinematic/Magic & Fantasy',
      'match-ignition/20089 match ignition-full.mp3':'Foley & Household/Matches & Ignition',
      'match-strike/Matches_Movement_OCP-1284-011.wav':'Foley & Household/Matches & Ignition',
      'Mountain Audio - Autumn Breeze/wav/Track 01.wav':'Nature & Weather/Wind',
      'Mountain Audio - Fairy Dust/mp3/Track 01.mp3':'Designed & Cinematic/Magic & Fantasy',
      'Needle On Record/Needle On Record.mp3':'Music & Seasonal/Vinyl & Turntables',
      'Ocean Beach Sea/Track 01.wav':'Nature & Weather/Ocean, Underwater & Waves',
      'Ocean Wave/Track 01.wav':'Nature & Weather/Ocean, Underwater & Waves',
      'page-turning/page wav/Mountain Audio - Book Pages Turning - Sound 7.wav':'Foley & Household/Paper & Books',
      'park-ambience/Track 01.wav':'Ambience & Environments/Parks & Outdoor',
      'Pirate Laughing And Drinking/Pirate Laughing And Drinking.wav':'People & Crowds/People & Reactions',
      'Pirate Ship Sailing Ambience/Pirate Ship Sailing Ambience 2.mp3':'Ambience & Environments/Ocean & Watercraft',
      'Pirate_Chest_OCM-0018-334.wav':'Foley & Household/Containers & Objects',
      'pirate-character-pack/Land Ahoy.wav':'People & Crowds/Shouts & Reactions',
      'Rain & Thunder/Track_01.wav':'Nature & Weather/Rain & Thunder',
      'ReactionChildren AR04_78_1.wav':'People & Crowds/People & Reactions',
      'residential-park-area/LDj_Audio_ResidentialParkArea_V3.wav':'Ambience & Environments/Parks & Outdoor',
      'Sleigh Bell Loop SFX/Track_01.wav':'Music & Seasonal/Christmas',
      'sleigh-bells/Sleigh Bells 04.wav':'Music & Seasonal/Christmas'}

    def test_every_readable_screenshot_case(self):
        for name,expected in self.CASES.items():
            with self.subTest(name=name):
                r=classify(Path(name)); self.assertIsNotNone(r); self.assertEqual(r['cat'],expected)

    def test_variants_are_semantic_not_full_filename_hardcoding(self):
        variants=['DESERT_WIND.aif','packs/Desert-Winds/track-9.flac','packs/desert winds/SOUND_03.MP3']
        for name in variants:self.assertEqual(classify(Path(name))['cat'],'Nature & Weather/Wind')
        self.assertEqual(classify(Path('Fairy Dust/wav/SWORD-clash-02.wav'))['cat'],'Weapons & Combat/Blades & Combat')

    def test_generic_child_inherits_pack_and_specific_child_overrides(self):
        generic=Path('Mountain Audio - Fairy Dust/mp3/Track 01.mp3')
        specific=Path('Mountain Audio - Fairy Dust/mp3/door opening 02.mp3')
        self.assertEqual(classify(generic)['cat'],'Designed & Cinematic/Magic & Fantasy')
        self.assertEqual(classify(specific)['cat'],'Foley & Household/Doors & Windows')

    def test_standard_name_removes_vendor_date_catalog_and_preserves_sequence(self):
        p=Path('audiojungle-123456-page-turning-2026-05-18-11-21-46-utc/Mountain Audio - Book Pages Turning - Sound 7.wav')
        stem=standardized_stem(p,classify(p))
        self.assertEqual(stem,'Page_Turning_Book_Pages_007')
        self.assertNotRegex(stem.lower(),r'audiojungle|mountain|utc|123456')

    def test_christmas_city_keeps_secondary_tag(self):
        r=classify(Path('Christmas Urban Street Ambience/Track_01.wav'))
        self.assertEqual(r['cat'],'Ambience & Environments/City & Street'); self.assertIn('Christmas',r['tags'])

class EngineUpgrade(unittest.TestCase):
    def test_full_screenshot_tree_one_click_and_second_run_is_noop(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); base=root/'0Hollywood Sound FX'
            for rel in PathSemantics.CASES:
                p=base/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(rel.encode())
            (base/'Magic Whoosh/information.pdf').write_bytes(b'pdf')
            (base/'door-opening/Readme - Thank You.txt').write_text('license')
            e=Engine(root)
            try:
                first=e.fast(); self.assertEqual(first['moved'],len(PathSemantics.CASES)); self.assertEqual(first['attachments_moved'],2); self.assertEqual(first['pending'],[])
                self.assertFalse(base.exists()); self.assertEqual(len(list(root.rglob('*.wav')))+len(list(root.rglob('*.mp3')))+len(list(root.rglob('*.aif')))+len(list(root.rglob('*.flac'))),len(PathSemantics.CASES))
                second=e.fast(); self.assertEqual(second['moved'],0); self.assertEqual(second['attachments_moved'],0); self.assertEqual(second['skipped'],len(PathSemantics.CASES))
            finally:e.close()

    def test_old_rule_record_is_rechecked_then_current_record_is_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'female-steps-slow/Track_01.wav'; p.parent.mkdir(); p.write_bytes(b'feet')
            e=Engine(root)
            try:
                sig=signature(p); e.db.execute('INSERT INTO seen VALUES(?,?)',(sig,str(p)))
                e.db.execute('INSERT INTO file_rules VALUES(?,?)',(sig,RULE_VERSION-1)); e.db.commit()
                first=e.fast(); self.assertEqual(first['moved'],1)
                moved=list(root.glob('Foley & Household/Footsteps/*.wav')); self.assertEqual(len(moved),1)
                self.assertEqual(e.fast()['moved'],0)
            finally:e.close()

    def test_current_identity_survives_manual_category_rename(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'door open.wav').write_bytes(b'x'); e=Engine(root)
            try:
                self.assertEqual(e.fast()['moved'],1); old=root/'Foley & Household'; new=root/'我改過的擬音分類'; old.rename(new)
                self.assertEqual(e.fast()['moved'],0); self.assertTrue(next(new.rglob('*.wav')).exists())
            finally:e.close()

    def test_attachments_consolidated_empty_tree_removed_and_undo_restores(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); pack=root/'0Hollywood Sound FX/page-turning/page wav'; pack.mkdir(parents=True)
            (pack/'Turning Pages 01.wav').write_bytes(b'audio'); (pack/'Readme - Thank You.txt').write_text('license'); (pack/'cover.xyz').write_bytes(b'cover')
            e=Engine(root)
            try:
                r=e.fast(); self.assertEqual(r['moved'],1); self.assertEqual(r['attachments_moved'],2); self.assertEqual(len(r['attachments']),2)
                self.assertFalse((root/'0Hollywood Sound FX').exists())
                docs=root/DOC_ROOT; self.assertTrue(next(docs.rglob('Readme - Thank You.txt')).exists()); self.assertTrue(next(docs.rglob('cover.xyz')).exists())
                self.assertEqual(e.undo(),3); self.assertTrue((pack/'Turning Pages 01.wav').exists()); self.assertTrue((pack/'Readme - Thank You.txt').exists())
            finally:e.close()

    def test_renamed_lossless_lossy_versions_still_pair(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); pack=root/'heartbeat'; pack.mkdir(); (pack/'Heartbeat.wav').write_bytes(b'high'); (pack/'Heartbeat.mp3').write_bytes(b'low')
            e=Engine(root)
            try:
                self.assertEqual(e.fast()['moved'],2); pairs=quality_candidates(e.scan()); self.assertEqual(len(pairs),1)
                self.assertEqual(pairs[0][0].stem,pairs[0][1].stem)
            finally:e.close()

    def test_missing_source_stops_without_creating_destination(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'door.wav'; p.write_bytes(b'x'); e=Engine(root)
            try:
                dest=e.destination(p,classify(p)); p.unlink()
                with self.assertRaises(FileNotFoundError):e.move(p,{'cat':'Foley & Household/Doors & Windows','label':'Door'},'test',expected=dest)
                self.assertFalse(dest.exists())
            finally:e.close()

    def test_launcher_has_both_standard_intel_and_apple_silicon_python_paths(self):
        launcher=Path(__file__).parents[1]/'MacOS/SoundFX4'; text=launcher.read_text()
        self.assertIn('/opt/homebrew/bin/python3',text); self.assertIn('/usr/local/bin/python3',text)

if __name__=='__main__':unittest.main()
