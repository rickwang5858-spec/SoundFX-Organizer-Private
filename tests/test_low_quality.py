import tempfile,unittest,shutil,wave,math,struct
from pathlib import Path
from unittest.mock import patch
import low_quality
from engine import Engine

def tone(p,freq=440,seconds=3):
    rate=8000; data=[int(12000*math.sin(2*math.pi*freq*i/rate)) for i in range(rate*seconds)]
    with wave.open(str(p),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes(struct.pack('<%dh'%len(data),*data))

class Quality(unittest.TestCase):
    def test_pairing_is_conservative(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td)
            for n in ['Rain_HQ.wav','Rain_LQ_128kbps.mp3','other.mp3','Rain_HQ.wav.bak']:(r/n).write_bytes(b'x')
            pairs=low_quality.candidates(list(r.iterdir()))
            self.assertEqual([(a.name,b.name) for a,b in pairs],[('Rain_HQ.wav','Rain_LQ_128kbps.mp3')])
    def test_audio_match_and_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td); hi=r/'Bell.wav'; low=r/'Bell.mp3'; other=r/'Other.mp3'; tone(hi);low.write_bytes(b'fake');other.write_bytes(b'fake')
            def decoder(src,out): tone(out,880 if src.name=='Other.mp3' else 440)
            with patch('low_quality.decode_mono_8k',decoder):
                self.assertIsNotNone(low_quality.compare(hi,low))
                self.assertIsNone(low_quality.compare(hi,other))
    def test_same_loudness_different_spectrum_is_not_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td); hi=r/'Tone.wav'; low=r/'Tone.mp3'; hi.write_bytes(b'x'); low.write_bytes(b'y')
            def decoder(src,out): tone(out,880 if src.suffix=='.mp3' else 440)
            with patch('low_quality.decode_mono_8k',decoder):self.assertIsNone(low_quality.compare(hi,low))
    def test_quarantine_and_undo(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td); hi=r/'Rain.wav'; low=r/'Rain.mp3'; hi.write_bytes(b'high'); low.write_bytes(b'low')
            e=Engine(r)
            try:
                row={'keep':str(hi),'remove':str(low),'reason':'test'}
                self.assertEqual(e.apply_low_quality([row]),1); self.assertFalse(low.exists()); self.assertTrue(hi.exists())
                self.assertEqual(e.undo(),1); self.assertEqual(low.read_bytes(),b'low'); self.assertEqual(hi.read_bytes(),b'high')
            finally:e.close()
    def test_purge_only_quarantine_and_disables_undo(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td); hi=r/'Rain.wav'; low=r/'Rain.mp3'; hi.write_bytes(b'high'); low.write_bytes(b'low')
            e=Engine(r)
            try:
                e.apply_low_quality([{'keep':str(hi),'remove':str(low),'reason':'test'}])
                self.assertEqual(e.quarantine_summary(),{'count':1,'bytes':3})
                info=e.purge_quarantine()
                self.assertEqual(info,{'count':1,'bytes':3}); self.assertTrue(hi.exists()); self.assertFalse(low.exists())
                self.assertEqual(e.undo(),0)
                self.assertEqual(e.db.execute("SELECT status FROM moves").fetchone()[0],'purged')
            finally:e.close()
    def test_purge_preflight_rejects_symlink_before_deletion(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td); q=r/'.soundfx_organizer/LowQuality_Quarantine/batch'; q.mkdir(parents=True)
            audio=q/'low.mp3'; audio.write_bytes(b'low'); (q/'unsafe').symlink_to(r)
            e=Engine(r)
            try:
                with self.assertRaises(ValueError):e.purge_quarantine()
                self.assertTrue(audio.exists())
            finally:e.close()
    def test_duration_guard(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td); a=r/'x.wav';b=r/'x.mp3';a.write_bytes(b'a');b.write_bytes(b'b')
            with patch('low_quality.signature',side_effect=[([1]*8000,1),([1]*16000,2)]):self.assertIsNone(low_quality.compare(a,b))
if __name__=='__main__':unittest.main()
