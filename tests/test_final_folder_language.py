import tempfile,unittest
from pathlib import Path
from categories import classify
from engine import Engine
from taxonomy import render_category

class FolderLanguage(unittest.TestCase):
    def test_render_all_three_styles(self):
        cat='Foley & Household/Footsteps'
        self.assertEqual(str(render_category(cat,'en')),'Foley & Household/Footsteps')
        self.assertEqual(str(render_category(cat,'zh-Hant')),'擬音與日常物件/腳步')
        self.assertEqual(str(render_category(cat,'bilingual')),'擬音與日常物件 Foley & Household/腳步 Footsteps')

    def test_categories_have_no_sort_numbers(self):
        self.assertEqual(classify(Path('female-running-footsteps.wav'))['cat'],'Foley & Household/Footsteps')

    def test_each_style_moves_and_reruns_once(self):
        for style,path in [('en','Nature & Weather/Wind'),('zh-Hant','自然與天氣/風'),('bilingual','自然與天氣 Nature & Weather/風 Wind')]:
            with self.subTest(style=style),tempfile.TemporaryDirectory() as d:
                root=Path(d);(root/'wind.wav').write_bytes(b'wind')
                e=Engine(root,folder_style=style)
                try:
                    self.assertEqual(e.fast()['moved'],1);self.assertEqual(len(list((root/path).glob('*.wav'))),1)
                    self.assertEqual(e.fast()['moved'],0)
                finally:e.close()

    def test_style_switch_migrates_app_file_without_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'door-open.wav').write_bytes(b'door')
            e=Engine(root,folder_style='en')
            try:e.fast()
            finally:e.close()
            e=Engine(root,folder_style='bilingual')
            try:
                e.fast();target=root/'擬音與日常物件 Foley & Household'/'門窗 Doors & Windows'
                self.assertEqual(len(list(target.glob('*.wav'))),1)
                self.assertFalse((root/'Foley & Household').exists())
                self.assertEqual(e.fast()['moved'],0)
            finally:e.close()

    def test_name_collision_stays_in_selected_localized_category(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);audio=root/'wind.wav';audio.write_bytes(b'wind')
            e=Engine(root,folder_style='bilingual')
            try:
                result=classify(audio);first=e.destination(audio,result)
                second=e.destination(audio,result,{str(first).casefold()})
                localized=root/'自然與天氣 Nature & Weather'/'風 Wind'
                self.assertEqual(second.parent,localized.resolve(strict=False))
                self.assertTrue(second.name.endswith('_002.wav'))
            finally:e.close()

    def test_unproven_similar_folder_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'05 Foley & Household'/'manual.txt';p.parent.mkdir();p.write_text('user')
            e=Engine(root,folder_style='zh-Hant')
            try:e.migrate_category_roots();self.assertTrue(p.exists())
            finally:e.close()
