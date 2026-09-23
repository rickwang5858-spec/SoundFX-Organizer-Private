import csv
import os
import tempfile
import time
import unittest
from pathlib import Path

from engine import Engine, LOG_ROOT


class IncrementalIntake(unittest.TestCase):
    def test_existing_managed_library_is_baselined_without_scan_or_move(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            managed=root/'擬音與日常物件 Foley & Household'/'門窗 Doors & Windows'
            managed.mkdir(parents=True)
            old=managed/'Door_Open_001.wav';old.write_bytes(b'existing-library-audio')
            before=(old.stat().st_ino,old.stat().st_mtime_ns,old.read_bytes())
            (root/'wind new.wav').write_bytes(b'new-audio')
            e=Engine(root,folder_style='bilingual')
            try:
                result=e.fast()
                self.assertEqual(result['moved'],1)
                self.assertEqual(result['new_audio_found'],1)
                self.assertEqual((old.stat().st_ino,old.stat().st_mtime_ns,old.read_bytes()),before)
            finally:e.close()

    def test_touching_managed_audio_never_reprocesses_it(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);managed=root/'Nature & Weather'/'Wind';managed.mkdir(parents=True)
            old=managed/'Wind_001.wav';old.write_bytes(b'old')
            e=Engine(root,folder_style='en')
            try:
                first=e.fast();self.assertEqual(first['moved'],0)
                os.utime(old,ns=(old.stat().st_atime_ns,old.stat().st_mtime_ns+1_000_000))
                second=e.fast();self.assertEqual(second['moved'],0);self.assertEqual(second['new_audio_found'],0)
                self.assertTrue(old.exists())
            finally:e.close()

    def test_new_single_file_and_nested_pack_only_are_processed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);managed=root/'Nature & Weather'/'Fire';managed.mkdir(parents=True)
            old=managed/'Fire_001.wav';old.write_bytes(b'protected')
            pack=root/'New Download'/'page turning'/'wav';pack.mkdir(parents=True)
            (pack/'Track 01.wav').write_bytes(b'page')
            (root/'door open.wav').write_bytes(b'door')
            e=Engine(root,folder_style='en')
            try:
                result=e.fast();self.assertEqual(result['moved'],2);self.assertEqual(result['new_audio_found'],2)
                self.assertTrue(old.exists());self.assertEqual(old.read_bytes(),b'protected')
                self.assertFalse((root/'New Download').exists())
                again=e.fast();self.assertEqual(again['moved'],0);self.assertEqual(again['new_audio_found'],0)
            finally:e.close()

    def test_pending_file_is_not_reclassified_after_timestamp_change(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pending=root/'123.wav';pending.write_bytes(b'ambiguous')
            e=Engine(root,folder_style='en')
            try:
                first=e.fast();self.assertEqual(first['pending'],[str(pending)]);self.assertEqual(first['new_audio_found'],1)
                os.utime(pending,None)
                second=e.fast();self.assertEqual(second['moved'],0);self.assertEqual(second['new_audio_found'],0)
                self.assertEqual(second['pending'],[str(pending)]);self.assertTrue(pending.exists())
            finally:e.close()

    def test_same_content_reintroduced_is_skipped_and_logged(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);first=root/'door open.wav';first.write_bytes(b'identical')
            e=Engine(root,folder_style='en')
            try:
                self.assertEqual(e.fast()['moved'],1)
                duplicate=root/'downloaded again.wav';duplicate.write_bytes(b'identical')
                result=e.fast();self.assertEqual(result['moved'],0);self.assertEqual(result['duplicates'],1)
                self.assertTrue(duplicate.exists())
                self.assertTrue(any(row['status']=='重複，已略過' and row['original_path']==str(duplicate) for row in result['log_rows']))
            finally:e.close()

    def test_undo_restores_incremental_file_and_allows_explicit_rerun(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'door open.wav';source.write_bytes(b'audio')
            e=Engine(root,folder_style='en')
            try:
                self.assertEqual(e.fast()['moved'],1);self.assertFalse(source.exists())
                self.assertEqual(e.undo(),1);self.assertTrue(source.exists())
                self.assertEqual(e.fast()['moved'],1);self.assertFalse(source.exists())
            finally:e.close()

    def test_batch_txt_and_csv_map_original_to_final_path(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'door open.wav';source.write_bytes(b'audio')
            e=Engine(root,folder_style='en')
            try:result=e.fast()
            finally:e.close()
            txt=Path(result['log']['text']);csv_path=Path(result['log']['csv'])
            self.assertEqual(txt.parent,root/LOG_ROOT);self.assertTrue(txt.is_file());self.assertTrue(csv_path.is_file())
            with csv_path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['原始位置'],str(source));self.assertEqual(rows[0]['處理狀態'],'成功')
            final=Path(rows[0]['最終完整路徑']);self.assertTrue(final.is_file());self.assertEqual(rows[0]['更名後檔名'],final.name)
            text=txt.read_text('utf-8');self.assertIn(str(source),text);self.assertIn(str(final),text)

    def test_missing_incremental_table_rebuilds_safely_from_protected_roots(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);managed=root/'Foley & Household'/'Footsteps';managed.mkdir(parents=True)
            old=managed/'Footsteps_001.wav';old.write_bytes(b'protected')
            e=Engine(root,folder_style='en');e.db.execute('DROP TABLE intake_files');e.db.commit();e.close()
            e=Engine(root,folder_style='en')
            try:
                result=e.fast();self.assertEqual(result['moved'],0);self.assertEqual(result['new_audio_found'],0);self.assertTrue(old.exists())
            finally:e.close()

    def test_corrupt_index_stops_before_touching_managed_audio(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);managed=root/'Foley & Household'/'Footsteps';managed.mkdir(parents=True)
            old=managed/'Footsteps_001.wav';old.write_bytes(b'protected')
            ctl=root/'.soundfx_organizer';ctl.mkdir();(ctl/'state4.sqlite').write_bytes(b'not a sqlite database')
            with self.assertRaisesRegex(RuntimeError,'安全停止'):Engine(root,folder_style='en')
            self.assertTrue(old.exists());self.assertEqual(old.read_bytes(),b'protected')


if __name__=='__main__':unittest.main()
