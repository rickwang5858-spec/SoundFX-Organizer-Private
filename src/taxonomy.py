"""Stable category IDs with localized filesystem labels."""
import re
from pathlib import Path

STYLES=('bilingual','zh-Hant','en')
TOP_ZH={
 'Ambience & Environments':'環境與空間','Nature & Weather':'自然與天氣','Animals & Birds':'動物與鳥類',
 'People & Crowds':'人聲與群眾','Foley & Household':'擬音與日常物件','Transportation & Traffic':'交通工具與交通',
 'Weapons & Combat':'武器與戰鬥','Impacts & Destruction':'撞擊與破壞','Designed & Cinematic':'設計音效與電影感',
 'Bells, Alarms & Technology':'鈴聲、警報與科技','Music & Seasonal':'音樂與節慶','Sports & Recreation':'運動與休閒',
 'Documentation & Licenses':'說明文件與授權','Needs Review':'待確認'}
SUB_ZH={
 'City & Street':'城市與街道','Nature':'自然環境','Interiors & Public Spaces':'室內與公共空間','Parks & Outdoor':'公園與戶外',
 'Ocean & Watercraft':'海洋與船舶','Wind':'風','Water':'水','Fire':'火','Rain & Thunder':'雨與雷',
 'Ocean, Underwater & Waves':'海洋、水下與海浪','Leaves & Vegetation':'樹葉與植物','Hot Springs & Geothermal':'溫泉與地熱',
 'Birds':'鳥類','Dogs & Cats':'狗與貓','Other':'其他動物','Crowd':'群眾','Human':'人聲',
 'People & Reactions':'人物與反應','Human Sounds':'人體聲音','Shouts & Reactions':'呼喊與反應','Body & Heartbeat':'身體與心跳',
 'Footsteps':'腳步','Doors & Windows':'門窗','Clothing & Body':'衣物與身體','Objects':'物件','Household':'居家',
 'Paper & Books':'紙張與書籍','Matches & Ignition':'火柴與點火','Kitchen & Dishes':'廚房與餐具','Containers & Objects':'容器與物件',
 'Metal Objects & Handling':'金屬物件與操作','Stone Objects & Mechanisms':'石材物件與機關','Wood Objects':'木製物件',
 'Drinks, Pouring & Fizz':'飲料、傾倒與氣泡','Bicycle & Motorcycle':'自行車與機車','Cars':'汽車',
 'Air & Rail':'航空與鐵路','Vehicle Interior & Components':'車內與零組件','Mixed Traffic & Engines':'混合交通與引擎',
 'Bow & Arrow':'弓箭','Guns':'槍械','Blades & Combat':'刀劍與戰鬥','Staff & Stick Combat':'棍棒戰鬥',
 'Weapons & Explosions':'武器與爆炸','Fights & Body Impacts':'打鬥與身體撞擊','Wood Breaks':'木材斷裂',
 'Magic & Fantasy':'魔法與奇幻','Shimmer, Sparkle & Crystal':'閃爍、亮光與水晶','Vinyl & Turntables':'黑膠與唱盤',
 'Christmas':'聖誕節','UI & Notifications':'介面與通知','Doorbells':'門鈴','Bells & Chimes':'鈴與鐘聲',
 'Devices & Mechanisms':'裝置與機械','Mixed Devices & Tools':'混合裝置與工具','General':'一般','Other Files':'其他檔案',
 'Root Files':'根目錄檔案','Sports & Boats':'運動與船艇','Mixed Natural Sounds':'混合自然聲','Animals_Birds':'動物與鳥類'}

def clean_legacy(value): return re.sub(r'^\d{2}\s+','',str(value))
def label(english,style):
    english=clean_legacy(english);zh=TOP_ZH.get(english,SUB_ZH.get(english,english))
    if style=='en' or zh==english:return english
    if style=='zh-Hant':return zh
    return zh+' '+english
def render_category(category,style='bilingual'):
    if style not in STYLES:style='bilingual'
    return Path(*(label(part,style) for part in str(category).split('/') if part))
def aliases(english):
    english=clean_legacy(english);zh=TOP_ZH.get(english,SUB_ZH.get(english,english))
    values={english,zh,zh+' '+english}
    values.update('%02d %s'%(n,english) for n in range(1,100))
    return values
def recognized_component(value,english):return str(value) in aliases(english)
def canonical_component(value):
    for english in tuple(TOP_ZH)+tuple(SUB_ZH):
        if str(value) in aliases(english):return english
    return None
def is_category_root(value):return any(str(value) in aliases(english) for english in TOP_ZH)
def translate_known_path(path,style):
    return Path(*(label(canonical_component(part),style) if canonical_component(part) else part for part in Path(path).parts))
