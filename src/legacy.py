#!/usr/bin/env python3
import csv, hashlib, json, os, re, shutil, subprocess, sys, tempfile
from datetime import datetime
from pathlib import Path

AUDIO={'.wav','.wave','.aif','.aiff','.mp3','.m4a','.flac','.caf','.ogg'}
CONTROL='.soundfx_organizer'
RULES=[
('Ambience/City & Street',r'city|urban|street|traffic|downtown|alley|market|subway|metro|station|airport|restaurant|cafe|office|roomtone|room tone|城市|街道|市場|捷運|車站|機場|餐廳|辦公室'),
('Ambience/Nature',r'ambien|atmos|forest|jungle|mountain|field|desert|cave|woods|nature|環境|森林|叢林|山谷|荒野|洞穴'),
('Nature/Wind',r'wind|breeze|gust|storm|hurricane|tornado|風聲|強風|微風|暴風'),
('Nature/Water',r'water|river|stream|creek|ocean|sea|wave|rain|thunder|underwater|splash|drip|瀑布|河流|海浪|雨|雷|水滴|水下'),
('Nature/Fire',r'fire|flame|campfire|bonfire|burn|crackle|火焰|營火|燃燒'),
('Animals/Birds',r'bird|crow|raven|owl|eagle|seagull|duck|chicken|rooster|鳥|烏鴉|貓頭鷹|海鷗|雞叫'),
('Animals/Dogs & Cats',r'dog|puppy|bark|cat|kitten|meow|犬|狗|貓|喵'),
('Animals/Other',r'animal|horse|cow|pig|sheep|goat|lion|tiger|elephant|monkey|insect|bee|mosquito|frog|動物|馬|牛|豬|羊|獅|虎|象|昆蟲|青蛙'),
('Crowd & Voices/Crowd',r'crowd|audience|people|mob|cheer|applause|clap|booing|chant|人群|觀眾|歡呼|掌聲|鼓掌'),
('Crowd & Voices/Human',r'laugh|cry|scream|shout|whisper|breath|cough|sneeze|yawn|baby|kid|woman|man voice|笑聲|哭聲|尖叫|呼吸|咳嗽|噴嚏|嬰兒'),
('Foley/Footsteps',r'footstep|foot step|walking|running|shoe|boots|heel|腳步|走路|跑步|鞋跟'),
('Foley/Doors & Windows',r'door|window|gate|hinge|knock|latch|lock|門|窗|敲門|門鎖'),
('Foley/Clothing & Body',r'cloth|clothing|fabric|zipper|body fall|body hit|skin|衣服|布料|拉鍊|身體'),
('Foley/Objects',r'foley|paper|book|bag|box|bottle|can|cup|glass|keys|coin|chair|table|drawer|switch|button|紙張|書本|袋子|盒子|瓶子|杯子|鑰匙|硬幣|椅子|抽屜|開關'),
('Vehicles/Bicycle & Motorcycle',r'bike|bicycle|cycle|motorcycle|scooter|自行車|腳踏車|機車|摩托車'),
('Vehicles/Cars',r'car|auto|engine|motor|truck|bus|horn|brake|skid|tire|vehicle|汽車|引擎|卡車|巴士|喇叭|煞車|輪胎'),
('Vehicles/Air & Rail',r'airplane|aircraft|jet|helicopter|train|rail|tram|飛機|直升機|火車|列車'),
('Weapons/Bow & Arrow',r'bow.?arrow|archery|arrow|bow release|弓箭|射箭'),
('Weapons/Guns',r'gun|rifle|pistol|shotgun|firearm|bullet|gunshot|槍|步槍|手槍|子彈'),
('Weapons/Blades & Combat',r'sword|knife|blade|dagger|axe|fight|punch|kick|combat|劍|刀|斧|打鬥|拳擊'),
('Explosions & Destruction',r'explosion|explode|bomb|blast|debris|collapse|destruction|爆炸|炸彈|倒塌|破壞'),
('Impacts & Hits',r'impact|hit|slam|bang|thud|crash|smash|撞擊|重擊|摔落|砸碎'),
('Whooshes & Transitions',r'whoosh|woosh|swoosh|swish|transition|pass by|flyby|轉場|呼嘯'),
('Bells & Chimes',r'bell|chime|ding|gong|鈴|鐘聲|風鈴|鑼'),
('Clocks & Mechanisms',r'clock|watch|tick.?tock|gear|mechanism|machine|projector|時鐘|手錶|滴答|齒輪|機械|放映機'),
('Technology & UI',r'computer|keyboard|mouse|phone|camera|notification|interface|beep|digital|scanner|radio|television|電腦|鍵盤|滑鼠|手機|相機|通知|介面|嗶聲'),
('Magic & Fantasy',r'magic|spell|wizard|fairy|fantasy|supernatural|ghost|monster|dragon|魔法|奇幻|鬼魂|怪物|龍'),
('Sci-Fi',r'sci.?fi|spaceship|space ship|laser|robot|alien|futur|太空船|雷射|機器人|外星|未來'),
('Horror',r'horror|scary|creepy|terror|haunted|zombie|blood|恐怖|驚悚|鬧鬼|殭屍'),
('Christmas',r'christmas|xmas|sleigh|santa|聖誕|雪橇|聖誕老人'),
('Music & Stingers',r'stinger|jingle|logo|fanfare|drum roll|musical|music cue|音樂|片頭|片尾|短樂句')]
RULES=[(c,re.compile(p,re.I)) for c,p in RULES]

