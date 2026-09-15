"""Path-aware Sound FX taxonomy and deterministic English naming."""
import re
from pathlib import Path
from legacy import RULES

RULE_VERSION=7
GROUPS={
 'Ambience':'Ambience & Environments','Nature':'Nature & Weather',
 'Animals':'Animals & Birds','Crowd & Voices':'People & Crowds',
 'Foley':'Foley & Household','Vehicles':'Transportation & Traffic',
 'Weapons':'Weapons & Combat','Explosions & Destruction':'Impacts & Destruction',
 'Impacts & Hits':'Impacts & Destruction','Whooshes & Transitions':'Designed & Cinematic',
 'Magic & Fantasy':'Designed & Cinematic','Sci-Fi':'Designed & Cinematic',
 'Horror':'Designed & Cinematic','Bells & Chimes':'Bells, Alarms & Technology',
 'Clocks & Mechanisms':'Bells, Alarms & Technology','Technology & UI':'Bells, Alarms & Technology',
 'Christmas':'Music & Seasonal','Music & Stingers':'Music & Seasonal'}
CANONICAL_ROOTS=set(GROUPS.values())|{'Sports & Recreation','Documentation & Licenses','Needs Review'}

def normal(value):
    s=re.sub(r'([a-z])([A-Z])',r'\1 \2',str(value))
    s=re.sub(r'(?i)audiojungle[ _.-]*\d+',' ',s)
    s=re.sub(r'(?i)20\d{2}[ _.-]\d{2}[ _.-]\d{2}(?:[ _.-]\d{2}){3}[ _.-]*utc',' ',s)
    s=re.sub(r'[_\W]+',' ',s)
    return re.sub(r'\s+',' ',s).strip().lower()

def phrase(rx,s): return re.search(r'(?<![a-z])(?:'+rx+r')(?![a-z])',s,re.I)
def convert(cat):
    top,sep,sub=cat.partition('/')
    top=re.sub(r'^\d{2}\s+','',top)
    return GROUPS.get(top,top)+'/'+(sub if sep else top)
def result(cat,why,label,tags=None,evidence=None,confidence=.82,reason_code='semantic_rule'):
    return {'cat':convert(cat),'label':label,'source':why,'tags':tags or [],
            'evidence':evidence or '', 'confidence':round(float(confidence),2),
            'reason_code':reason_code, 'rule_version':RULE_VERSION}

