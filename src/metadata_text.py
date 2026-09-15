"""Bounded, text-only metadata extraction. Audio sample data is never decoded."""
import os, plistlib, struct, subprocess
from pathlib import Path

MAX_METADATA=2*1024*1024

def _clean(value):
    if not value:return ''
    if isinstance(value,bytes):
        for enc in ('utf-8','utf-16','latin-1'):
            try:value=value.decode(enc);break
            except UnicodeError:continue
    value=' '.join(str(value).replace('\x00',' ').split())
    return value[:4096]

def _riff(path):
    out=[]
    with path.open('rb') as f:
        head=f.read(12)
        if len(head)<12 or head[:4] not in (b'RIFF',b'RF64') or head[8:12]!=b'WAVE':return out
        read=12
        while read<MAX_METADATA:
            h=f.read(8)
            if len(h)<8:break
            key,size=h[:4],struct.unpack('<I',h[4:])[0];read+=8
            if size>512*1024*1024:break
            if key in (b'bext',b'iXML',b'axml',b'LIST'):
                data=f.read(min(size,MAX_METADATA-read));read+=min(size,MAX_METADATA-read)
                text=_clean(data[:4096] if key==b'bext' else data)
                if text:out.append(('BWF/iXML' if key!=b'LIST' else 'RIFF INFO',text))
                if size>len(data):f.seek(size-len(data),1)
            else:f.seek(size,1);read+=size
            if size&1:f.seek(1,1);read+=1
    return out

def _synchsafe(data): return ((data[0]&127)<<21)|((data[1]&127)<<14)|((data[2]&127)<<7)|(data[3]&127)
def _decode_id3(data):
    if not data:return ''
    enc=data[0];body=data[1:]
    codec={0:'latin-1',1:'utf-16',2:'utf-16-be',3:'utf-8'}.get(enc,'utf-8')
    try:return _clean(body.decode(codec,errors='replace'))
    except Exception:return ''

def _mp3(path):
    out=[]
    with path.open('rb') as f:
        head=f.read(10)
        if len(head)<10 or head[:3]!=b'ID3':return out
        version=head[3];size=min(_synchsafe(head[6:10]),MAX_METADATA);data=f.read(size);pos=0
        while pos+10<=len(data):
            frame=data[pos:pos+4]
            if not frame.strip(b'\x00'):break
            n=_synchsafe(data[pos+4:pos+8]) if version==4 else int.from_bytes(data[pos+4:pos+8],'big')
            if n<1 or pos+10+n>len(data):break
            if frame in (b'TIT2',b'COMM',b'TXXX'):
                text=_decode_id3(data[pos+10:pos+10+n])
                if text:out.append(('ID3 '+frame.decode('ascii'),text))
            pos+=10+n
    return out

def _flac(path):
    out=[]
    with path.open('rb') as f:
        if f.read(4)!=b'fLaC':return out
        total=4
        while total<MAX_METADATA:
            h=f.read(4)
            if len(h)<4:break
            last=bool(h[0]&128);kind=h[0]&127;n=int.from_bytes(h[1:4],'big');total+=4
            if n>MAX_METADATA:break
            data=f.read(n);total+=n
            if kind==4:
                try:
                    p=0;vendor=int.from_bytes(data[p:p+4],'little');p+=4+vendor
                    count=int.from_bytes(data[p:p+4],'little');p+=4
                    for _ in range(min(count,128)):
                        size=int.from_bytes(data[p:p+4],'little');p+=4
                        val=_clean(data[p:p+size]);p+=size
                        if val:out.append(('FLAC Vorbis Comment',val))
                except (ValueError,IndexError):pass
            if last:break
    return out

def _aiff(path):
    out=[]
    with path.open('rb') as f:
        if f.read(4)!=b'FORM':return out
        f.read(4)
        if f.read(4) not in (b'AIFF',b'AIFC'):return out
        total=12
        while total<MAX_METADATA:
            h=f.read(8)
            if len(h)<8:break
            key=h[:4];n=int.from_bytes(h[4:],'big');total+=8
            if n>512*1024*1024:break
            if key in (b'NAME',b'AUTH',b'ANNO',b'COMT'):
                data=f.read(min(n,MAX_METADATA-total));text=_clean(data)
                if text:out.append(('AIFF '+key.decode('ascii'),text))
                if n>len(data):f.seek(n-len(data),1)
            else:f.seek(n,1)
            total+=n
            if n&1:f.seek(1,1);total+=1
    return out

def _finder_tags(path):
    out=[]
    try:
        raw=os.getxattr(path,'com.apple.metadata:_kMDItemUserTags')
        tags=plistlib.loads(raw)
        text=' '.join(str(t).split('\n')[0] for t in tags)
        if text:out.append(('Finder Tags',text))
    except (AttributeError,OSError,ValueError,plistlib.InvalidFileException):pass
    return out

def extract(path):
    """Return [(source, text)] without reading media sample payloads."""
    path=Path(path);suffix=path.suffix.lower();out=[]
    try:
        if suffix in ('.wav','.wave'):out.extend(_riff(path))
        elif suffix=='.mp3':out.extend(_mp3(path))
        elif suffix in ('.aif','.aiff'):out.extend(_aiff(path))
        elif suffix=='.flac':out.extend(_flac(path))
        out.extend(_finder_tags(path))
    except (OSError,ValueError,struct.error):pass
    seen=set();unique=[]
    for source,text in out:
        key=(source,text.casefold())
        if key not in seen:unique.append((source,text));seen.add(key)
    return unique
