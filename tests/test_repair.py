import unittest,tempfile,json
from pathlib import Path
from engine import Engine,classify,signature
from categories import audio_category

LONG='AMBISONIC_A_EXT_Lightly_Travelled_Urban_Street_in_Summer_Some_Close_Cars_on_77_Abruyn_Str_STEREO.wav'
class Regression(unittest.TestCase):
    def test_user_examples(self):
        for name in ['City_Traffic_Track_03.mp3',LONG,'Ambience/City_Traffic_Track_03.mp3']:
            self.assertEqual(classify(Path(name))['cat'],'Ambience & Environments/City & Street',name)
        for name in ['female-steps-slow-2025-08-27-06-25-33-utc.wav','female-steps-slow-2025-08-27-06-25-33-utc/Track_01.aif']:
            r=classify(Path(name)); self.assertEqual(r['cat'],'Foley & Household/Footsteps'); self.assertEqual(r['label'],'Footsteps_Female_Slow')
    def test_subject_priority(self):
        cases={'door-bell.wav':'Bells, Alarms & Technology/Doorbells','campfire-night-wind.wav':'Nature & Weather/Fire','fork-on-plate-clink.wav':'Foley & Household/Kitchen & Dishes','Car_Engine.wav':'Transportation & Traffic/Cars','forest-birds.wav':'Ambience & Environments/Nature'}
        for name,cat in cases.items(): self.assertEqual(classify(Path(name))['cat'],cat,name)
        self.assertEqual(audio_category({'label':'Door_Close','cat':'Foley/Doors'})['cat'],'Foley & Household/Doors & Windows')
    def test_numbered_pack(self):
        name=Path('0Hollywood Sound FX/08 - Traffic, Sirens, Motors & Busses/Track_03.mp3')
        self.assertEqual(classify(name)['cat'],'Transportation & Traffic/Mixed Traffic & Engines')
        name=Path('0Hollywood Sound FX/05 - Rain, Thunder, Fire, Bubbles/Track_01.wav')
        self.assertEqual(classify(name)['cat'],'Nature & Weather/Mixed Natural Sounds')
    def test_repair_seen_preview_apply_and_idempotence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'Ambience').mkdir(); old=root/'Ambience/City_Traffic_Track_03.mp3'; old.write_bytes(b'unchanged')
            (root/LONG).write_bytes(b'long')
            pack=root/'female-steps-slow-2025-08-27-06-25-33-utc'; pack.mkdir(); (pack/'Track_01.wav').write_bytes(b'feet')
            h=root/'0Hollywood Sound FX/08 - Traffic, Sirens, Motors & Busses'; h.mkdir(parents=True); (h/'Track_03.mp3').write_bytes(b'pack')
            e=Engine(root)
            try:
                e.db.execute('INSERT INTO seen VALUES(?,?)',(signature(old),str(old))); e.db.commit()
                rows,pending=e.repair_plan(); self.assertEqual(len(rows),4); self.assertTrue(old.exists())
                e.apply_repair(rows,pending)
                self.assertEqual(e.repair_plan()[0],[])
                self.assertEqual(e.fast()['moved'],0)
                for row in rows:self.assertTrue(Path(row['dst']).exists())
                self.assertEqual(e.undo(),4); self.assertTrue(old.exists()); self.assertEqual(old.read_bytes(),b'unchanged')
            finally:e.close()
    def test_changed_after_preview(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'city_traffic.wav'; p.write_bytes(b'x'); e=Engine(root)
            try:
                rows,pending=e.repair_plan(); p.write_bytes(b'new data')
                with self.assertRaises(ValueError):e.apply_repair(rows,pending)
                self.assertEqual(p.read_bytes(),b'new data')
            finally:e.close()
    def test_no_prefix_accumulation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); e=Engine(root)
            try:
                p=root/'City_Street_city_traffic.wav'; p.write_bytes(b'x')
                r=classify(p); target=e.destination(p,r)
                self.assertEqual(target.name,'City_Street_Traffic_001.wav')
                target.parent.mkdir(parents=True); target.write_bytes(b'x')
                self.assertEqual(e.destination(target,classify(target.relative_to(root))).name,target.name)
            finally:e.close()
if __name__=='__main__':unittest.main()
