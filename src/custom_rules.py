"""Local-only, bounded user classification rules."""
import json, re, uuid
from datetime import datetime, timezone
from pathlib import Path
from categories import normal, result, RULE_VERSION

class CustomRules:
    def __init__(self,path):self.path=Path(path);self.rows=self._load()
    def _load(self):
        try:
            data=json.loads(self.path.read_text('utf-8'))
            return [r for r in data.get('rules',[]) if isinstance(r,dict)]
        except (OSError,ValueError):return []
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps({'version':1,'rules':self.rows},ensure_ascii=False,indent=2),'utf-8');tmp.replace(self.path)
    def add(self,pattern,category,label=None,scope='filename',tags=None):
        pattern=normal(pattern)
        if len(pattern)<2:raise ValueError('自訂規則至少需要兩個有效字元')
        row={'id':uuid.uuid4().hex,'enabled':True,'pattern':pattern,'scope':scope,'category':category,
             'label':label or re.sub(r'[^A-Za-z0-9]+','_',category.split('/')[-1]).strip('_'),
             'tags':tags or [],'created_at':datetime.now(timezone.utc).isoformat()}
        self.rows.append(row);self.save();return row
    def classify(self,path):
        path=Path(path);filename=normal(path.stem);whole=normal(' '.join(path.parts))
        for row in reversed(self.rows):
            if not row.get('enabled',True):continue
            hay=filename if row.get('scope')=='filename' else whole
            pattern=row.get('pattern','')
            if pattern and re.search(r'(?<![a-z])'+re.escape(pattern)+r'(?![a-z])',hay,re.I):
                return result(row['category'],'使用者自訂規則',row.get('label','Sound_Effect'),row.get('tags',[]),pattern,.99,'custom_rule')
        return None
    def export_to(self,path):Path(path).write_text(json.dumps({'version':1,'rules':self.rows},ensure_ascii=False,indent=2),'utf-8')
    def import_from(self,path):
        data=json.loads(Path(path).read_text('utf-8'));incoming=data.get('rules',[])
        known={r.get('id') for r in self.rows};self.rows.extend(r for r in incoming if isinstance(r,dict) and r.get('id') not in known);self.save()
    def toggle(self,rule_id):
        for row in self.rows:
            if row.get('id')==rule_id:row['enabled']=not row.get('enabled',True);self.save();return
    def delete(self,rule_id):self.rows=[r for r in self.rows if r.get('id')!=rule_id];self.save()
