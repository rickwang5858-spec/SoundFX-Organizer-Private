"""Runtime localization from external JSON resources."""
import json, locale, os, subprocess
from pathlib import Path

LANGUAGES={'system':None,'zh-Hant':'zh-Hant','en':'en'}
LABELS={'system':'Follow System / 跟隨系統','zh-Hant':'繁體中文','en':'English'}

def system_language():
    candidates=[]
    try:
        p=subprocess.run(['/usr/bin/defaults','read','-g','AppleLanguages'],capture_output=True,text=True,timeout=1)
        candidates.append(p.stdout)
    except (OSError,subprocess.TimeoutExpired):pass
    candidates.extend([os.environ.get('LANG',''),locale.getlocale()[0] or ''])
    return 'zh-Hant' if any(x.lower().startswith(('zh_tw','zh-tw','zh_hant','zh-hant')) or 'zh-Hant' in x for x in candidates) else 'en'

class I18n:
    def __init__(self,choice='system'):
        self.base=Path(__file__).with_name('locales');self.choice=choice;self.data={};self.reload()
    @property
    def language(self):return system_language() if self.choice=='system' else self.choice
    def reload(self):
        lang=self.language if self.language in ('zh-Hant','en') else 'en'
        try:self.data=json.loads((self.base/(lang+'.json')).read_text('utf-8'))
        except (OSError,ValueError):self.data={}
    def set(self,choice):self.choice=choice if choice in LANGUAGES else 'system';self.reload()
    def t(self,key,**values):
        text=self.data.get(key,key)
        try:return text.format(**values)
        except (KeyError,ValueError):return text