def osa(script): return subprocess.run(['/usr/bin/osascript','-e',script],text=True,capture_output=True,check=True).stdout.strip()
def notify(msg):
    try: osa(f'display notification "{esc(msg)}" with title "Sound FX Organizer"')
    except Exception: pass
def esc(s): return str(s).replace('\\','\\\\').replace('"','\\"').replace('\n','\\n')
def dialog(msg,buttons=('完成',),default=None,cancel=None):
    default=default or buttons[-1]; b=', '.join('"'+esc(x)+'"' for x in buttons)
    tail=f' buttons {{{b}}} default button "{esc(default)}"'
    if cancel: tail+=f' cancel button "{esc(cancel)}"'
    return osa(f'display dialog "{esc(msg)}" with title "Sound FX Organizer"{tail}\nbutton returned of result')
def choose(): return Path(osa('POSIX path of (choose folder with prompt "請選擇 Sound FX 音效庫最上層資料夾")')).resolve()
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()
def load(p,default):
    try: return json.loads(p.read_text('utf-8'))
    except (FileNotFoundError,json.JSONDecodeError,UnicodeDecodeError): return default
def save(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=p.name+'.',dir=p.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(obj,f,ensure_ascii=False,indent=2); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
def scan(root):
    out=[]
    for base,dirs,files in os.walk(root):
        dirs[:]=[d for d in dirs if d!=CONTROL and not d.startswith('.')]
        for n in files:
            p=Path(base)/n
            if p.suffix.lower() in AUDIO and not p.is_symlink(): out.append(p)
    return sorted(out,key=lambda p:str(p).casefold())
def classify(rel):
    s=re.sub(r'[_\-.]+',' ',str(rel))
    for cat,rx in RULES:
        if rx.search(s): return cat,'high',rx.pattern
    return '_待確認','low','檔名與原資料夾沒有足夠線索'
def unique_dest(p,h):
    if not p.exists(): return p
    if p.is_file() and digest(p)==h: return None
    for i in range(2,10000):
        q=p.with_name(f'{p.stem}_{i:02d}{p.suffix}')
        if not q.exists(): return q
    raise RuntimeError(f'同名檔案過多：{p}')
def preview(root,items):
    p=root/f'_SoundFX_分類預覽_{datetime.now():%Y%m%d_%H%M%S}.csv'
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['原始相對路徑','檔名','格式','建議分類','信心度','判斷依據','預計新位置'])
        for x in items: w.writerow([x['rel'],x['path'].name,x['path'].suffix,x['cat'],x['confidence'],x['reason'],f"{x['cat']}/{x['path'].name}"])
    return p
def process(root,mode,items=None):
    ctl=root/CONTROL; dbp=ctl/'database.json'; db=load(dbp,{'version':2,'files':{}}); ctl.mkdir(parents=True,exist_ok=True)
    if items is None:
        fresh=[]
        for p in scan(root):
            h=digest(p)
            if h not in db['files']:
                cat,conf,reason=classify(p.relative_to(root)); fresh.append({'path':p,'rel':str(p.relative_to(root)),'hash':h,'cat':cat,'confidence':conf,'reason':reason})
    else: fresh=items
    if not fresh: return {'fresh':0,'moved':0,'duplicate':0,'errors':[]}
    log=preview(root,fresh)
    if mode=='baseline':
        for x in fresh: db['files'][x['hash']]={'lastKnownPath':x['rel'],'registeredAt':datetime.now().isoformat(),'mode':'baseline'}
        save(dbp,db); return {'fresh':len(fresh),'moved':0,'duplicate':0,'errors':[],'log':log}
    moved=dup=0; errors=[]
    for x in fresh:
        try:
            dest=unique_dest(root/x['cat']/x['path'].name,x['hash'])
            if dest is None: dup+=1
            else: dest.parent.mkdir(parents=True,exist_ok=True); shutil.move(str(x['path']),str(dest)); moved+=1
            db['files'][x['hash']]={'lastKnownPath':str((dest or x['path']).relative_to(root)),'registeredAt':datetime.now().isoformat(),'category':x['cat'],'confidence':x['confidence']}
        except Exception as e: errors.append(f"{x['rel']} — {e}")
    db['lastRun']=datetime.now().isoformat(); save(dbp,db)
    return {'fresh':len(fresh),'moved':moved,'duplicate':dup,'errors':errors,'log':log}
