import unittest,tempfile,threading,errno
from pathlib import Path
from unittest.mock import patch
from engine import Engine,classify,Stopped
class Tests(unittest.TestCase):
    def test_boundaries(self):
        for n in ['catalog.wav','notificationless.wav','education.wav','20240901.wav']:
            self.assertIsNone(classify(Path(n)),n)
        self.assertEqual(classify(Path('door_open.wav'))['cat'],'Foley & Household/Doors & Windows')
        self.assertEqual(classify(Path('Footsteps.WAV'))['cat'],'Foley & Household/Footsteps')
    def test_two_stages_and_rename(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'door_open.wav').write_bytes(b'1'); (root/'123.wav').write_bytes(b'2')
            e=Engine(root)
            try:
                fast=e.fast(); self.assertEqual(fast['moved'],1); self.assertEqual(len(fast['pending']),1)
                self.assertTrue((root/'123.wav').exists())
                calls=[]
                def ai(p): calls.append(p); return {'accepted':True,'cat':'Animals','label':'Dog_Barking'}
                result=e.listen(fast['pending'],ai); self.assertEqual(result['moved'],1); self.assertEqual(len(calls),1)
                (root/'Foley & Household').rename(root/'擬音'); self.assertEqual(e.fast()['moved'],0)
                self.assertEqual(e.undo(),1); self.assertTrue((root/'123.wav').exists())
            finally: e.close()
    def test_cancel_before_move(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'wind.wav').write_bytes(b'a'); stop=threading.Event(); stop.set(); e=Engine(root,stop=stop)
            try:
                with self.assertRaises(Stopped): e.fast()
                self.assertTrue((root/'wind.wav').exists())
            finally: e.close()
    def test_legacy_processed_paths_rechecked_once(self):
        import json
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); ctl=root/'.soundfx_organizer'; ctl.mkdir()
            (root/'door.wav').write_bytes(b'old')
            (ctl/'database.json').write_text(json.dumps({'files':{'hash':{'lastKnownPath':'door.wav','category':'Foley/Doors'}}}))
            e=Engine(root)
            try:
                self.assertEqual(e.fast()['moved'],1)
                self.assertEqual(e.fast()['moved'],0)
                self.assertFalse((root/'door.wav').exists())
            finally:e.close()
    def test_exfat_fallback_and_restore(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'wind.wav').write_bytes(b'abc'*1000); e=Engine(root)
            try:
                with patch('engine.os.link',side_effect=OSError(errno.EOPNOTSUPP,'unsupported')):
                    self.assertEqual(e.fast()['moved'],1)
                    self.assertEqual(e.undo(),1)
                self.assertEqual((root/'wind.wav').read_bytes(),b'abc'*1000)
            finally: e.close()
    def test_macos_errno_45_external_drive_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'wind.wav').write_bytes(b'external-drive-data'*500);e=Engine(root)
            try:
                with patch('engine.os.link',side_effect=OSError(45,'Operation not supported')):
                    self.assertEqual(e.fast()['moved'],1)
                moved=next((root/'Nature & Weather/Wind').glob('*.wav'))
                self.assertEqual(moved.read_bytes(),b'external-drive-data'*500)
            finally:e.close()
    def test_stale_pre_move_journal_recovers_automatically(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'wind.wav';p.write_bytes(b'intact');e=Engine(root)
            try:
                sig=__import__('engine').signature(p);dest=e.destination(p,classify(p))
                e.db.execute("INSERT INTO moves(batch,src,dst,sig,status) VALUES(?,?,?,?,?)",('old',str(p),str(dest),sig,'moving'));e.db.commit()
            finally:e.close()
            e=Engine(root)
            try:
                self.assertEqual(e.db.execute("SELECT status FROM moves WHERE batch='old'").fetchone()[0],'failed')
                with patch('engine.os.link',side_effect=OSError(45,'Operation not supported')):
                    self.assertEqual(e.fast()['moved'],1)
                self.assertFalse(p.exists())
            finally:e.close()
    def test_collision_and_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'001.wav').write_bytes(b'a'); e=Engine(root)
            try:
                p=e.fast()['pending']; calls=[]
                def ai(x): calls.append(x); return {'accepted':False}
                e.listen(p,ai); e.listen(p,ai); self.assertEqual(len(calls),1)
                (root/'Wind').mkdir(); (root/'Wind/x.wav').write_bytes(b'existing')
                (root/'x.wav').write_bytes(b'new')
                target=e.destination(root/'x.wav',{'cat':'Wind','label':'x'})
                e.move(root/'x.wav',{'cat':'Wind','label':'x'},'test',expected=target)
                self.assertEqual((root/'Wind/x.wav').read_bytes(),b'existing')
                self.assertEqual(target.read_bytes(),b'new')
            finally: e.close()
    def test_1000_fast_without_audio(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for i in range(1000): (root/('door_%d.aif'%i)).write_bytes(str(i).encode())
            e=Engine(root)
            try:
                self.assertEqual(e.fast()['moved'],1000)
                self.assertEqual(e.fast()['moved'],0)
            finally: e.close()
if __name__=='__main__': unittest.main()
