import os, re, json, sqlite3, time, uuid, csv, threading, fcntl, errno, hashlib, shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from legacy import AUDIO
from categories import classify, audio_category, GROUPS, RULE_VERSION, CANONICAL_ROOTS, standardized_stem, normal, is_generic
from low_quality import candidates as low_candidates, compare as compare_quality
from metadata_text import extract as extract_metadata
from custom_rules import CustomRules
from taxonomy import render_category, aliases, TOP_ZH, STYLES, is_category_root, translate_known_path

CONTROL='.soundfx_organizer'
DOC_ROOT='Documentation & Licenses'
LOG_ROOT='SoundFX Organizer Logs'
DOC_EXTS={'.txt','.pdf','.rtf','.doc','.docx','.jpg','.jpeg','.png','.gif','.tif','.tiff','.webp','.html','.htm','.url','.webloc','.nfo','.md'}
LINK_FALLBACK_ERRNOS={errno.EPERM,errno.EOPNOTSUPP,errno.EXDEV,errno.ENOSYS,45}
if hasattr(errno,'ENOTSUP'):LINK_FALLBACK_ERRNOS.add(errno.ENOTSUP)
class Stopped(Exception): pass
def system_file(name):return name.startswith('._') or name in ('.DS_Store','Thumbs.db','desktop.ini')
def signature(p):
    s=p.stat(); return '%d:%d:%d:%d'%(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
class Engine:
    def __init__(self,root,emit=lambda *x:None,stop=None,pause=None,performance='quiet',folder_style='en'):
        self.root=Path(root).resolve(); self.emit=emit; self.stop=stop or threading.Event(); self.pause=pause or threading.Event()
        self.performance=performance;self.folder_style=folder_style if folder_style in STYLES else 'bilingual';self.system_skipped=0;self.system_files=[]
        if self.root in [Path('/'),Path.home()] or self.root.parent==Path('/Volumes'): raise ValueError('請選音效庫子資料夾，不要選整顆磁碟。')
        self.ctl=self.root/CONTROL; self.ctl.mkdir(exist_ok=True)
        self.lock=(self.ctl/'lock4').open('a')
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:self.lock.close();raise
        try:
            self.db=sqlite3.connect(self.ctl/'state4.sqlite')
            self.db.executescript('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE IF NOT EXISTS seen(sig TEXT PRIMARY KEY,path TEXT); CREATE TABLE IF NOT EXISTS file_rules(sig TEXT PRIMARY KEY,rule_version INTEGER); CREATE TABLE IF NOT EXISTS audio(sig TEXT PRIMARY KEY,result TEXT); CREATE TABLE IF NOT EXISTS moves(id INTEGER PRIMARY KEY, batch TEXT,src TEXT,dst TEXT,sig TEXT,status TEXT); CREATE TABLE IF NOT EXISTS decisions(sig TEXT PRIMARY KEY,path TEXT,category TEXT,tags TEXT,evidence TEXT,confidence REAL,reason TEXT,rule_version INTEGER); CREATE TABLE IF NOT EXISTS intake_files(file_key TEXT PRIMARY KEY,content_hash TEXT NOT NULL,stat_sig TEXT NOT NULL,original_path TEXT NOT NULL,current_path TEXT NOT NULL,status TEXT NOT NULL,batch TEXT,updated_at REAL NOT NULL,detail TEXT); CREATE INDEX IF NOT EXISTS intake_content_hash ON intake_files(content_hash);')
        except sqlite3.DatabaseError as exc:
            try:self.db.close()
            except Exception:pass
            self.lock.close()
            raise RuntimeError('增量索引無法讀取，為避免重新搬動既有音效，已在變更任何檔案前安全停止。請匯出診斷資訊。') from exc
        self.device=self.root.stat().st_dev
        self.custom=CustomRules(self.ctl/'custom_rules.json')
        self.intake={};self.duplicate_rows=[];self.known_pending=[];self.new_audio_found=0;self.new_attachment_found=0
        self._recover_incomplete_moves()
    def _relative(self,p):
        """Return a safe library-relative path across macOS path aliases.

        macOS exposes some locations through aliases such as /var -> /private/var.
        Resolve both the selected root and incoming path before containment checks.
        Paths that actually escape the library still raise ValueError.
        """
        return Path(p).resolve(strict=False).relative_to(self.root)
    def _recover_incomplete_moves(self):
        """Resolve journal rows left before the source file was removed."""
        rows=self.db.execute("SELECT id,src,dst,sig,status FROM moves WHERE status IN ('moving','failed') ORDER BY id").fetchall()
        for row_id,src,dst,sig,status in rows:
            source,target=Path(src),Path(dst)
            recovery=self.ctl/'Interrupted_Copies'/('%s-%s'%(row_id,target.name))
            if system_file(source.name):
                self.db.execute("UPDATE moves SET status='system_metadata_preserved' WHERE id=?",(row_id,));continue
            if status=='failed':
                if source.exists():continue
                if recovery.exists() and not target.exists():
                    source.parent.mkdir(parents=True,exist_ok=True)
                    try:os.replace(recovery,source);self.db.execute("UPDATE moves SET status='recovered' WHERE id=?",(row_id,))
                    except OSError:self.db.execute("UPDATE moves SET status='needs_review' WHERE id=?",(row_id,))
                else:self.db.execute("UPDATE moves SET status='needs_review' WHERE id=?",(row_id,))
                continue
            if source.exists() and not target.exists():
                self.db.execute("UPDATE moves SET status='failed' WHERE id=?",(row_id,))
                self.emit('notice','已自動清除上次未開始的搬移紀錄，來源檔完整保留。')
            elif source.exists() and target.exists():
                recovery=self.ctl/'Interrupted_Copies'/('%s-%s'%(row_id,target.name))
                recovery.parent.mkdir(parents=True,exist_ok=True)
                try:
                    if os.path.samefile(source,target):target.unlink()
                    else:os.replace(target,recovery)
                    self.db.execute("UPDATE moves SET status='failed' WHERE id=?",(row_id,))
                    self.emit('notice','已保留並隔離上次中斷產生的目的檔；來源檔未刪除。')
                except OSError:
                    self.db.execute("UPDATE moves SET status='needs_review' WHERE id=?",(row_id,))
                    self.emit('notice','上次中斷留下兩個檔案，兩份均保留並列入紀錄。')
            elif not source.exists() and target.exists():
                try:
                    if signature(target)==sig:
                        self.db.execute("UPDATE moves SET status='done',sig=? WHERE id=?",(signature(target),row_id))
                        self.db.execute('INSERT OR REPLACE INTO seen VALUES(?,?)',(signature(target),str(target)))
                    else:self.db.execute("UPDATE moves SET status='needs_review' WHERE id=?",(row_id,))
                except OSError:self.db.execute("UPDATE moves SET status='needs_review' WHERE id=?",(row_id,))
            else:self.db.execute("UPDATE moves SET status='needs_review' WHERE id=?",(row_id,))
        self.db.commit()
    def close(self): self.db.close(); self.lock.close()
    def checkpoint(self):
        if not self.root.is_dir() or self.root.stat().st_dev!=self.device:raise OSError(errno.ENODEV,'音效庫磁碟已中斷或被替換，已安全停止。')
        while self.pause.is_set():
            if self.stop.wait(.15): raise Stopped()
        if self.stop.is_set(): raise Stopped()
    def scan(self):
        files=[]; attachments=[]; extras=[]; dirs=[]
        def onerror(e): extras.append((e.filename,'讀取失敗：'+str(e)))
        for base,ds,fs in os.walk(self.root,onerror=onerror,followlinks=False):
            self.checkpoint()
            kept=[]
            for d in ds:
                q=Path(base)/d
                if d in (CONTROL,LOG_ROOT) or d in aliases(DOC_ROOT) or d.endswith('.app'):continue
                if q.is_symlink():extras.append((str(q),'資料夾連結，保留原處'));continue
                kept.append(d)
            ds[:]=kept
            dirs.extend(Path(base)/d for d in ds)
            for name in fs:
                p=Path(base)/name
                if system_file(name):self.system_skipped+=1;self.system_files.append(p);continue
                if p.is_symlink(): extras.append((str(p),'連結，保留原處'))
                elif p.suffix.lower() in AUDIO and not name.startswith('._'): files.append(p)
                else: attachments.append(p)
            self.emit('scan',len(files))
        self.dirs=dirs; self.attachments=attachments; self.extras=extras; return files
    def _protected_intake_root(self,name):
        """Top-level destinations are immutable during normal incremental runs."""
        return (name in (CONTROL,LOG_ROOT) or name.endswith('.app') or
                is_category_root(name) or name in aliases(DOC_ROOT))
    def scan_intake(self):
        """Scan only root-level inbox material, never managed category trees."""
        files=[];attachments=[];extras=[];dirs=[]
        def onerror(e):extras.append((e.filename,'讀取失敗：'+str(e)))
        for base,ds,fs in os.walk(self.root,onerror=onerror,followlinks=False):
            self.checkpoint();base_path=Path(base);kept=[]
            for d in ds:
                q=base_path/d
                protected=(base_path==self.root and self._protected_intake_root(d))
                if protected or d in (CONTROL,LOG_ROOT) or d.endswith('.app'):continue
                if q.is_symlink():extras.append((str(q),'資料夾連結，保留原處'));continue
                kept.append(d)
            ds[:]=kept;dirs.extend(base_path/d for d in ds)
            for name in fs:
                p=base_path/name
                if system_file(name):self.system_skipped+=1;self.system_files.append(p);continue
                if p.is_symlink():extras.append((str(p),'連結，保留原處'))
                elif p.suffix.lower() in AUDIO and not name.startswith('._'):files.append(p)
                else:attachments.append(p)
            self.emit('scan',len(files))
        self.dirs=dirs;self.attachments=attachments;self.extras=extras
        return files
    @staticmethod
    def _intake_identity(p):
        s=Path(p).stat()
        return ('%d:%d'%(s.st_dev,s.st_ino),'%d:%d:%d'%(s.st_size,s.st_mtime_ns,s.st_ctime_ns))
    def _remember_intake(self,meta,current,status,batch,detail=''):
        current=Path(current);key,stat_sig=self._intake_identity(current)
        values=(key,meta['hash'],stat_sig,meta['original'],str(current),status,batch,time.time(),detail)
        self.db.execute('INSERT OR REPLACE INTO intake_files VALUES(?,?,?,?,?,?,?,?,?)',values)
        if key!=meta['key']:
            original_values=(meta['key'],meta['hash'],meta['stat'],meta['original'],str(current),status,batch,time.time(),detail)
            self.db.execute('INSERT OR REPLACE INTO intake_files VALUES(?,?,?,?,?,?,?,?,?)',original_values)
        self.db.commit()
    @staticmethod
    def _log_row(source,category='',renamed='',final='',status='',reason=''):
        source=Path(source)
        return {'original_name':source.name,'original_path':str(source),'category':str(category),
                'renamed_name':str(renamed),'final_path':str(final),'status':str(status),'reason':str(reason)}
    def _write_batch_log(self,batch,rows,started,kind='快速分類'):
        finished=time.time();logs=self.root/LOG_ROOT;logs.mkdir(exist_ok=True)
        stamp=time.strftime('%Y-%m-%d_%H-%M-%S',time.localtime(started));base=logs/('%s_%s'%(stamp,batch[:8]))
        csv_path=base.with_suffix('.csv');txt_path=base.with_suffix('.txt')
        headings=['原始檔名','原始位置','分類結果','更名後檔名','最終完整路徑','處理狀態','原因']
        fields=['original_name','original_path','category','renamed_name','final_path','status','reason']
        tmp_csv=csv_path.with_suffix('.csv.tmp');tmp_txt=txt_path.with_suffix('.txt.tmp')
        with tmp_csv.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(headings);w.writerows([[row.get(k,'') for k in fields] for row in rows])
        counts={}
        for row in rows:counts[row.get('status','')]=counts.get(row.get('status',''),0)+1
        lines=['SoundFX Organizer 本次處理紀錄','工作：'+kind,
               '開始：'+time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(started)),
               '完成：'+time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(finished)),
               '摘要：'+('、'.join('%s %d'%(k,v) for k,v in counts.items() if k) or '沒有發現需要處理的新檔案'),'']
        for i,row in enumerate(rows,1):
            lines.extend(['[%d] %s'%(i,row.get('status','')),
                          '原始：'+row.get('original_path',''),'分類：'+row.get('category',''),
                          '新名：'+row.get('renamed_name',''),'最終：'+row.get('final_path',''),
                          '說明：'+row.get('reason',''),''])
        tmp_txt.write_text('\n'.join(lines),encoding='utf-8');os.replace(tmp_csv,csv_path);os.replace(tmp_txt,txt_path)
        return {'text':str(txt_path),'csv':str(csv_path),'started':started,'finished':finished,'rows':rows,'counts':counts}
    def candidates(self):
        files=self.scan_intake()
        if not self.db.execute("SELECT 1 FROM meta WHERE key='legacy_import'").fetchone():
            protected=set(); prefixes=set()
            p=self.ctl/'state3.json'
            if p.exists():
                old=json.loads(p.read_text('utf-8'))
                prefixes={':'.join(k.split(':')[:2]) for k in old.get('identities',{})}
            p=self.ctl/'database.json'
            if p.exists():
                old=json.loads(p.read_text('utf-8'))
                for row in old.get('files',{}).values():
                    if row.get('category') in ('_待確認','Unclassified') or row.get('confidence')=='low': continue
                    if row.get('lastKnownPath'): protected.add(str(self.root/row['lastKnownPath']))
            for p in files:
                sig=signature(p)
                if str(p) in protected or ':'.join(sig.split(':')[:2]) in prefixes:
                    # Review items are explicitly eligible for optional re-analysis.
                    if not any(x in ('_待確認','_Needs Review','Unclassified') for x in self._relative(p).parts):
                        self.db.execute('INSERT OR REPLACE INTO seen VALUES(?,?)',(sig,str(p)))
            self.db.execute("INSERT INTO meta VALUES('legacy_import','1')"); self.db.commit()
        current={r[0] for r in self.db.execute('SELECT sig FROM file_rules WHERE rule_version=?',(RULE_VERSION,))};pending=[];self.skipped=len(current)
        self.intake={};self.duplicate_rows=[];self.known_pending=[];self.new_audio_found=0
        for p in files:
            self.checkpoint()
            try:
                if signature(p) in current:continue
                key,stat_sig=self._intake_identity(p);row=self.db.execute('SELECT content_hash,stat_sig,status,original_path FROM intake_files WHERE file_key=?',(key,)).fetchone()
                if row and row[1]==stat_sig and row[2] in ('pending','duplicate','classified','attachment'):
                    if row[2]=='pending':self.known_pending.append(str(p))
                    continue
                content_hash=digest(p)
                if row and row[0]==content_hash and row[2]=='pending':
                    meta={'key':key,'stat':stat_sig,'hash':content_hash,'original':row[3]};self._remember_intake(meta,p,'pending','',row[2]);self.known_pending.append(str(p));continue
                duplicate=self.db.execute("SELECT current_path,status FROM intake_files WHERE content_hash=? AND status IN ('classified','attachment','duplicate') ORDER BY updated_at DESC LIMIT 1",(content_hash,)).fetchone()
                meta={'key':key,'stat':stat_sig,'hash':content_hash,'original':str(p)}
                if duplicate:
                    reason='內容與已處理檔案相同：'+duplicate[0]
                    self._remember_intake(meta,p,'duplicate','',reason);self.new_audio_found+=1
                    self.duplicate_rows.append(self._log_row(p,final=p,status='重複，已略過',reason=reason));continue
                self.intake[str(p)]=meta;pending.append(p);self.new_audio_found+=1
            except OSError as e: self.extras.append((str(p),str(e)))
        return pending
    def classify_fast(self,p,readme_text=''):
        """Weighted text sources. Never decodes audio samples."""
        rel=self._relative(p)
        custom=self.custom.classify(rel)
        if custom:return custom
        direct=classify(rel)
        filename_specific=not is_generic(p.stem) and direct and str(direct.get('source','')).startswith('檔名')
        metadata=[]
        for source,text in extract_metadata(p):
            hit=classify(Path(text+p.suffix))
            if hit:
                hit=dict(hit);hit.update(source='Metadata：'+source,evidence=text[:240],confidence=.92,reason_code='metadata')
                metadata.append(hit)
        if filename_specific:return direct
        if metadata:return max(metadata,key=lambda x:x.get('confidence',0))
        if direct:return direct
        if readme_text and is_generic(p.stem):
            hit=classify(Path(readme_text+p.suffix))
            if hit:
                hit=dict(hit);hit.update(source='套件說明文字',evidence=readme_text[:240],confidence=.68,reason_code='package_documentation')
                return hit
        return None
    def _package_key(self,p):
        parts=self._relative(p).parts[:-1]
        for part in parts:
            if not is_category_root(part) and part not in CANONICAL_ROOTS and normal(part) not in ('0 hollywood sound fx','hollywood sound fx'):
                return part
        return parts[0] if parts else '__root__'
    def _readme_context(self,attachments):
        contexts={}
        for p in attachments:
            if p.suffix.lower() not in ('.txt','.md','.nfo'):continue
            try:text=p.read_text('utf-8',errors='replace')[:131072]
            except OSError:continue
            contexts.setdefault(self._package_key(p),[]).append(text)
        return {k:' '.join(v)[:262144] for k,v in contexts.items()}
    def classify_batch(self,files,attachments=None):
        contexts=self._readme_context(attachments or [])
        def inspect(p):
            key=self._package_key(p);return {'path':p,'package':key,'result':self.classify_fast(p,contexts.get(key,''))}
        workers=2 if self.performance!='fast' else min(8,max(2,(os.cpu_count() or 4)//2))
        with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='metadata') as pool:rows=list(pool.map(inspect,files))
        # Package consensus is only for semantically empty names and only when
        # at least 3 clear siblings agree at >=80%; explicit filenames always win.
        groups={}
        for row in rows:
            if row['result'] and not is_generic(row['path'].stem):groups.setdefault(row['package'],[]).append(row['result']['cat'])
        consensus={}
        for key,cats in groups.items():
            if len(cats)<3:continue
            counts={c:cats.count(c) for c in set(cats)};cat,n=max(counts.items(),key=lambda x:x[1])
            if n/len(cats)>=.8:consensus[key]=(cat,n,len(cats))
        for row in rows:
            if row['result'] is None and is_generic(row['path'].stem) and row['package'] in consensus:
                cat,n,total=consensus[row['package']]
                label=re.sub(r'[^A-Za-z0-9]+','_',cat.split('/')[-1]).strip('_')
                row['result']={'cat':cat,'label':label,'source':'依套件同層檔案共識分類','tags':['Package Consensus'],
                    'evidence':'%d/%d 個明確檔案支持'%(n,total),'confidence':round(.72+.18*n/total,2),
                    'reason_code':'package_consensus','rule_version':RULE_VERSION}
        return rows
    def destination(self,p,result,reserved=None):
        reserved=reserved or set(); cat=result['cat']; stem=standardized_stem(self._relative(p),result)
        while len(stem.encode('utf-8'))>210: stem=stem[:-1]
        dest=self.root/render_category(cat,self.folder_style)/(stem+p.suffix.lower())
        if self.root not in dest.resolve().parents: raise ValueError('分類路徑不安全')
        n=1
        while dest!=p and (dest.exists() or dest.is_symlink() or str(dest).casefold() in reserved):
            n+=1; dest=self.root/render_category(cat,self.folder_style)/(stem+'_%03d'%n+p.suffix.lower())
        return dest
    def _mark_current(self,p):
        sig=signature(p)
        self.db.execute('INSERT OR REPLACE INTO seen VALUES(?,?)',(sig,str(p)))
        self.db.execute('INSERT OR REPLACE INTO file_rules VALUES(?,?)',(sig,RULE_VERSION))
    def _record_decision(self,p,result):
        self.db.execute('INSERT OR REPLACE INTO decisions VALUES(?,?,?,?,?,?,?,?)',(
            signature(p),str(p),result.get('cat',''),json.dumps(result.get('tags',[]),ensure_ascii=False),
            result.get('evidence',''),float(result.get('confidence',0)),result.get('source',''),
            int(result.get('rule_version',RULE_VERSION))))
    def move(self,p,result,batch,expected=None,classified=True):
        self.checkpoint()
        if system_file(p.name):raise ValueError('系統附屬檔不會單獨搬移：'+str(p))
        if not p.exists():raise FileNotFoundError('來源檔已不存在；未移除其他檔案：'+str(p))
        sig=signature(p)
        if self.db.execute("SELECT count(*) FROM moves WHERE status='moving'").fetchone()[0]: raise ValueError('先還原上次中斷的操作，才能繼續。')
        dest=Path(expected) if expected else self.destination(p,result)
        if self.root not in dest.resolve().parents or dest.is_symlink(): raise ValueError('目的路徑不安全')
        if p==dest:
            if classified:self._mark_current(p);self._record_decision(p,result)
            self.db.commit(); return p
        if dest.exists(): raise FileExistsError('預覽後目的地出現檔案，請重新預覽：'+str(dest))
        dest.parent.mkdir(parents=True,exist_ok=True)
        cur=self.db.execute('INSERT INTO moves(batch,src,dst,sig,status) VALUES(?,?,?,?,?)',(batch,str(p),str(dest),sig,'moving')); self.db.commit()
        # Same-volume hardlink + unlink: no full-file hash/copy and no overwrite race.
        # If filesystem disallows hardlinks, fail safely rather than fall back to destructive rename.
        if signature(p)!=sig: raise ValueError('來源已變動')
        try: os.link(p,dest)
        except OSError as e:
            if e.errno not in LINK_FALLBACK_ERRNOS: raise
            # exFAT and other filesystems without hardlinks: exclusive, verified copy.
            h=hashlib.sha256();created=False
            try:
                with p.open('rb') as source, dest.open('xb') as target:
                    created=True
                    for block in iter(lambda:source.read(1024*1024),b''):
                        target.write(block); h.update(block)
                    target.flush(); os.fsync(target.fileno())
                verify=hashlib.sha256()
                with dest.open('rb') as f:
                    for block in iter(lambda:f.read(1024*1024),b''): verify.update(block)
                if h.digest()!=verify.digest(): raise ValueError('複製驗證失敗，保留來源')
                source_stat=p.stat()
                try:os.utime(dest,ns=(source_stat.st_atime_ns,source_stat.st_mtime_ns))
                except OSError:pass
                try:os.chmod(dest,source_stat.st_mode & 0o777)
                except OSError:pass
            except BaseException:
                if created and dest.exists() and p.exists():
                    recovery=self.ctl/'Interrupted_Copies'/('%s-%s'%(cur.lastrowid,dest.name));recovery.parent.mkdir(parents=True,exist_ok=True)
                    try:os.replace(dest,recovery)
                    except OSError:pass
                self.db.execute("UPDATE moves SET status='failed' WHERE id=?",(cur.lastrowid,));self.db.commit()
                raise
        if signature(p)!=sig: raise ValueError('來源搬移中變動；兩份均保留，請還原')
        # Preserve AppleDouble metadata before removing its data fork. Some
        # external-drive drivers remove the sidecar as a consequence of unlink.
        side=p.with_name('._'+p.name);side_backup=None
        if side.is_file():
            side_backup=self.ctl/'Metadata_Backups'/str(cur.lastrowid)/side.name
            side_backup.parent.mkdir(parents=True,exist_ok=True)
            with side.open('rb') as source,side_backup.open('xb') as target:
                shutil.copyfileobj(source,target,1024*1024);target.flush();os.fsync(target.fileno())
            if digest(side)!=digest(side_backup):raise ValueError('附屬資訊備份驗證失敗；來源與目的音檔均保留')
        p.unlink()
        if side_backup and side.exists():
            if digest(side)==digest(side_backup):side.unlink()
        self.db.execute('UPDATE moves SET status=?,sig=? WHERE id=?',('done',signature(dest),cur.lastrowid))
        self.db.execute('INSERT OR REPLACE INTO seen VALUES(?,?)',(signature(dest),str(dest)))
        if classified:
            self.db.execute('INSERT OR REPLACE INTO file_rules VALUES(?,?)',(signature(dest),RULE_VERSION));self._record_decision(dest,result)
        self.db.commit()
        return dest
    def _safe_piece(self,value):
        value=re.sub(r'(?i)[ _.-]*20\d{2}(?:[ _.-]\d{2}){5}[ _.-]*utc$','',str(value))
        value=re.sub(r'[^A-Za-z0-9 _.-]+','_',value).strip(' ._-')
        return value[:100] or 'Source_Package'
    def attachment_destination(self,p,reserved=None):
        reserved=reserved or set(); parts=self._relative(p).parts[:-1]; package='Root Files'
        for part in parts:
            n=normal(part)
            if is_category_root(part) or part in CANONICAL_ROOTS or n in ('0 hollywood sound fx','hollywood sound fx') or is_generic(part):continue
            package=self._safe_piece(part);break
        sub='' if p.suffix.lower() in DOC_EXTS else 'Other Files'
        dest=self.root/render_category(DOC_ROOT,self.folder_style)/package
        if sub:dest=dest/sub
        dest=dest/p.name; n=1
        while dest.exists() or dest.is_symlink() or str(dest).casefold() in reserved:
            n+=1;dest=dest.with_name('%s_%03d%s'%(p.stem,n,p.suffix))
        if self.root not in dest.resolve().parents:raise ValueError('附件路徑不安全')
        return dest
    def fast(self):
        started=time.time();self.migrate_category_roots()
        files=self.candidates();attachments=list(self.attachments);batch=uuid.uuid4().hex;rest=list(self.known_pending);moved=0;docs=0;doc_rows=[];reserved=set();log_rows=list(self.duplicate_rows)
        new_attachments=[]
        for p in attachments:
            try:
                key,stat_sig=self._intake_identity(p);row=self.db.execute('SELECT content_hash,stat_sig,status,original_path FROM intake_files WHERE file_key=?',(key,)).fetchone()
                if row and row[1]==stat_sig and row[2] in ('attachment','duplicate'):continue
                content_hash=digest(p);duplicate=self.db.execute("SELECT current_path FROM intake_files WHERE content_hash=? AND status IN ('classified','attachment','duplicate') ORDER BY updated_at DESC LIMIT 1",(content_hash,)).fetchone()
                meta={'key':key,'stat':stat_sig,'hash':content_hash,'original':str(p)}
                if duplicate:
                    reason='內容與已處理檔案相同：'+duplicate[0];self._remember_intake(meta,p,'duplicate','',reason);self.new_attachment_found+=1
                    log_rows.append(self._log_row(p,final=p,status='重複，已略過',reason=reason));continue
                self.intake[str(p)]=meta;new_attachments.append(p);self.new_attachment_found+=1
            except OSError as e:self.extras.append((str(p),str(e)))
        attachments=new_attachments
        classified=self.classify_batch(files,attachments)
        details=[]
        for i,row in enumerate(classified):
            p=row['path'];original=str(p);self.checkpoint();result=row['result'];meta=self.intake.get(original)
            if not p.exists():
                reason='掃描後來源已不存在，未標示為成功';self.extras.append((original,reason));log_rows.append(self._log_row(original,status='失敗',reason=reason));continue
            try:
                if result:
                    dest=self.move(p,result,batch);moved+=1
                    if meta:self._remember_intake(meta,dest,'classified',batch,result.get('source',''))
                    log_rows.append(self._log_row(original,render_category(result['cat'],self.folder_style),dest.name,dest,'成功',result.get('source','')))
                else:
                    rest.append(original)
                    if meta:self._remember_intake(meta,p,'pending',batch,'快速分類無法確定')
                    log_rows.append(self._log_row(original,final=original,status='待判斷',reason='快速分類無法確定；可使用音訊辨識'))
            except Stopped:raise
            except Exception as exc:
                reason=str(exc);self.extras.append((original,reason));log_rows.append(self._log_row(original,final=original,status='失敗',reason=reason))
            details.append({'path':str(p),'result':result})
            self.emit('progress',i+1,len(files)+len(attachments),p.name)
        for j,p in enumerate(attachments):
            self.checkpoint();original=str(p);meta=self.intake.get(original)
            if system_file(p.name):continue
            if not p.exists():
                reason='掃描後附件已不存在，保留其他檔案';self.extras.append((original,reason));log_rows.append(self._log_row(original,status='失敗',reason=reason));continue
            try:
                dest=self.attachment_destination(p,reserved);reserved.add(str(dest).casefold())
                self.move(p,{'cat':'','label':''},batch,expected=dest,classified=False);docs+=1;doc_rows.append((str(dest),'附件已集中保存'))
                if meta:self._remember_intake(meta,dest,'attachment',batch,'附件已集中保存')
                log_rows.append(self._log_row(original,render_category(DOC_ROOT,self.folder_style),dest.name,dest,'成功','附件已集中保存'))
            except Stopped:raise
            except Exception as exc:
                reason=str(exc);self.extras.append((original,reason));log_rows.append(self._log_row(original,final=original,status='失敗',reason=reason))
            self.emit('progress',len(files)+j+1,len(files)+len(attachments),p.name)
        self.cleanup();self.export();log=self._write_batch_log(batch,log_rows,started)
        return {'moved':moved,'attachments_moved':docs,'attachments':doc_rows,'pending':rest,'details':details,'extras':self.extras,'skipped':self.skipped,'system_skipped':self.system_skipped,'rule_version':RULE_VERSION,'log':log,'log_rows':log_rows,'new_audio_found':self.new_audio_found,'new_attachment_found':self.new_attachment_found,'duplicates':sum(1 for r in log_rows if r['status'].startswith('重複')),'failed':sum(1 for r in log_rows if r['status']=='失敗')}

    def migrate_category_roots(self):
        """Migrate only files proven to have been placed by this app."""
        desired={top:self.root/render_category(top,self.folder_style) for top in TOP_ZH}
        batch='folder-language-'+uuid.uuid4().hex
        for top,target_root in desired.items():
            for name in aliases(top):
                old_root=self.root/name
                if old_root==target_root or not old_root.is_dir() or old_root.is_symlink():continue
                for p in sorted(old_root.rglob('*')):
                    if not p.is_file() or p.is_symlink() or system_file(p.name):continue
                    sig=signature(p);was_current=self.db.execute('SELECT 1 FROM file_rules WHERE sig=? AND rule_version=?',(sig,RULE_VERSION)).fetchone()
                    proof=self.db.execute("SELECT 1 FROM moves WHERE dst=? AND status='done'",(str(p),)).fetchone()
                    if not proof:continue
                    relative=translate_known_path(p.relative_to(old_root),self.folder_style);dest=target_root/relative;n=1
                    while dest.exists():n+=1;dest=dest.with_name(p.stem+'_%03d'%n+p.suffix)
                    self.move(p,{'cat':'','label':''},batch,expected=dest,classified=False)
                    new_sig=signature(dest)
                    if was_current:self.db.execute('INSERT OR REPLACE INTO file_rules VALUES(?,?)',(new_sig,RULE_VERSION))
                    self.db.execute('UPDATE decisions SET sig=?,path=? WHERE path=?',(new_sig,str(dest),str(p)))
                    self.db.commit()
                for d in sorted(old_root.rglob('*'),key=lambda x:len(x.parts),reverse=True)+[old_root]:
                    try:d.rmdir()
                    except OSError:pass

    def learn(self,paths,category):
        """Create conservative local filename rules from a reviewed batch."""
        added=[]
        for name in paths:
            p=Path(name);stem=normal(p.stem)
            if is_generic(stem):continue
            words=[w for w in stem.split() if not w.isdigit()]
            phrase=' '.join(words[:6])
            if phrase:added.append(self.custom.add(phrase,category,scope='filename'))
        return added
    def listen(self,paths,analyzer):
        started=time.time();batch=uuid.uuid4().hex;moved=0;rest=[];log_rows=[]
        for i,name in enumerate(paths):
            self.checkpoint(); p=Path(name)
            if not p.exists():
                rest.append(name);log_rows.append(self._log_row(name,status='失敗',reason='音訊辨識前來源已不存在'));continue
            sig=signature(p); row=self.db.execute('SELECT result FROM audio WHERE sig=?',(sig,)).fetchone()
            try:
                result=json.loads(row[0]) if row else analyzer(p)
                if not row: self.db.execute('INSERT OR REPLACE INTO audio VALUES(?,?)',(sig,json.dumps(result))); self.db.commit()
            except Stopped: raise
            except Exception as e:
                reason='音訊辨識失敗：'+str(e);self.extras.append((str(p),reason));rest.append(name);log_rows.append(self._log_row(name,final=name,status='失敗',reason=reason));continue
            if result.get('accepted'):
                original=str(p);classified=audio_category(result);dest=self.move(p,classified,batch);moved+=1
                key,stat_sig=self._intake_identity(dest);known=self.db.execute('SELECT content_hash,original_path FROM intake_files WHERE current_path=? ORDER BY updated_at DESC LIMIT 1',(original,)).fetchone()
                meta={'key':key,'stat':stat_sig,'hash':known[0] if known else digest(dest),'original':known[1] if known else original}
                self.db.execute("UPDATE intake_files SET current_path=?,status='classified',batch=?,updated_at=?,detail=? WHERE current_path=?",(str(dest),batch,time.time(),'音訊辨識',original))
                self._remember_intake(meta,dest,'classified',batch,result.get('source','音訊辨識'))
                log_rows.append(self._log_row(meta['original'],render_category(classified['cat'],self.folder_style),dest.name,dest,'成功','音訊辨識'))
            else:
                rest.append(name);log_rows.append(self._log_row(name,final=name,status='略過',reason='音訊辨識未達接受門檻'))
            self.emit('progress',i+1,len(paths),p.name)
        self.cleanup();self.export();log=self._write_batch_log(batch,log_rows,started,'音訊辨識')
        return {'moved':moved,'pending':rest,'extras':self.extras,'log':log,'log_rows':log_rows,'new_audio_found':len(paths),'new_attachment_found':0,'duplicates':0,'failed':sum(1 for r in log_rows if r['status']=='失敗')}
    def cleanup(self):
        for p in sorted(getattr(self,'dirs',[]),key=lambda x:len(x.parts),reverse=True):
            try: p.rmdir()
            except OSError: pass
    def repair_plan(self):
        files=self.scan(); rows=[]; pending=[]; reserved=set()
        current={r[0] for r in self.db.execute('SELECT sig FROM file_rules WHERE rule_version=?',(RULE_VERSION,))}
        for i,p in enumerate(files):
            self.checkpoint()
            if signature(p) in current:
                self.emit('progress',i+1,len(files),p.name); continue
            r=classify(self._relative(p))
            if r:
                dest=self.destination(p,r,reserved)
                if p!=dest:
                    rows.append({'src':str(p),'dst':str(dest),'sig':signature(p),'result':r})
                    reserved.add(str(dest).casefold())
            else: pending.append(str(p))
            self.emit('progress',i+1,len(files),p.name)
        return rows,pending
    def low_quality_plan(self,files=None):
        if files is None: files=self.scan()
        pairs=low_candidates(files); rows=[]
        for i,(keep,remove) in enumerate(pairs):
            self.checkpoint(); self.emit('quality',i+1,len(pairs),remove.name)
            try:
                r=compare_quality(keep,remove)
                if r: rows.append(r)
            except Exception as e:self.extras.append((str(remove),'音質副本檢測未通過，完全保留：'+str(e)))
        return rows
    def apply_low_quality(self,rows):
        batch='quality-'+uuid.uuid4().hex; moved=0
        for i,row in enumerate(rows):
            self.checkpoint(); p=Path(row['remove'])
            dest=self.ctl/'LowQuality_Quarantine'/batch/self._relative(p)
            self.move(p,{'cat':'','label':''},batch,expected=dest,classified=False); moved+=1
            self.emit('progress',i+1,len(rows),p.name)
        self.export(); return moved
    def quarantine_summary(self):
        base=self.ctl/'LowQuality_Quarantine'; count=0; size=0
        if not base.exists(): return {'count':0,'bytes':0}
        for p in base.rglob('*'):
            if p.is_file() and not p.is_symlink():
                count+=1
                try:size+=p.stat().st_size
                except OSError:pass
        return {'count':count,'bytes':size}
    def purge_quarantine(self):
        """Permanently remove only regular files inside our exact quarantine tree."""
        base=(self.ctl/'LowQuality_Quarantine').resolve()
        if not base.exists(): return {'count':0,'bytes':0}
        if self.root not in base.parents or base.name!='LowQuality_Quarantine':
            raise ValueError('隔離區路徑安全檢查失敗')
        count=0; size=0; entries=sorted(base.rglob('*'),key=lambda x:len(x.parts),reverse=True)
        # Complete preflight before the first irreversible unlink.
        for p in entries:
            if p.is_symlink(): raise ValueError('隔離區含連結，為避免誤刪已停止：'+str(p))
            if base not in p.resolve().parents: raise ValueError('項目超出隔離區，已停止')
            if not (p.is_file() or p.is_dir()): raise ValueError('隔離區含不支援項目，已停止：'+str(p))
        files=[p for p in entries if p.is_file()]
        for p in entries:
            self.checkpoint()
            if p.is_file():
                n=p.stat().st_size; p.unlink(); count+=1; size+=n
                self.db.execute("UPDATE moves SET status='purged' WHERE dst=? AND status='done'",(str(p),))
                self.db.commit(); self.emit('progress',count,max(1,len(files)),p.name)
            elif p.is_dir():
                try:p.rmdir()
                except OSError:pass
        try:base.rmdir()
        except OSError:pass
        self.export(); return {'count':count,'bytes':size}
    def apply_repair(self,rows,pending):
        batch=uuid.uuid4().hex
        for i,row in enumerate(rows):
            self.checkpoint(); p=Path(row['src'])
            if signature(p)!=row['sig']: raise ValueError('預覽後來源檔案有變動，已停止：'+str(p))
            self.move(p,row['result'],batch,expected=row['dst'])
            self.emit('progress',i+1,len(rows),p.name)
        # Explicit repair releases incorrectly protected unknowns for the optional AI stage.
        for p in pending:
            if Path(p).exists(): self.db.execute('DELETE FROM seen WHERE sig=?',(signature(Path(p)),))
        self.db.commit(); self.cleanup(); self.export()
        return {'moved':len(rows),'pending':pending,'extras':self.extras}
    def export(self):
        (self.ctl/'diagnostics.json').write_text(json.dumps({'version':'5.0.3','folder_style':self.folder_style,'system_files_excluded':self.system_skipped,'issues':getattr(self,'extras',[]),'journal':self.db.execute('SELECT status,count(*) FROM moves GROUP BY status').fetchall()},ensure_ascii=False,indent=2),encoding='utf-8')
        with (self.ctl/'原名新名對照.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f); w.writerow(['批次','原路徑','新路徑','狀態']); w.writerows(self.db.execute('SELECT batch,src,dst,status FROM moves ORDER BY id'))
        with (self.ctl/'分類判斷紀錄.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(['目前路徑','主要分類','次要搜尋標籤','使用線索','信心分數','判斷原因','規則版本'])
            w.writerows(self.db.execute('SELECT path,category,tags,evidence,confidence,reason,rule_version FROM decisions ORDER BY path'))
    def undo(self):
        row=self.db.execute("SELECT batch FROM moves WHERE status IN ('done','moving') ORDER BY id DESC LIMIT 1").fetchone()
        if not row: return 0
        batch=row[0];rows=self.db.execute("SELECT id,src,dst,sig,status FROM moves WHERE batch=? AND status IN ('done','moving') ORDER BY id DESC",row).fetchall()
        for i,(id,src,dst,sig,status) in enumerate(rows):
            self.checkpoint(); a=Path(src); b=Path(dst)
            if a.exists():
                if status!='moving': raise ValueError('原位置已存在檔案，停止以避免覆蓋：'+src)
                if b.exists():
                    if not os.path.samefile(a,b): raise ValueError('兩個位置內容可能不同，保留兩份：'+src)
                    b.unlink()
            else:
                if signature(b)!=sig: raise ValueError('還原檔案已變動，停止：'+dst)
                a.parent.mkdir(parents=True,exist_ok=True)
                try: os.link(b,a)
                except OSError as e:
                    if e.errno not in (errno.EPERM,errno.EOPNOTSUPP,errno.EXDEV,errno.ENOSYS): raise
                    with b.open('rb') as source,a.open('xb') as target: shutil.copyfileobj(source,target,1024*1024)
                    def sha(p):
                        h=hashlib.sha256()
                        with p.open('rb') as f:
                            for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
                        return h.digest()
                    if sha(a)!=sha(b): raise ValueError('還原驗證失敗，保留兩份')
                    shutil.copystat(b,a)
                b.unlink()
            self.db.execute('DELETE FROM seen WHERE sig=?',(sig,))
            self.db.execute('DELETE FROM file_rules WHERE sig=?',(sig,))
            self.db.execute('DELETE FROM decisions WHERE sig=?',(sig,))
            self.db.execute("UPDATE moves SET status='restored' WHERE id=?",(id,)); self.db.commit()
            self.emit('progress',i+1,len(rows),a.name)
        # A restored source is inbox material again and must be eligible for a
        # future explicit run.  Remove only the exact batch's incremental rows.
        self.db.execute('DELETE FROM intake_files WHERE batch=?',(batch,));self.db.commit()
        self.export(); return len(rows)