def gui():
    pref=Path.home()/'Library/Preferences/tw.snowmanmusic.soundfx-organizer.json'; settings=load(pref,{})
    root=Path(settings.get('root','')) if settings.get('root') else None
    if not root or not root.is_dir(): root=choose(); save(pref,{'root':str(root)})
    dialog(f'程式已開啟。\n\n音效庫：{root.name}\n\n按「開始掃描」後會讀取音效檔案。第一次掃描大型音效庫可能需要幾分鐘；完成後會自動出現確認視窗。',('取消','開始掃描'),'開始掃描','取消')
    notify('正在掃描音效庫；完成後會自動顯示結果。')
    db=load(root/CONTROL/'database.json',{'files':{}}); first=not db.get('files')
    # Pre-scan only to report count; process recalculates safely after confirmation.
    known=set(db.get('files',{})); fresh=[]
    for p in scan(root):
        h=digest(p)
        if h not in known:
            cat,conf,reason=classify(p.relative_to(root)); fresh.append({'path':p,'rel':str(p.relative_to(root)),'hash':h,'cat':cat,'confidence':conf,'reason':reason})
    count=len(fresh); high=sum(x['confidence']=='high' for x in fresh)
    if not count: dialog(f'掃描完成。\n\n沒有找到尚未處理的新音效。\n已登記 {len(known)} 個檔案；現有分類完全沒有被更動。'); return
    msg=f'找到 {count} 個尚未登記的音效。\n\n可自動分類：{high}\n待確認：{count-high}\n\n確認後才會搬動檔案，並產生 CSV 預覽。'
    if first:
        msg+='\n\n第一次執行：若現有檔案早已整理好，選「只建立現況」；若整庫仍零散，選「正式整理」。'
        ans=dialog(msg,('取消','只建立現況','正式整理'),'正式整理','取消'); mode='baseline' if ans=='只建立現況' else 'apply'
    else: dialog(msg,('取消','正式整理'),'正式整理','取消'); mode='apply'
    r=process(root,mode,fresh)
    if mode=='baseline': dialog(f"完成。已登記 {r['fresh']} 個現有音效，沒有搬動任何檔案。")
    else: dialog(f"整理完成。\n\n已分類搬移：{r['moved']}\n相同內容未重複搬移：{r['duplicate']}\n失敗：{len(r['errors'])}\n待確認音效已放在「_待確認」。\n\n紀錄：{r['log'].name}")
def self_test():
    with tempfile.TemporaryDirectory() as td:
        r=Path(td); (r/'舊分類').mkdir(); (r/'新下載包').mkdir()
        samples={'舊分類/keep.wav':b'old','新下載包/door-open.aif':b'door','新下載包/wind.wav':b'wind','新下載包/mystery.flac':b'x','新下載包/same.wav':b'door'}
        for n,data in samples.items(): p=r/n; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data)
        a=process(r,'baseline'); assert a['moved']==0 and len(scan(r))==5
        (r/'new bell.mp3').write_bytes(b'bell'); b=process(r,'apply'); assert b['moved']==1 and (r/'Bells & Chimes/new bell.mp3').exists()
        c=process(r,'apply'); assert c['fresh']==0
        (r/'Bells & Chimes').rename(r/'我改過名稱'); d=process(r,'apply'); assert d['fresh']==0
        (r/'door-open.aif').write_bytes(b'different'); e=process(r,'apply'); assert e['moved']==1 and (r/'Foley/Doors & Windows/door-open.aif').exists()
    print('SELF_TEST_OK')
if __name__=='__main__':
    try:
        if '--self-test' in sys.argv: self_test()
        else: gui()
    except subprocess.CalledProcessError as e:
        if '-128' not in (e.stderr or ''):
            log=Path.home()/'Desktop/Sound FX Organizer 錯誤紀錄.txt'
            log.write_text(f'{datetime.now().isoformat()}\nAppleScript error\n{e.stderr}\n',encoding='utf-8')
            try: dialog(f'執行時發生錯誤，詳細資料已存到桌面：\n{log.name}\n\n{e.stderr}')
            except Exception: pass
    except Exception as e:
        log=Path.home()/'Desktop/Sound FX Organizer 錯誤紀錄.txt'
        try: log.write_text(f'{datetime.now().isoformat()}\n{type(e).__name__}: {e}\n',encoding='utf-8')
        except Exception: pass
        try: dialog(f'執行時發生錯誤，詳細資料已存到桌面：\n{log.name}\n\n{type(e).__name__}: {e}')
        except Exception: pass
