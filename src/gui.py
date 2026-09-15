import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import threading,queue,time,os,sys,subprocess,json,platform,traceback,zipfile
from pathlib import Path
from engine import Engine,Stopped
from i18n import I18n,LABELS
from categories import SEMANTIC,convert

class App:
    def __init__(self,root):
        self.root=root; root.geometry('1120x780'); root.minsize(980,700)
        self.events=queue.Queue(); self.stop=threading.Event(); self.pause=threading.Event(); self.busy=False; self.pending=[]; self.entries=[]
        self.base=Path.home()/'Library/Application Support/SoundFX4'; self.base.mkdir(parents=True,exist_ok=True)
        self.pref=self.base/'settings.json'
        try: saved=json.loads(self.pref.read_text())
        except (OSError,ValueError): saved={}
        self.i18n=I18n(saved.get('language','system')); self.folder=tk.StringVar(value=saved.get('folder','')); self.mode=tk.StringVar(value=saved.get('mode','quiet'));self.mode_display=tk.StringVar()
        self.folder_style=tk.StringVar(value=saved.get('folder_style','bilingual'));self.folder_style_display=tk.StringVar()
        frame=ttk.Frame(root,padding=24); frame.pack(fill='both',expand=True)
        head=ttk.Frame(frame);head.pack(fill='x')
        self.hero=ttk.Label(head,font=('Helvetica',24,'bold'));self.hero.pack(side='left')
        self.lang_label=ttk.Label(head);self.lang_label.pack(side='right',padx=(8,0))
        self.language=tk.StringVar(value=LABELS.get(self.i18n.choice,LABELS['system']))
        self.lang_combo=ttk.Combobox(head,textvariable=self.language,values=list(LABELS.values()),state='readonly',width=24);self.lang_combo.pack(side='right')
        self.lang_combo.bind('<<ComboboxSelected>>',self.change_language)
        self.subtitle=ttk.Label(frame,font=('Helvetica',13));self.subtitle.pack(anchor='w',pady=(8,20))
        top=ttk.Frame(frame); top.pack(fill='x')
        self.pathentry=ttk.Entry(top,textvariable=self.folder,state='readonly'); self.pathentry.pack(side='left',fill='x',expand=True)
        self.choose=ttk.Button(top,command=self.select); self.choose.pack(side='left',padx=(10,0))
        opts=ttk.Frame(frame); opts.pack(fill='x',pady=14)
        self.resource_label=ttk.Label(opts);self.resource_label.pack(side='left')
        self.combo=ttk.Combobox(opts,textvariable=self.mode_display,state='readonly',width=14); self.combo.pack(side='left',padx=10);self.combo.bind('<<ComboboxSelected>>',self.change_mode)
        self.hardware=ttk.Label(opts,text=platform.machine()+' · adaptive worker scheduling');self.hardware.pack(side='left')
        self.folder_style_label=ttk.Label(opts);self.folder_style_label.pack(side='left',padx=(22,4))
        self.folder_style_combo=ttk.Combobox(opts,textvariable=self.folder_style_display,state='readonly',width=20);self.folder_style_combo.pack(side='left');self.folder_style_combo.bind('<<ComboboxSelected>>',self.change_folder_style)
        self.title=tk.StringVar(); self.desc=tk.StringVar()
        ttk.Label(frame,textvariable=self.title,font=('Helvetica',17,'bold')).pack(anchor='w',pady=(10,6))
        ttk.Label(frame,textvariable=self.desc,wraplength=850).pack(anchor='w')
        self.bar=ttk.Progressbar(frame,mode='determinate',maximum=100); self.bar.pack(fill='x',pady=14)
        self.detail=tk.StringVar(); ttk.Label(frame,textvariable=self.detail).pack(anchor='w')
        controls=ttk.Frame(frame); controls.pack(fill='x',pady=16)
        self.fast=ttk.Button(controls,command=lambda:self.start('fast')); self.fast.pack(side='left')
        self.ai=ttk.Button(controls,command=lambda:self.start('ai'),state='disabled'); self.ai.pack(side='left',padx=8)
        self.quality=ttk.Button(controls,command=lambda:self.start('quality')); self.quality.pack(side='left')
        self.pb=ttk.Button(controls,command=self.toggle,state='disabled'); self.pb.pack(side='left')
        self.cancel=ttk.Button(controls,command=self.stop.set,state='disabled'); self.cancel.pack(side='left',padx=8)
        self.undo=ttk.Button(controls,command=lambda:self.start('undo')); self.undo.pack(side='right')
        self.purge=ttk.Button(controls,command=lambda:self.start('purge')); self.purge.pack(side='right',padx=8)
        self.tree=ttk.Treeview(frame,columns=('file','suggestion','confidence','reason'),show='headings',height=12,selectmode='extended')
        self.tree.column('file',width=470);self.tree.column('suggestion',width=260);self.tree.column('confidence',width=75);self.tree.column('reason',width=230)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=self.tree.yview); self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y'); self.tree.pack(fill='both',expand=True); self.tree.bind('<Double-1>',self.reveal)
        review=ttk.Frame(frame);review.pack(fill='x',pady=(10,0))
        self.review_category=tk.StringVar();cats=sorted({convert(r[2]) for r in SEMANTIC})
        self.category_combo=ttk.Combobox(review,textvariable=self.review_category,values=cats,state='readonly',width=47);self.category_combo.pack(side='left')
        self.assign=ttk.Button(review,command=self.assign_selected);self.assign.pack(side='left',padx=6)
        self.play=ttk.Button(review,command=self.preview_audio);self.play.pack(side='left')
        self.finder=ttk.Button(review,command=self.reveal);self.finder.pack(side='left',padx=6)
        self.export_rules=ttk.Button(review,command=self.export_custom_rules);self.export_rules.pack(side='right')
        self.import_rules=ttk.Button(review,command=self.import_custom_rules);self.import_rules.pack(side='right',padx=6)
        self.manage_rules=ttk.Button(review,command=self.manage_custom_rules);self.manage_rules.pack(side='right')
        self.review_hint=ttk.Label(frame);self.review_hint.pack(anchor='w',pady=(8,0))
        self.diagnostics=ttk.Button(frame,command=self.export_diagnostics);self.diagnostics.pack(anchor='e',pady=(6,0))
        self.refresh_text()
        root.protocol('WM_DELETE_WINDOW',self.close); root.after(100,self.pump)
    def select(self):
        p=filedialog.askdirectory(title=self.t('choose_title'))
        if p: self.folder.set(p); self.pending=[]; self.ai.config(state='disabled')
    def t(self,key,**values):return self.i18n.t(key,**values)
    def refresh_text(self):
        self.root.title(self.t('app_title'));self.hero.config(text=self.t('hero'));self.subtitle.config(text=self.t('subtitle'))
        self.lang_label.config(text=self.t('language'));self.choose.config(text=self.t('choose'));self.resource_label.config(text=self.t('resource'))
        self.folder_style_label.config(text=self.t('folder_naming'))
        self.fast.config(text=self.t('fast_button'));self.ai.config(text=self.t('ai_button'));self.quality.config(text=self.t('quality_button'))
        self.pb.config(text=self.t('pause'));self.cancel.config(text=self.t('stop'));self.undo.config(text=self.t('undo'));self.purge.config(text=self.t('purge'))
        self.tree.heading('file',text=self.t('file_column'));self.tree.heading('suggestion',text=self.t('suggestion_column'));self.tree.heading('confidence',text=self.t('confidence_column'));self.tree.heading('reason',text=self.t('reason_column'))
        self.assign.config(text=self.t('assign'));self.play.config(text=self.t('play'));self.finder.config(text=self.t('finder'));self.export_rules.config(text=self.t('export_rules'));self.import_rules.config(text=self.t('import_rules'));self.manage_rules.config(text=self.t('manage_rules'));self.review_hint.config(text=self.t('review_hint'))
        self.diagnostics.config(text=self.t('diagnostics'))
        modes=[self.t('quiet'),self.t('fast_mode')];self.combo.config(values=modes);self.mode_display.set(modes[0] if self.mode.get()=='quiet' else modes[1])
        styles=[self.t('folder_bilingual'),self.t('folder_zh'),self.t('folder_en')];self.folder_style_combo.config(values=styles)
        self.folder_style_display.set(styles[{'bilingual':0,'zh-Hant':1,'en':2}.get(self.folder_style.get(),0)])
        if not self.busy:self.title.set(self.t('ready'));self.desc.set(self.t('fast_description'));self.detail.set(self.t('waiting'))
    def change_language(self,event=None):
        choice=next((k for k,v in LABELS.items() if v==self.language.get()),'system');self.i18n.set(choice);self.refresh_text();self.save_preferences()
    def change_mode(self,event=None):
        self.mode.set('fast' if self.mode_display.get()==self.t('fast_mode') else 'quiet');self.save_preferences()
    def change_folder_style(self,event=None):
        choices={self.t('folder_bilingual'):'bilingual',self.t('folder_zh'):'zh-Hant',self.t('folder_en'):'en'}
        self.folder_style.set(choices.get(self.folder_style_display.get(),'bilingual'));self.save_preferences()
    def save_preferences(self):
        self.pref.write_text(json.dumps({'folder':self.folder.get(),'mode':self.mode.get(),'language':self.i18n.choice,'folder_style':self.folder_style.get()}))
    def engine(self,folder=None,**kwargs):
        return Engine(folder or self.folder.get(),folder_style=self.folder_style.get(),**kwargs)
    def export_diagnostics(self):
        target=filedialog.asksaveasfilename(defaultextension='.zip',initialfile='SoundFX_Diagnostics.zip')
        if not target:return
        try:
            with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
                for p in (self.base/'error.log',Path(self.folder.get())/'.soundfx_organizer/diagnostics.json'):
                    if p.is_file():z.write(p,p.name)
            messagebox.showinfo(self.t('diagnostics'),self.t('diagnostics_saved'))
        except OSError as ex:messagebox.showerror(self.t('diagnostics'),str(ex))
    def toggle(self):
        if self.pause.is_set(): self.pause.clear(); self.pb.config(text=self.t('pause'))
        else: self.pause.set(); self.pb.config(text=self.t('resume')); self.detail.set(self.t('pause'))
    def close(self):
        if self.busy: messagebox.showinfo(self.t('busy_title'),self.t('busy_body')); return
        self.root.destroy()
    def start(self,task):
        if self.busy: return
        folder=self.folder.get()
        if not Path(folder).is_dir(): messagebox.showerror(self.t('choose'),self.t('no_folder')); return
        if task=='fast' and not messagebox.askokcancel(self.t('start_title'),self.t('start_body')): return
        if task=='ai' and not messagebox.askokcancel(self.t('ai_title'),self.t('ai_body',count=len(self.pending))): return
        if task=='undo' and not messagebox.askokcancel(self.t('undo_title'),self.t('undo_body')): return
        if task=='quality' and not messagebox.askokcancel(self.t('quality_title'),self.t('quality_body')): return
        if task=='purge':
            try:
                e=self.engine(folder); info=e.quarantine_summary(); e.close()
            except Exception as ex: messagebox.showerror('無法檢查隔離區',str(ex)); return
            if not info['count']: messagebox.showinfo('隔離區是空的','目前沒有可永久清除的低音質副本。'); return
            size=self.human_bytes(info['bytes'])
            if not messagebox.askyesno('永久清除隔離區','將永久刪除 %d 個已隔離副本（%s）。\n\n清除後無法使用「還原最近一批」復原。只有先前通過嚴格名稱、格式、長度及波形比對，且已由你確認隔離的檔案會被刪除。確定繼續？'%(info['count'],size),icon='warning'): return
        self.save_preferences()
        self.busy=True; self.stop.clear(); self.pause.clear(); self.started=time.monotonic()
        for w in [self.fast,self.ai,self.quality,self.undo,self.choose,self.purge]: w.config(state='disabled')
        self.combo.config(state='disabled');self.folder_style_combo.config(state='disabled'); self.cancel.config(state='normal'); self.pb.config(state='normal',text='暫停')
        self.title.set({'fast':'正在快速分類','ai':'準備音訊辨識','quality':'準備檢查音質副本','undo':'正在還原','repair':'檢查舊版歸檔位置','purge':'正在永久清除隔離區'}[task]); self.bar.config(mode='indeterminate'); self.bar.start(15)
        args=(task,folder,list(self.pending),self.mode.get(),self.folder_style.get())
        threading.Thread(target=self.work,args=args,daemon=True).start()
    def emit(self,*args): self.events.put(args)
    @staticmethod
    def human_bytes(n):
        value=float(n)
        for unit in ('B','KB','MB','GB','TB'):
            if value<1024 or unit=='TB': return ('%.1f %s'%(value,unit)) if unit!='B' else ('%d B'%value)
            value/=1024
    def command(self,args,log):
        with log.open('a') as f:
            proc=subprocess.Popen(args,stdout=f,stderr=f)
            while proc.poll() is None:
                if self.stop.wait(.2): proc.terminate(); proc.wait(); raise Stopped()
            if proc.returncode: raise RuntimeError('安裝失敗：'+log.read_text(errors='replace')[-1400:])
    def bundled_ai_worker(self):
        """Return the frozen, architecture-matched audio helper.

        A released app must never invoke the user's Python installation.  The
        helper is built on the same architecture as the app and lives inside
        the signed bundle.  Source checkouts may explicitly opt in to the
        current interpreter for developer tests only.
        """
        candidates=[]
        if getattr(sys,'frozen',False):
            bundle=Path(sys.executable).resolve().parents[1]
            candidates.extend((bundle/'Resources/ai_worker/ai_worker',bundle/'MacOS/ai_worker'))
        if os.environ.get('SOUNDFX_DEV_AI')=='1':
            candidates.append(Path(__file__).with_name('ai_worker.py'))
        for candidate in candidates:
            if candidate.is_file():return candidate
        raise RuntimeError('此版本未包含相容的本機音訊辨識元件。快速文字分類不受影響；請匯出診斷資訊。')
    def analyzer(self,mode):
        worker=self.bundled_ai_worker()
        self.emit('stage','載入聲音模型','首次需下載模型資料；完成後顯示逐檔進度。')
        args=[str(worker)] if worker.suffix!='.py' else [sys.executable,str(worker)]
        if mode=='fast':args.append('--accelerated')
        env=os.environ.copy(); env['HF_HOME']=str(self.base/'models'); env['HF_HUB_DISABLE_TELEMETRY']='1'
        err=(self.base/'audio.log').open('a')
        proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,text=True,bufsize=1,env=env)
        responses=queue.Queue()
        def read():
            for line in proc.stdout:
                try: responses.put(json.loads(line))
                except ValueError: pass
            responses.put({'error':'音訊服務已結束，請查看 audio.log。'})
        threading.Thread(target=read,daemon=True).start()
        def receive():
            while True:
                if self.stop.is_set(): raise Stopped()
                try:
                    result=responses.get(timeout=.2)
                    if 'error' in result: raise RuntimeError(result['error'])
                    return result
                except queue.Empty: pass
        try: receive()
        except BaseException: proc.terminate(); proc.wait(); err.close(); raise
        def analyze(p):
            proc.stdin.write(json.dumps({'path':str(p)})+'\n'); proc.stdin.flush(); return receive()['result']
        def cleanup(): proc.terminate(); proc.wait(); err.close()
        return analyze,cleanup
    def work(self,task,folder,pending,mode,folder_style):
        e=None; clean=None
        try:
            e=Engine(folder,self.emit,self.stop,self.pause,performance=mode,folder_style=folder_style)
            if task=='fast':
                result=e.fast()
            elif task=='quality':
                qrows=e.low_quality_plan(); answer={'apply':False}; ready=threading.Event()
                if qrows:
                    self.emit('quality_preview',qrows,answer,ready)
                    while not ready.wait(.2):
                        if self.stop.is_set(): raise Stopped()
                    moved=e.apply_low_quality(qrows) if answer['apply'] else 0
                else:moved=0
                result={'moved':moved,'quality_found':len(qrows),'pending':pending,'extras':e.extras}
            elif task=='repair':
                rows,pending=e.repair_plan(); answer={'apply':False}; ready=threading.Event()
                self.emit('repair_preview',rows,pending,answer,ready)
                while not ready.wait(.2):
                    if self.stop.is_set(): raise Stopped()
                if not answer['apply']: raise Stopped()
                result=e.apply_repair(rows,pending)
            elif task=='undo': result={'moved':e.undo(),'pending':pending,'extras':[]}
            elif task=='purge':
                info=e.purge_quarantine(); result={'moved':info['count'],'purged_bytes':info['bytes'],'pending':pending,'extras':[]}
            else:
                e.extras=[]; e.dirs=[]; analyze,clean=self.analyzer(mode); result=e.listen(pending,analyze)
            self.emit('done',task,result)
        except Stopped: self.emit('stopped')
        except Exception as ex:
            if e:
                try:e.export()
                except Exception:pass
            (self.base/'error.log').write_text(traceback.format_exc()); self.emit('error',str(ex))
        finally:
            if clean: clean()
            if e: e.close()
            self.emit('idle')
    def reveal(self,event=None):
        ids=self.tree.selection()
        if ids:
            path=self.tree.item(ids[0],'values')[0]
            if Path(path).exists(): subprocess.Popen(['/usr/bin/open','-R',path])
    def preview_audio(self):
        ids=self.tree.selection()
        if ids:
            path=Path(self.tree.item(ids[0],'values')[0])
            if path.exists() and Path('/usr/bin/afplay').exists():subprocess.Popen(['/usr/bin/afplay',str(path)])
    def assign_selected(self):
        paths=[self.tree.item(i,'values')[0] for i in self.tree.selection()]
        category=self.review_category.get()
        if not paths or not category:return
        try:
            e=self.engine();added=e.learn(paths,category);e.close()
            if not added:messagebox.showinfo(self.t('completed'),'Selected names were code-only; no unsafe broad rule was created.');return
            self.pending=[p for p in self.pending if p not in paths]
            self.start('fast')
        except Exception as ex:messagebox.showerror(self.t('completed'),str(ex))
    def export_custom_rules(self):
        path=filedialog.asksaveasfilename(defaultextension='.json',initialfile='SoundFX_Custom_Rules.json')
        if not path:return
        try:
            e=self.engine();e.custom.export_to(path);e.close()
        except Exception as ex:messagebox.showerror(self.t('export_rules'),str(ex))
    def import_custom_rules(self):
        path=filedialog.askopenfilename(filetypes=[('JSON','*.json')])
        if not path:return
        try:
            e=self.engine();e.custom.import_from(path);e.close();messagebox.showinfo(self.t('import_rules'),self.t('completed'))
        except Exception as ex:messagebox.showerror(self.t('import_rules'),str(ex))
    def manage_custom_rules(self):
        try:e=self.engine()
        except Exception as ex:messagebox.showerror(self.t('manage_rules'),str(ex));return
        win=tk.Toplevel(self.root);win.title(self.t('manage_rules'));win.geometry('760x420');win.transient(self.root);win.grab_set()
        tree=ttk.Treeview(win,columns=('enabled','pattern','category'),show='headings');tree.heading('enabled',text=self.t('enabled'));tree.heading('pattern',text=self.t('pattern'));tree.heading('category',text=self.t('category'));tree.column('enabled',width=80);tree.column('pattern',width=230);tree.column('category',width=400);tree.pack(fill='both',expand=True,padx=12,pady=12)
        def load():
            tree.delete(*tree.get_children())
            for r in e.custom.rows:tree.insert('','end',iid=r['id'],values=('✓' if r.get('enabled',True) else '—',r.get('pattern',''),r.get('category','')))
        def toggle():
            if tree.selection():e.custom.toggle(tree.selection()[0]);load()
        def delete():
            if tree.selection():e.custom.delete(tree.selection()[0]);load()
        bar=ttk.Frame(win);bar.pack(fill='x',padx=12,pady=(0,12));ttk.Button(bar,text=self.t('toggle_rule'),command=toggle).pack(side='left');ttk.Button(bar,text=self.t('delete_rule'),command=delete).pack(side='left',padx=6);ttk.Button(bar,text=self.t('done'),command=win.destroy).pack(side='right')
        win.protocol('WM_DELETE_WINDOW',win.destroy);win.bind('<Destroy>',lambda event:e.close() if event.widget is win else None);load()
    def preview_repair(self,rows,pending,answer,ready):
        win=tk.Toplevel(self.root); win.title('修復預覽 · 確認後才搬移'); win.geometry('940x560'); win.transient(self.root); win.grab_set()
        ttk.Label(win,text='可修復 %d 個音效；仍待判斷 %d 個。'%(len(rows),len(pending)),font=('Helvetica',16,'bold')).pack(padx=20,pady=16)
        ttk.Label(win,text='此操作會重新檢查已登記的舊音效，並套用新分類。手動調整過的分類也可能變更；下方列出每項目的地。',wraplength=870).pack(padx=20)
        box=ttk.Frame(win,padding=12); box.pack(fill='both',expand=True)
        tree=ttk.Treeview(box,columns=('old','new'),show='headings'); tree.heading('old',text='原路徑'); tree.heading('new',text='新路徑')
        tree.column('old',width=430); tree.column('new',width=430)
        scroll=ttk.Scrollbar(box,command=tree.yview); tree.configure(yscrollcommand=scroll.set); scroll.pack(side='right',fill='y'); tree.pack(fill='both',expand=True)
        for row in rows: tree.insert('','end',values=(row['src'],row['dst']))
        def finish(apply): answer['apply']=apply; ready.set(); win.destroy()
        buttons=ttk.Frame(win,padding=16); buttons.pack(fill='x')
        ttk.Button(buttons,text='取消，不變更',command=lambda:finish(False)).pack(side='left')
        ttk.Button(buttons,text='一次套用以上修復',command=lambda:finish(True)).pack(side='right')
        win.protocol('WM_DELETE_WINDOW',lambda:finish(False))
    def preview_quality(self,rows,answer,ready):
        win=tk.Toplevel(self.root); win.title('低音質副本清理預覽'); win.geometry('960x560'); win.transient(self.root); win.grab_set()
        ttk.Label(win,text='確認找到 %d 個低音質副本'%len(rows),font=('Helvetica',16,'bold')).pack(padx=20,pady=14)
        ttk.Label(win,text='只有同資料夾、基礎檔名相同、無損／有損配對，而且解碼後長度及波形都通過嚴格比對才列入。移除檔會放入隱藏隔離區，可由「還原最近一批」復原。',wraplength=900).pack(padx=20)
        box=ttk.Frame(win,padding=12); box.pack(fill='both',expand=True)
        tree=ttk.Treeview(box,columns=('keep','remove','proof'),show='headings'); tree.heading('keep',text='保留高音質'); tree.heading('remove',text='移至隔離區'); tree.heading('proof',text='檢測依據')
        tree.column('keep',width=320); tree.column('remove',width=320); tree.column('proof',width=270)
        scroll=ttk.Scrollbar(box,command=tree.yview); tree.configure(yscrollcommand=scroll.set); scroll.pack(side='right',fill='y'); tree.pack(fill='both',expand=True)
        for r in rows:tree.insert('','end',values=(r['keep'],r['remove'],r['reason']))
        def finish(apply):answer['apply']=apply; ready.set(); win.destroy()
        buttons=ttk.Frame(win,padding=16); buttons.pack(fill='x')
        ttk.Button(buttons,text='全部保留',command=lambda:finish(False)).pack(side='left')
        ttk.Button(buttons,text='將以上低音質副本移至隔離區',command=lambda:finish(True)).pack(side='right')
        win.protocol('WM_DELETE_WINDOW',lambda:finish(False))
    def pump(self):
        for _ in range(200):
            try: ev=self.events.get_nowait()
            except queue.Empty: break
            kind=ev[0]
            if kind=='scan': self.detail.set(self.t('scan_progress',count=ev[1]))
            elif kind=='stage': self.title.set(ev[1]); self.desc.set(ev[2]); self.bar.config(mode='indeterminate'); self.bar.start(15)
            elif kind=='progress':
                n,total,name=ev[1:]; self.bar.stop(); self.bar.config(mode='determinate',value=100*n/max(1,total))
                elapsed=time.monotonic()-self.started; eta=elapsed/max(1,n)*(total-n)
                self.detail.set(self.t('file_progress',done=n,total=total,percent=100*n/max(1,total),eta=eta,name=name[:50]))
            elif kind=='done':
                task,r=ev[1:]; self.pending=r['pending']; self.bar.stop(); self.bar.config(mode='determinate',value=100)
                self.title.set(self.t('completed') if task=='fast' else '舊版歸檔修復完成' if task=='repair' else '本次工作完成')
                msg=self.t('result_summary',moved=r['moved'],pending=len(self.pending),extras=len(r['extras']))
                total=r['moved']+len(self.pending)
                if task=='fast' and total:msg+='\n'+self.t('rate_summary',classified=100*r['moved']/total,review=100*len(self.pending)/total)
                if r.get('attachments_moved'):msg+='\n'+self.t('attachments_summary',count=r['attachments_moved'])
                if task=='quality':msg=('找到 %d 個通過嚴格比對的低音質副本；已移至隔離區 %d 個。'%(r.get('quality_found',0),r['moved']))
                if task=='purge':msg='已永久清除 %d 個隔離副本，釋放 %s。'%(r['moved'],self.human_bytes(r.get('purged_bytes',0)))
                if r.get('skipped'):msg+='\n'+self.t('skipped_summary',count=r['skipped'])
                self.desc.set(msg); self.tree.delete(*self.tree.get_children())
                for p in self.pending: self.tree.insert('', 'end',values=(p,'',0,self.t('needs_review')))
                for p,why in r.get('attachments',[]): self.tree.insert('', 'end',values=(p,'','',why))
                for p,why in r['extras']: self.tree.insert('', 'end',values=(p,'','',why))
                if r.get('system_skipped'):msg+='\n'+self.t('system_summary',count=r['system_skipped'])
                if r['extras']:
                    self.title.set(self.t('partial'));messagebox.showwarning(self.t('partial'),msg)
                else:messagebox.showinfo(self.t('success_title') if task=='fast' else self.t('done'),msg+('\n\n'+self.t('next_audio') if task in ('fast','repair') else ''))
            elif kind=='stopped': self.title.set(self.t('stopped_title')); self.desc.set(self.t('stopped_body'))
            elif kind=='error': self.title.set(self.t('safe_stop')); self.desc.set(ev[1]); messagebox.showerror(self.t('not_completed'),ev[1])
            elif kind=='notice': self.desc.set(ev[1])
            elif kind=='repair_preview': self.bar.stop(); self.preview_repair(*ev[1:])
            elif kind=='quality_preview': self.bar.stop(); self.preview_quality(*ev[1:])
            elif kind=='quality':
                n,total,name=ev[1:]; self.title.set('檢查高／低音質副本'); self.bar.stop(); self.bar.config(mode='determinate',value=100*n/max(1,total)); self.detail.set('%d / %d · %s'%(n,total,name[:60]))
            elif kind=='idle':
                self.busy=False; self.bar.stop()
                for w in [self.fast,self.quality,self.undo,self.choose,self.purge]: w.config(state='normal')
                self.combo.config(state='readonly');self.folder_style_combo.config(state='readonly'); self.ai.config(state='normal' if self.pending else 'disabled'); self.cancel.config(state='disabled'); self.pb.config(state='disabled')
        self.root.after(100,self.pump)

def release_self_test():
    """Non-destructive post-package launch check used by macOS CI."""
    from taxonomy import render_category
    checks={
        'python_frozen':bool(getattr(sys,'frozen',False)),
        'architecture':platform.machine(),
        'locale_en':I18n('en').t('app_title'),
        'locale_zh':I18n('zh-Hant').t('app_title'),
        'folder_en':str(render_category('Foley & Household/Footsteps','en')),
        'folder_bilingual':str(render_category('Foley & Household/Footsteps','bilingual')),
    }
    if not checks['locale_en'] or not checks['locale_zh']:raise RuntimeError('locale self-test failed')
    print(json.dumps(checks,ensure_ascii=False,sort_keys=True),flush=True)

if __name__=='__main__' and '--release-self-test' in sys.argv:
    release_self_test()
elif __name__=='__main__':
    try: os.nice(5)
    except OSError: pass
    root=tk.Tk(); App(root); root.mainloop()