# Reusable compound semantics, never complete-filename literals.
# A file component receives more weight than a parent folder, so an explicit
# child description overrides its pack; generic Track/Sound names inherit it.
SEMANTIC=[
 (165,r'(?:attach|handle|handling|move|drop|set(?:ting)?)\s+(?:a\s+)?metal\s+(?:items?|objects?)|metal\s+(?:items?|objects?)\s+(?:attach|handling|movement)','Foley/Metal Objects & Handling','Metal_Object_Handling',['Metal']),
 (164,r'(?:shimmer|sparkles?|glitter|twinkles?)(?:\s+(?:pops?|bursts?))?|crystal(?:line)?\s+(?:shimmer|chime|sparkle)|(?:magic\s+)?crystal','Magic & Fantasy/Shimmer, Sparkle & Crystal','Shimmer_Sparkle_Crystal',[]),
 (163,r'(?:soda|cola|soft\s+drink).*(?:fizz|pour|bubbles?)|(?:fizz|pour).*(?:soda|cola|soft\s+drink)|liquid\s*pour.*fizz','Foley/Drinks, Pouring & Fizz','Drink_Pouring_Fizz',[]),
 (163,r'(?:static\s+)?vinyl\s+(?:crackle|crackling|noise|static)|record\s+(?:crackle|crackling|static)','Music & Stingers/Vinyl & Turntables','Vinyl_Crackling',[]),
 (163,r'vehicle\s+(?:side\s+)?windows?|car\s+(?:door\s+)?windows?','Vehicles/Vehicle Interior & Components','Vehicle_Window',['Vehicle','Window']),
 (163,r'(?:window|wndw)\s+(?:slide|sliding)\s+(?:close|closing|open|opening)|(?:slide|sliding)\s+windows?','Foley/Doors & Windows','Window_Sliding',[]),
 (163,r'wood(?:en)?\s+(?:sticks?|branches?|boards?)\s+(?:break|breaking|breaks|snap|snapping)','Explosions & Destruction/Wood Breaks','Wood_Break',['Wood']),
 (163,r'wood(?:en)?\s+sticks?\s+(?:fight|fighting|combat|clash|clashing)|(?:fight|fighting)\s+(?:with\s+)?wood(?:en)?\s+sticks?','Weapons/Staff & Stick Combat','Wooden_Stick_Combat',['Wood','Stick']),
 (162,r'stone\s+(?:insert|inserting|slide|sliding)\s+(?:in|into)?\s*stone|stone\s+(?:objects?|mechanisms?)','Foley/Stone Objects & Mechanisms','Stone_Object_Mechanism',['Stone']),
 (162,r'wood\s*rattles?|rattl(?:e|ing)\s+wood','Foley/Wood Objects','Wood_Rattle',['Wood','Rattle']),
 (162,r'(?:hot\s+springs?|geothermal|onsen|溫泉|温泉)','Nature/Hot Springs & Geothermal','Hot_Spring_Geothermal',[]),
 (161,r'(?:underwater|under\s*water|ambience\s*underw|subaquatic|subsea)','Nature/Ocean, Underwater & Waves','Underwater_Ambience',[]),
 (160,r'christmas\s+(?:urban\s+)?street\s+ambien(?:ce|ces|t|ts)?|(?:urban\s+)?street\s+christmas\s+ambien(?:ce|ces|t|ts)?','Ambience/City & Street','City_Street_Ambience',['Christmas']),
 (158,r'city\s+people\s+(?:talk|talking|conversation)|people\s+talking\s+(?:in\s+)?city','Crowd & Voices/People & Reactions','People_Talking_City',[]),
 (156,r'christmas\s+(?:transition|whoosh)|(?:transition|whoosh)\s+christmas','Christmas/Christmas','Christmas_Transition',[]),
 (154,r'correct\s+answer\s+(?:chime|bell|ding)','Technology & UI/UI & Notifications','Correct_Answer_Chime',[]),
 (152,r'bike\s+bells?|bicycle\s+bells?','Vehicles/Bicycle & Motorcycle','Bicycle_Bell',[]),
 (153,r'christmas.*bells?|bells?.*christmas','Christmas/Christmas','Christmas_Bell',[]),
 (152,r'door\s*bells?|bells?\s+doors?|doorbell','Bells & Chimes/Doorbells','Doorbell',[]),
 (151,r'wind\s+chimes?','Bells & Chimes/Bells & Chimes','Wind_Chime',[]),
 (150,r'pirate\s+ship\s+(?:sailing\s+)?ambien(?:ce|ces|t|ts)?|ship\s+sailing\s+ambien(?:ce|ces|t|ts)?','Ambience/Ocean & Watercraft','Pirate_Ship_Ambience',[]),
 (150,r'pirate\s+(?:laugh|laughing).*(?:drink|drinking)|(?:laugh|laughing).*(?:drink|drinking).*pirate','Crowd & Voices/People & Reactions','Pirate_Laughing_Drinking',[]),
 (150,r'pirate\s+chest','Foley/Containers & Objects','Pirate_Chest',[]),
 (150,r'needle\s+on\s+(?:a\s+)?record|vinyl\s+(?:needle|record)|record\s+needle','Music & Stingers/Vinyl & Turntables','Vinyl_Needle',[]),
 (150,r'(?:book\s+)?pages?\s+(?:turn|turning)|turning\s+(?:book\s+)?pages?','Foley/Paper & Books','Page_Turning',[]),
 (150,r'light\s+(?:a\s+)?match|matches?\s+(?:ignition|strike|striking|movement)|match\s+(?:ignition|strike|striking)|ignition\s+match','Foley/Matches & Ignition','Match_Ignition',[]),
 (148,r'magic\s+(?:whoosh|woosh)|fairy\s+dust','Magic & Fantasy/Magic & Fantasy','Magic_Fantasy',[]),
 (148,r'battl(?:e|ing)\s+knights?|knights?\s+(?:battle|fighting)','Weapons/Blades & Combat','Knight_Battle',[]),
 (148,r'rain\s+(?:and\s+)?thunder|thunder\s+(?:and\s+)?rain','Nature/Rain & Thunder','Rain_Thunder',[]),
 (147,r'ocean\s+beach\s+sea|ocean\s+waves?|sea\s+waves?|beach\s+waves?','Nature/Ocean, Underwater & Waves','Ocean_Waves',[]),
 (147,r'(?:residential\s+)?park\s+(?:area\s+)?ambien(?:ce|ces|t|ts)?|ambien(?:ce|ces|t|ts)?.*(?:residential\s+)?park','Ambience/Parks & Outdoor','Park_Ambience',[]),
 (147,r'autumn\s+(?:leaves|leaf).*(?:rustle|movement)|(?:rustling|movement)\s+(?:autumn\s+)?leaves','Nature/Leaves & Vegetation','Leaves_Rustle',[]),
 (146,r'(?:female|male|human)\s+(?:foot\s*)?steps|foot\s*steps|footsteps','Foley/Footsteps','Footsteps',[]),
 (146,r'heart\s*beats?|heartbeat','Crowd & Voices/Body & Heartbeat','Heartbeat',[]),
 (145,r'desert\s+winds?|autumn\s+breezes?','Nature/Wind','Wind',[]),
 (145,r'forest\s+(?:ambien|birds?)','Ambience/Nature','Forest_Ambience',[]),
 (144,r'campfire|bonfire','Nature/Fire','Campfire',[]),
 (144,r'fork\s+(?:on\s+)?plate|cutlery','Foley/Kitchen & Dishes','Cutlery',[]),
 (143,r'restaurant\s+ambien(?:ce|ces|t|ts)?|cafe\s+ambien(?:ce|ces|t|ts)?','Ambience/Interiors & Public Spaces','Restaurant_Ambience',[]),
 (143,r'city\s+traffic|urban\s+street|city\s+street|traffic\s+city|city\s+wash|lightly\s+travelled.*street','Ambience/City & Street','City_Street',[]),
 (142,r'opening\s+doors?|doors?\s+(?:open|opening)|door\s+open','Foley/Doors & Windows','Door_Open',[]),
 (142,r'land\s+ahoy|ship\s+ahoy|yo\s+ho\s+ho','Crowd & Voices/Shouts & Reactions','Pirate_Shout',[]),
 (140,r'droplets?|water\s+drops?|dripping','Nature/Water','Water_Droplet',[]),
 (140,r'sleigh\s+bells?','Christmas/Christmas','Christmas_Sleigh_Bells',[]),
 (138,r'bow\s+release|bow\s+arrow|archery','Weapons/Bow & Arrow','Bow_Arrow',[]),
 (138,r'gun\s*shots?|gunshot|rifles?|pistols?','Weapons/Guns','Gunshot',[]),
 (137,r'engine\s+(?:start|idle|rev)|car\s+engine','Vehicles/Cars','Car_Engine',[]),
 (136,r'interior\s+ambien(?:ce|ces|t|ts)?|room\s+tone','Ambience/Interiors & Public Spaces','Interior_Ambience',[]),
 (135,r'children?.*reaction|reaction.*children?','Crowd & Voices/People & Reactions','Children_Reaction',[]),
 (134,r'magic|fairy|fantasy|spell|wizard','Magic & Fantasy/Magic & Fantasy','Magic_Fantasy',[]),
 (133,r'page\s+turn|turning\s+pages?','Foley/Paper & Books','Page_Turning',[]),
 (132,r'match(?:es)?|match\s+stick','Foley/Matches & Ignition','Match',[]),
 (131,r'(?:leaves|leaf).*(?:rustle|movement)|rustling\s+leaves','Nature/Leaves & Vegetation','Leaves_Rustle',[]),
 (130,r'ocean|sea|waves?|beach|underwater','Nature/Ocean, Underwater & Waves','Ocean_Waves',[]),
 (130,r'park\s+ambien|residential\s+park','Ambience/Parks & Outdoor','Park_Ambience',[]),
 (130,r'fire|flame|burning|crackle','Nature/Fire','Fire',[]),
]

