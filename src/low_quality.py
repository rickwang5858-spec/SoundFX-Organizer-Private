import math, os, re, struct, subprocess, tempfile, wave
from collections import defaultdict
from pathlib import Path

LOSSLESS={'.wav','.wave','.aif','.aiff','.flac'}
LOSSY={'.mp3','.m4a','.ogg'}

def family_name(p):
    s=p.stem.casefold()
    s=re.sub(r'(?i)(?:^|[ _.-])(lossless|lossy|high|low|hires|hi res|hq|lq|wav|wave|aiff?|mp3|m4a|ogg|flac)(?=$|[ _.-])',' ',s)
    s=re.sub(r'(?i)(?:^|[ _.-])(?:64|96|128|160|192|256|320)\s*(?:k|kbps)(?=$|[ _.-])',' ',s)
    return re.sub(r'[^\w]+','',s)

def candidates(files):
    groups=defaultdict(list)
    for p in files:
        if p.suffix.lower() in LOSSLESS|LOSSY:
            key=(str(p.parent.resolve()).casefold(),family_name(p))
            if key[1]: groups[key].append(p)
    pairs=[]
    for group in groups.values():
        lossless=[p for p in group if p.suffix.lower() in LOSSLESS]
        lossy=[p for p in group if p.suffix.lower() in LOSSY]
        if lossless and lossy:
            keep=sorted(lossless,key=lambda p:(p.stat().st_size,p.suffix.lower()=='.wav'),reverse=True)[0]
            pairs.extend((keep,p) for p in lossy)
    return pairs

def decode_mono_8k(path,out):
    cmd=['/usr/bin/afconvert','-f','WAVE','-d','LEI16@8000','-c','1',str(path),str(out)]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=1800)
    if r.returncode: raise ValueError('macOS 無法解碼：'+(r.stderr or r.stdout)[-300:])

def samples(path):
    with wave.open(str(path),'rb') as w:
        if w.getnchannels()!=1 or w.getsampwidth()!=2 or w.getframerate()!=8000: raise ValueError('比較格式不符')
        raw=w.readframes(w.getnframes())
    n=len(raw)//2
    return list(struct.unpack('<%dh'%n,raw)),n/8000

def signature(path):
    with tempfile.TemporaryDirectory() as td:
        out=Path(td)/'decoded.wav'; decode_mono_8k(path,out); x,d=samples(out)
    # Trim digital/encoder padding using a conservative signal threshold.
    peak=max((abs(v) for v in x),default=0); threshold=max(8,int(peak*.004))
    active=[i for i,v in enumerate(x) if abs(v)>=threshold]
    if not active or peak<32: raise ValueError('接近靜音，不能安全判定重複')
    x=x[max(0,active[0]-160):min(len(x),active[-1]+161)]
    # At most 20 seconds from beginning, middle and end.
    take=20*8000
    if len(x)>take*3:
        mid=len(x)//2; x=x[:take]+x[mid-take//2:mid+take//2]+x[-take:]
    return x,d

def correlation(a,b):
    # 20 ms features are robust to lossy codecs. Zero crossings and normalized
    # sample differences prevent two sounds with similar loudness contours but
    # clearly different spectral character from being treated as duplicates.
    def features(x):
        size=160; env=[]; zcr=[]; rough=[]
        for i in range(0,len(x)-size+1,size):
            block=x[i:i+size]; energy=sum(v*v for v in block)
            env.append(math.log1p(math.sqrt(energy/size)))
            zcr.append(sum((block[j]<0)!=(block[j-1]<0) for j in range(1,size))/(size-1))
            rough.append(math.sqrt(sum((block[j]-block[j-1])**2 for j in range(1,size))/max(1,energy)))
        return env,zcr,rough
    best=None; ae,az,ar=features(a); be,bz,br=features(b)
    # Encoder delay is handled by testing +/- 0.12 seconds.
    for shift in range(-6,7):
        aa=ae[max(0,shift):min(len(ae),len(be)+shift)]
        bb=be[max(0,-shift):min(len(be),len(ae)-shift)]
        n=min(len(aa),len(bb))
        if n<25: continue
        aa=aa[:n]; bb=bb[:n]
        ma=sum(aa)/n; mb=sum(bb)/n
        va=sum((v-ma)**2 for v in aa); vb=sum((v-mb)**2 for v in bb)
        if not va or not vb: continue
        c=sum((aa[i]-ma)*(bb[i]-mb) for i in range(n))/math.sqrt(va*vb)
        za=az[max(0,shift):max(0,shift)+n]; zb=bz[max(0,-shift):max(0,-shift)+n]
        ra=ar[max(0,shift):max(0,shift)+n]; rb=br[max(0,-shift):max(0,-shift)+n]
        zerr=sum(abs(x-y) for x,y in zip(za,zb))/n
        rerr=sum(abs(x-y) for x,y in zip(ra,rb))/n
        row=(c,zerr,rerr)
        if best is None or row[0]>best[0]: best=row
    return best

def compare(keep,remove):
    a,da=signature(keep); b,db=signature(remove)
    if abs(da-db)>max(.25,min(da,db)*.002): return None
    metrics=correlation(a,b)
    if not metrics: return None
    score,zerr,rerr=metrics
    if score<.998 or zerr>.02 or rerr>.08: return None
    return {'keep':str(keep),'remove':str(remove),'correlation':score,'duration_a':da,'duration_b':db,
            'reason':'同資料夾同基礎名稱；無損／有損格式；長度一致，波形 %.4f，頻譜形狀通過'%(score)}