PACKS=[
 (r'traffic.*sirens.*motors','06 Transportation & Traffic/Mixed Traffic & Engines','Traffic_Engines'),
 (r'rain.*thunder.*fire.*bubbles','02 Nature & Weather/Mixed Natural Sounds','Natural_Sounds'),
 (r'birds.*animals','03 Animals & Birds/General','Animals_Birds'),
 (r'guns.*ricochets.*explosions','07 Weapons & Combat/Weapons & Explosions','Weapons_Explosions'),
 (r'fights.*body.*falls','07 Weapons & Combat/Fights & Body Impacts','Fight_Body_Impacts'),
 (r'sports.*boats','12 Sports & Recreation/Sports & Boats','Sports_Boats'),
 (r'human\s+sounds','04 People & Crowds/Human Sounds','Human_Sounds'),
 (r'crowds.*kids.*babies','04 People & Crowds/People & Reactions','People_Reactions'),
 (r'interior\s+ambien(?:ce|ces|t|ts)?','01 Ambience & Environments/Interiors & Public Spaces','Interior_Ambience'),
 (r'household','05 Foley & Household/Household','Household'),
 (r'telephones.*cameras.*clocks','10 Bells, Alarms & Technology/Devices & Mechanisms','Devices_Mechanisms'),
 (r'beeps.*bells.*buzzers.*rumbles.*tools','10 Bells, Alarms & Technology/Mixed Devices & Tools','Devices_Tools'),
]

GENERIC_WORDS={'wav','wave','mp3','m4a','aif','aiff','flac','caf','ogg','audio','stereo','mono','track','sound','sounds','file','files','hq','lq','kbps','utc','sfx','fx','full'}
def useful_component(value):
    words=normal(value).split()
    return ' '.join(w for w in words if w not in GENERIC_WORDS and not w.isdigit())
def is_generic(value):
    s=useful_component(value)
    if not s or bool(re.fullmatch(r'(?:track|sound|take|version|v)?\s*\d*',s)): return True
    compact=re.sub(r'[^a-z0-9]','',s)
    # Common library/catalog IDs such as SR019MS, UWT01_29.1, OCM-0018-334.
    return bool(re.fullmatch(r'[a-z]{1,8}\d{2,}[a-z0-9]*',compact) or
                re.fullmatch(r'[a-z]{2,8}\d+(?:[a-z]{0,4}\d+)+',compact))

def _legacy_matches(s):
    hits=[]
    for cat,rx in RULES:
        for word in rx.pattern.split('|'):
            if word in ('ambien','atmos'):token=r'(?<![a-z])(?:'+word+r')[a-z]*(?![a-z])'
            else:token=r'(?<![a-z])(?:'+word+r')(?:s)?(?![a-z])' if word.isascii() else word
            if re.search(token,s,re.I):
                label=re.sub(r'[^A-Za-z0-9]+','_',cat.split('/')[-1]).strip('_')
                hits.append((convert(cat),label,word)); break
    return hits

def classify(path):
    path=Path(path); components=[('檔名',path.stem,180)]
    for depth,value in enumerate(reversed(path.parts[:-1])):
        components.append(('來源資料夾',value,max(28,68-depth*7)))
    scored=[]
    filename_has_semantic=False
    for origin,value,weight in components:
        s=normal(value)
        if not s:continue
        before=len(scored)
        for priority,rx,cat,label,tags in SEMANTIC:
            m=phrase(rx,s)
            if m:scored.append((priority+weight+min(12,len(m.group(0))//3),priority,result(cat,origin+'：整條路徑語意',label,tags,m.group(0),.96 if origin=='檔名' else .86)))
        if origin=='檔名' and len(scored)>before:filename_has_semantic=True
        if origin!='檔名' and is_generic(path.stem):
            for rx,cat,label in PACKS:
                if re.search(rx,s,re.I):scored.append((190+weight,190,result(cat,origin+'：套件群組語意',label,[],s)))
        for cat,label,word in _legacy_matches(s):
            scored.append((45+weight,45,result(cat,origin+'：一般語意',label,[],word)))
    if not scored:return None
    scored.sort(key=lambda x:x[0],reverse=True); best=scored[0]
    if best[1]<100:
        rivals=[x for x in scored[1:] if x[2]['cat'].split('/')[0]!=best[2]['cat'].split('/')[0] and best[0]-x[0]<12]
        if rivals:return None
    r=best[2]; all_text=' '.join(normal(x) for x in path.parts)
    if r['label']=='Footsteps':
        if phrase('female|woman|women',all_text):r['label']+='_Female';r['tags'].append('Female')
        elif phrase('male|man|men',all_text):r['label']+='_Male';r['tags'].append('Male')
        if phrase('slow',all_text):r['label']+='_Slow';r['tags'].append('Slow')
        elif phrase('fast|run|running',all_text):r['label']+='_Fast';r['tags'].extend(['Running','Fast'])
    if r['cat'].endswith('/Doors & Windows') and phrase('stone',all_text): r['tags'].append('Stone')
    return r

def _sequence(stem):
    s=normal(stem)
    hits=re.findall(r'(?<![a-z])(?:track|sound|take|version|ver|v)\s*(\d{1,3})(?!\d)',s,re.I)
    if hits:return int(hits[-1])
    if re.search(r'(?i)(?:ocm|ocp|hdf|ar\d*|ldj)[ _.-]*\d',str(stem)):return 1
    tail=re.search(r'(?<!\d)(\d{1,3})\s*$',s)
    return int(tail.group(1)) if tail else 1

def _clean_words(value):
    s=re.sub(r'([a-z])([A-Z])',r'\1 \2',str(value))
    s=re.sub(r'(?i)^.*?audiojungle[ _.-]*\d+[ _.-]*','',s)
    s=re.sub(r'(?i)^mountain[ _.-]+audio[ _.-]*','',s)
    s=re.sub(r'(?i)[ _.-]*20\d{2}(?:[ _.-]\d{2}){5}[ _.-]*utc$','',s)
    s=re.sub(r'(?i)(?:^|[ _.-])(?:track|sound|take|version|ver|v)[ _.-]*\d{1,3}(?=$|[ _.-])',' ',s)
    s=re.sub(r'(?i)(?:^|[ _.-])(?:wav|wave|mp3|m4a|aiff?|flac|caf|ogg|audio|stereo|mono|hq|lq|\d{2,3}\s*kbps)(?=$|[ _.-])',' ',s)
    s=re.sub(r'(?i)(?:^|[ _.-])(?:ocm|ocp|hdf|gen|ldj|ar\d*)(?:[ _.-]*\d+)*(?=$|[ _.-])',' ',s)
    words=re.findall(r'[A-Za-z]+|\d+',s)
    stop=GENERIC_WORDS|{'a','an','the','and','of','on','in','full'}
    return [w.capitalize() if not w.isupper() else w for w in words if w.lower() not in stop]

def standardized_stem(path,r):
    path=Path(path); seq=_sequence(path.stem); detail=_clean_words(path.stem)
    if not detail or all(x.isdigit() for x in detail):
        for parent in reversed(path.parts[:-1]):
            detail=_clean_words(parent)
            if detail and not is_generic(parent):break
    topic=[x for x in r['label'].split('_') if x]; out=[]; seen=set()
    for word in topic+detail:
        key=word.casefold()
        if key not in seen and not word.isdigit():out.append(word);seen.add(key)
    return '%s_%03d'%(('_'.join(out) or 'Sound_Effect'),seq)

def audio_category(r):
    r=dict(r); c=classify(Path(r.get('label','')+'.wav'))
    if c:r['cat']=c['cat'];r['label']=c['label']
    else:
        top=r.get('cat','Other').split('/')[0]
        mapping={'People':'People & Crowds','Objects':'Bells, Alarms & Technology','Design':'Designed & Cinematic','Other':'Needs Review'}
        r['cat']=mapping[top]+'/General' if top in mapping else convert(r.get('cat','Needs Review/General'))
    return r
