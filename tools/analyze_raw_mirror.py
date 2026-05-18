from __future__ import annotations
import argparse, csv, io, json, re, sqlite3, sys, time, xml.etree.ElementTree as ET, zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator
from metabolic_safety_etl.raw_sources import (
    extract_chembl_sqlite_archives, extract_cyp_relations, extract_half_life_hours,
    first_attr, first_text, iter_openfda_results, list_values, slugify, spl_sections,
    stable_hash, clean_label_title
)

OPENFDA_FIELD_MAP={
 'effect':('indications_and_usage','purpose','mechanism_of_action','pharmacodynamics'),
 'pk':('pharmacokinetics','clinical_pharmacology'),
 'interaction':('drug_interactions','drug_and_or_laboratory_test_interactions'),
 'dosage':('dosage_and_administration','dosage_forms_and_strengths'),
 'overdose':('overdosage',),
 'warning':('boxed_warning','warnings','warnings_and_precautions','contraindications'),
}
SECTION_HINTS={
 'effect':('INDICATIONS AND USAGE','PURPOSE','MECHANISM OF ACTION','PHARMACODYNAMICS'),
 'pk':('PHARMACOKINETICS','CLINICAL PHARMACOLOGY'),
 'interaction':('DRUG INTERACTIONS','DRUG AND OR LABORATORY TEST INTERACTIONS'),
 'dosage':('DOSAGE AND ADMINISTRATION','DOSAGE FORMS AND STRENGTHS'),
 'overdose':('OVERDOSAGE',),
 'warning':('BOXED WARNING','WARNINGS','WARNINGS AND PRECAUTIONS','CONTRAINDICATIONS'),
}
DOSE_RE=re.compile(r"(?P<value>\d+(?:\.\d+)?)(?:\s*(?:-|to|through|至|–|—)\s*(?P<value2>\d+(?:\.\d+)?))?\s*(?P<unit>mg/kg/day|mg/kg/dose|mcg/kg/min|mcg/kg/day|mcg/kg|ug/kg|µg/kg|mg|mcg|ug|µg|g|grams?|mL|ml|units?|IU|%)\b",re.I)
csv.field_size_limit(min(sys.maxsize, 2_147_483_647))
RISK_WORDS=re.compile(r"\b(avoid|contraindicated|contraindication|fatal|death|life-threatening|serotonin syndrome|respiratory depression|qt prolong|torsades|major|severe|not recommended)\b",re.I)

def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def squash(s:str)->str: return re.sub(r'\s+',' ',str(s or '')).strip()
def excerpt(s:str,n:int=1200)->str: return squash(s)[:n]
def vals(v:Any)->list[str]: return [str(x).strip() for x in v if str(x).strip()] if isinstance(v,list) else ([v.strip()] if isinstance(v,str) and v.strip() else [])
def split_terms(v:str)->list[str]: return [p.strip().strip('"') for p in re.split(r'[|;,]\s*',str(v or '')) if p.strip()][:50]
def joined(result:dict[str,Any], fields:Iterable[str])->str:
    out=[]
    for f in fields: out.extend(vals(result.get(f)))
    return '\n'.join(out)
def classify(title:str)->str|None:
    u=title.upper()
    for k,hints in SECTION_HINTS.items():
        if any(h in u for h in hints): return k
    return None

class Writer:
    def __init__(self,out:Path):
        self.out=out; self.out.mkdir(parents=True,exist_ok=True); (self.out/'jsonl').mkdir(exist_ok=True)
        self.db=self.out/'structured_facts.sqlite'; self.conn=sqlite3.connect(self.db)
        self.conn.execute('PRAGMA journal_mode=WAL'); self.conn.execute('PRAGMA synchronous=NORMAL')
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS facts(
          fact_id TEXT PRIMARY KEY, source_key TEXT, fact_type TEXT, subject_id TEXT,
          subject_ids_json TEXT, name TEXT, section TEXT, claim_json TEXT, risk_level TEXT,
          confidence TEXT, source_tier TEXT, source_name TEXT, source_url TEXT,
          evidence_quote TEXT, extraction_method TEXT, review_status TEXT, use_policy TEXT, updated_at TEXT);
        CREATE INDEX IF NOT EXISTS idx_facts_source ON facts(source_key);
        CREATE INDEX IF NOT EXISTS idx_facts_type ON facts(fact_type);
        CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject_id);
        CREATE TABLE IF NOT EXISTS run_summary(source_key TEXT PRIMARY KEY,status TEXT,records_seen INTEGER,facts_written INTEGER,seconds REAL,note TEXT,updated_at TEXT);
        ''')
        self.handles={}; self.counts=Counter(); self.by_source=Counter(); self.batch=0
    def emit(self,source_key,fact_type,subject_ids,claim,*,name=None,section=None,risk_level='Unknown',confidence='Unknown',source_tier='Signal',source_name='',source_url='',evidence_quote='',extraction_method='raw_analysis',review_status='unreviewed',use_policy='candidate_signal',basis=''):
        ids=[slugify(str(x)) for x in subject_ids if str(x).strip()] or ['unknown']
        basis=basis or json.dumps([source_key,fact_type,ids,claim,section],ensure_ascii=False,sort_keys=True)
        fid=f'{source_key}_{fact_type}_{stable_hash(basis,20)}'
        row=(fid,source_key,fact_type,ids[0],json.dumps(ids,ensure_ascii=False),name or claim.get('name_en') or claim.get('name') or ids[0],section,json.dumps(claim,ensure_ascii=False,sort_keys=True),risk_level,confidence,source_tier,source_name,source_url,excerpt(evidence_quote,1800),extraction_method,review_status,use_policy,now())
        cur=self.conn.execute('INSERT OR IGNORE INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',row)
        if cur.rowcount:
            h=self.handles.get(source_key)
            if h is None:
                h=(self.out/'jsonl'/f'{source_key}.jsonl').open('a',encoding='utf-8'); self.handles[source_key]=h
            h.write(json.dumps({'fact_id':fid,'source_key':source_key,'fact_type':fact_type,'subject_ids':ids,'name':row[5],'section':section,'claim':claim,'risk_level':risk_level,'confidence':confidence,'source_tier':source_tier,'source_name':source_name,'source_url':source_url,'evidence_quote':row[13],'extraction_method':extraction_method,'review_status':review_status,'use_policy':use_policy,'updated_at':row[17]},ensure_ascii=False,sort_keys=True)+'\n')
            self.counts[fact_type]+=1; self.by_source[source_key]+=1; self.batch+=1
            if self.batch>=2000: self.commit()
    def commit(self):
        self.conn.commit(); [h.flush() for h in self.handles.values()]; self.batch=0
    def summary(self,source,status,records,seconds,note=''):
        self.conn.execute('INSERT OR REPLACE INTO run_summary VALUES (?,?,?,?,?,?,?)',(source,status,records,self.by_source[source],seconds,note,now())); self.commit()
        print(f'summary source={source} status={status} records={records} facts={self.by_source[source]} seconds={seconds:.1f} {note}',flush=True)
    def close(self):
        self.commit(); [h.close() for h in self.handles.values()]
        (self.out/'summary.json').write_text(json.dumps({'db_path':str(self.db),'facts_by_type':dict(self.counts),'facts_by_source':dict(self.by_source),'updated_at':now()},ensure_ascii=False,indent=2,sort_keys=True),encoding='utf-8')
        self.conn.close()

def emit_text(w:Writer,source,subject,name,section,text,source_name,source_url,tier,method):
    text=squash(text)
    if not text: return
    w.emit(source,'label_section',[subject],{'section':section,'text_excerpt':excerpt(text,3000)},name=name,section=section,confidence='Medium',source_tier=tier,source_name=source_name,source_url=source_url,evidence_quote=text,extraction_method=method,use_policy='evidence_source')
    if section=='effect':
        w.emit(source,'drug_effect',[subject],{'effect_text':excerpt(text,2500)},name=name,section=section,confidence='Medium',source_tier=tier,source_name=source_name,source_url=source_url,evidence_quote=text,extraction_method=method)
    if section=='interaction':
        w.emit(source,'interaction_signal',[subject],{'interaction_text':excerpt(text,3000)},name=name,section=section,risk_level='Major' if RISK_WORDS.search(text) else 'Unknown',confidence='Medium',source_tier=tier,source_name=source_name,source_url=source_url,evidence_quote=text,extraction_method=method)
    if section=='overdose':
        w.emit(source,'overdose_warning',[subject],{'overdose_text':excerpt(text,2500)},name=name,section=section,risk_level='Major',confidence='Medium',source_tier=tier,source_name=source_name,source_url=source_url,evidence_quote=text,extraction_method=method)
    if section=='warning':
        w.emit(source,'safety_warning',[subject],{'warning_text':excerpt(text,2500)},name=name,section=section,risk_level='Major' if RISK_WORDS.search(text) else 'Moderate',confidence='Medium',source_tier=tier,source_name=source_name,source_url=source_url,evidence_quote=text,extraction_method=method)
    if section in {'pk','effect'}:
        hl=extract_half_life_hours(text)
        if hl is not None:
            w.emit(source,'pharmacokinetics',[subject],{'half_life_hours':hl},name=name,section=section,confidence='Medium',source_tier=tier,source_name=source_name,source_url=source_url,evidence_quote=text,extraction_method=method)
        for enzyme,rel,snip in extract_cyp_relations(text)[:20]:
            w.emit(source,'enzyme_relation',[subject],{'tag':f'{enzyme}_{rel}','enzyme':enzyme,'relation':rel},name=name,section=section,confidence='Low' if rel=='mentioned' else 'Medium',source_tier=tier,source_name=source_name,source_url=source_url,evidence_quote=snip,extraction_method=method)
    if section=='dosage':
        seen=set()
        for m in DOSE_RE.finditer(text):
            ctx=text[max(0,m.start()-140):min(len(text),m.end()+140)]
            key=(m.group('value'),m.group('value2') or '',m.group('unit').lower())
            if key in seen: continue
            seen.add(key)
            w.emit(source,'dose_candidate',[subject],{'value':float(m.group('value')),'value_max':float(m.group('value2')) if m.group('value2') else None,'unit':m.group('unit'),'context':excerpt(ctx,420)},name=name,section=section,confidence='Low',source_tier=tier,source_name=source_name,source_url=source_url,evidence_quote=ctx,extraction_method=method)
            if len(seen)>=40: break

def analyze_openfda(raw,w,max_records=0):
    source='openfda_label'; start=time.time(); seen=0
    for path in sorted((raw/source).glob('*')):
        if not zipfile.is_zipfile(path): continue
        print(f'openfda file={path.name}',flush=True)
        for result in iter_openfda_results(path):
            of=result.get('openfda') if isinstance(result.get('openfda'),dict) else {}
            names=list_values(of.get('generic_name')) or list_values(of.get('substance_name')) or list_values(of.get('brand_name'))
            name=names[0] if names else str(result.get('set_id') or result.get('id') or 'unknown_label')
            sid=slugify(name); aliases=sorted(set(list_values(of.get('brand_name'))+list_values(of.get('substance_name'))+names),key=str.lower)[:60]
            url='https://open.fda.gov/apis/drug/label/'
            w.emit(source,'substance_identity',[sid],{'name_en':name,'category':'DrugLabel','identifiers':{'aliases':aliases,'rxcui':list_values(of.get('rxcui'))[:20],'unii':list_values(of.get('unii'))[:20],'spl_id':list_values(of.get('spl_id'))[:20],'set_id':result.get('set_id')}},name=name,confidence='High',source_tier='Regulatory',source_name='openFDA drug label bulk',source_url=url,evidence_quote='openFDA label metadata',extraction_method='bulk_json',review_status='machine_checked',use_policy='evidence_source')
            for section,fields in OPENFDA_FIELD_MAP.items(): emit_text(w,source,sid,name,section,joined(result,fields),'openFDA drug label bulk',url,'Regulatory','bulk_json')
            seen+=1
            if seen%10000==0: print(f'openfda progress records={seen} facts={w.by_source[source]}',flush=True)
            if max_records and seen>=max_records: w.summary(source,'partial',seen,time.time()-start,f'max_records={max_records}'); return
    w.summary(source,'done',seen,time.time()-start)

def iter_dailymed_xml(outer_path:Path):
    with zipfile.ZipFile(outer_path) as outer:
        for member in outer.namelist():
            lower=member.lower()
            if lower.endswith('.xml'):
                yield outer.read(member)
            elif lower.endswith('.zip'):
                try:
                    with zipfile.ZipFile(io.BytesIO(outer.read(member))) as inner:
                        for inner_name in inner.namelist():
                            if inner_name.lower().endswith('.xml'): yield inner.read(inner_name)
                except Exception: continue

def analyze_dailymed(raw,w,max_records=0):
    source='dailymed'; start=time.time(); seen=0
    for path in sorted((raw/'dailymed_spl').glob('*.zip')):
        print(f'dailymed file={path.name}',flush=True)
        for xb in iter_dailymed_xml(path):
            try: root=ET.fromstring(xb)
            except Exception: continue
            title=clean_label_title(first_text(root,'title') or 'DailyMed SPL'); sid=slugify(title); setid=first_attr(root,'setId','root') or ''
            url=f'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}' if setid else 'https://dailymed.nlm.nih.gov/'
            w.emit(source,'substance_identity',[sid],{'name_en':title,'category':'DrugLabel','identifiers':{'dailymed_setid':setid}},name=title,confidence='High',source_tier='Regulatory',source_name='DailyMed SPL bulk',source_url=url,evidence_quote='DailyMed SPL metadata',extraction_method='bulk_spl_xml',review_status='machine_checked',use_policy='evidence_source')
            buckets={k:[] for k in SECTION_HINTS}
            for st,text in spl_sections(root):
                k=classify(st)
                if k: buckets[k].append(st+'\n'+text)
            for k,parts in buckets.items():
                if parts: emit_text(w,source,sid,title,k,'\n'.join(parts),'DailyMed SPL bulk',url,'Regulatory','bulk_spl_xml')
            seen+=1
            if seen%1000==0: print(f'dailymed progress labels={seen} facts={w.by_source[source]}',flush=True)
            if max_records and seen>=max_records: w.summary(source,'partial',seen,time.time()-start,f'max_records={max_records}'); return
    w.summary(source,'done',seen,time.time()-start)

def analyze_chembl(raw,w,max_records=0):
    source='chembl'; start=time.time(); source_dir=raw/'chembl'; seen=0
    dbs=list(source_dir.glob('**/*.db'))+list(source_dir.glob('**/*.sqlite'))+list(source_dir.glob('**/*.sqlite3'))
    if not dbs:
        print('chembl extracting sqlite archive',flush=True); dbs=extract_chembl_sqlite_archives(source_dir)
    for db in dbs:
        print(f'chembl db={db}',flush=True)
        with sqlite3.connect(db) as conn:
            conn.row_factory=sqlite3.Row
            rows=conn.execute('''SELECT md.chembl_id,md.pref_name,md.molecule_type,md.max_phase,md.therapeutic_flag,cp.alogp,cp.psa,cp.full_mwt,cp.hba,cp.hbd FROM molecule_dictionary md LEFT JOIN compound_properties cp ON cp.molregno=md.molregno WHERE md.pref_name IS NOT NULL ORDER BY md.pref_name''')
            for r in rows:
                name=r['pref_name']; sid=slugify(name); sol=None
                try:
                    alogp=float(r['alogp']) if r['alogp'] is not None else None; sol='Lipophilic' if alogp is not None and alogp>=2 else ('Hydrophilic' if alogp is not None else None)
                except Exception: pass
                w.emit(source,'substance_identity',[sid],{'name_en':name,'category':r['molecule_type'] or 'ChEMBL molecule','solubility':sol,'identifiers':{'chembl_id':r['chembl_id'],'alogp':r['alogp'],'psa':r['psa'],'full_mwt':r['full_mwt'],'hba':r['hba'],'hbd':r['hbd'],'max_phase':r['max_phase'],'therapeutic_flag':r['therapeutic_flag']}},name=name,confidence='High',source_tier='CuratedDB',source_name='ChEMBL bulk',source_url='https://www.ebi.ac.uk/chembl/',evidence_quote='ChEMBL molecule row',extraction_method='bulk_sqlite',review_status='machine_checked',use_policy='evidence_source')
                seen+=1
                if seen%25000==0: print(f'chembl progress molecules={seen} facts={w.by_source[source]}',flush=True)
                if max_records and seen>=max_records: w.summary(source,'partial',seen,time.time()-start,f'max_records={max_records}'); return
            try:
                for r in conn.execute('''SELECT md.pref_name drug_name,dm.mechanism_of_action,dm.action_type,td.pref_name target_name FROM drug_mechanism dm JOIN molecule_dictionary md ON md.molregno=dm.molregno LEFT JOIN target_dictionary td ON td.tid=dm.tid WHERE md.pref_name IS NOT NULL'''):
                    drug=r['drug_name']
                    w.emit(source,'drug_effect',[slugify(drug)],{'mechanism_of_action':r['mechanism_of_action'],'action_type':r['action_type'],'target':r['target_name']},name=drug,section='mechanism',confidence='High',source_tier='CuratedDB',source_name='ChEMBL drug mechanism',source_url='https://www.ebi.ac.uk/chembl/',evidence_quote=r['mechanism_of_action'] or r['target_name'] or 'ChEMBL mechanism',extraction_method='bulk_sqlite',use_policy='evidence_source')
            except Exception as exc: print(f'chembl mechanism skipped {type(exc).__name__}: {exc}',flush=True)
    w.summary(source,'done',seen,time.time()-start)

def zip_rows(path:Path):
    with zipfile.ZipFile(path) as z:
        for m in z.namelist():
            if not m.lower().endswith(('.tsv','.csv')): continue
            with z.open(m) as h:
                reader=csv.DictReader(io.TextIOWrapper(h,encoding='utf-8-sig',errors='replace'),delimiter='\t' if m.lower().endswith('.tsv') else ',')
                for row in reader: yield m,{str(k or '').strip():str(v or '').strip() for k,v in row.items()}

def analyze_pharmgkb(raw,w,max_records=0):
    source='pharmgkb'; start=time.time(); seen=0; source_dir=raw/'pharmgkb'
    for path in sorted(source_dir.glob('*.zip')):
        print(f'pharmgkb file={path.name}',flush=True)
        if path.name=='guidelineAnnotations.json.zip':
            with zipfile.ZipFile(path) as z:
                for m in z.namelist():
                    if not m.lower().endswith('.json'): continue
                    try: obj=json.loads(z.read(m).decode('utf-8')); g=obj.get('guideline') or {}
                    except Exception: continue
                    name=g.get('name') or m; chems=g.get('relatedChemicals') or [{'name':name}]; genes=g.get('relatedGenes') or []
                    summary=((g.get('summaryMarkdown') or {}).get('html') or ''); text=((g.get('textMarkdown') or {}).get('html') or '')
                    for c in chems:
                        drug=c.get('name') or name
                        w.emit(source,'pgx_guideline',[slugify(drug)],{'guideline_id':g.get('id'),'name':name,'source':g.get('source'),'genes':[x.get('symbol') or x.get('name') for x in genes],'dosing_information':g.get('dosingInformation'),'testing_info':g.get('hasTestingInfo'),'summary':excerpt(summary,1800)},name=drug,section='guideline',confidence='High',source_tier='Guideline',source_name='PharmGKB / ClinPGx guideline',source_url='https://api.pharmgkb.org/',evidence_quote=summary or text,extraction_method='bulk_json',review_status='machine_checked',use_policy='evidence_source')
                        seen+=1
            continue
        for member,row in zip_rows(path):
            lname=member.lower()
            if lname in {'drugs.tsv','chemicals.tsv'}:
                drug=row.get('Name') or ''
                if drug: w.emit(source,'substance_identity',[slugify(drug)],{'name_en':drug,'category':row.get('Type') or 'PharmGKB chemical','identifiers':{'pharmgkb_id':row.get('PharmGKB Accession Id'),'aliases':split_terms(row.get('Generic Names','')+';'+row.get('Trade Names','')),'rxnorm':split_terms(row.get('RxNorm Identifiers','')),'atc':split_terms(row.get('ATC Identifiers','')),'pubchem':split_terms(row.get('PubChem Compound Identifiers','')),'dosing_guideline':row.get('Dosing Guideline'),'top_cpic_level':row.get('Top CPIC Pairs Level')}},name=drug,confidence='High',source_tier='Guideline',source_name='PharmGKB / ClinPGx bulk',source_url='https://api.pharmgkb.org/',evidence_quote='PharmGKB drug/chemical row',extraction_method='bulk_tsv',review_status='machine_checked',use_policy='evidence_source')
            elif lname=='clinical_annotations.tsv':
                for drug in split_terms(row.get('Drug(s)','')):
                    w.emit(source,'pgx_clinical_annotation',[slugify(drug)],{'clinical_annotation_id':row.get('Clinical Annotation ID'),'gene':row.get('Gene'),'variant_haplotypes':row.get('Variant/Haplotypes'),'level_of_evidence':row.get('Level of Evidence'),'phenotype_category':row.get('Phenotype Category'),'phenotypes':split_terms(row.get('Phenotype(s)','')),'score':row.get('Score'),'pmid_count':row.get('PMID Count'),'url':row.get('URL')},name=drug,section='clinical_annotation',confidence='High',source_tier='Guideline',source_name='PharmGKB / ClinPGx clinical annotation',source_url=row.get('URL') or 'https://api.pharmgkb.org/',evidence_quote=json.dumps(row,ensure_ascii=False)[:1200],extraction_method='bulk_tsv',use_policy='evidence_source')
            elif lname=='druglabels.tsv':
                for drug in split_terms(row.get('Chemicals','')):
                    w.emit(source,'pgx_drug_label',[slugify(drug)],{'label_id':row.get('PharmGKB ID'),'name':row.get('Name'),'source':row.get('Source'),'testing_level':row.get('Testing Level'),'has_prescribing_info':row.get('Has Prescribing Info'),'has_dosing_info':row.get('Has Dosing Info'),'has_alternate_drug':row.get('Has Alternate Drug'),'genes':split_terms(row.get('Genes','')),'variants':split_terms(row.get('Variants/Haplotypes',''))},name=drug,section='drug_label',confidence='High',source_tier='Guideline',source_name='PharmGKB / ClinPGx drug label',source_url='https://api.pharmgkb.org/',evidence_quote=json.dumps(row,ensure_ascii=False)[:1200],extraction_method='bulk_tsv',use_policy='evidence_source')
            elif lname=='relationships.tsv':
                e1n,e1t,e2n,e2t=row.get('Entity1_name'),row.get('Entity1_type'),row.get('Entity2_name'),row.get('Entity2_type')
                if e1n and e2n and (e1t=='Chemical' or e2t=='Chemical'):
                    drug=e1n if e1t=='Chemical' else e2n; other=e2n if e1t=='Chemical' else e1n; ot=e2t if e1t=='Chemical' else e1t
                    w.emit(source,'pgx_relationship',[slugify(drug)],{'related_entity':other,'related_entity_type':ot,'association':row.get('Association'),'evidence':row.get('Evidence'),'pk':row.get('PK'),'pd':row.get('PD'),'pmids':split_terms(row.get('PMIDs',''))},name=drug,section='relationship',confidence='Medium',source_tier='Guideline',source_name='PharmGKB / ClinPGx relationship',source_url='https://api.pharmgkb.org/',evidence_quote=json.dumps(row,ensure_ascii=False)[:1200],extraction_method='bulk_tsv')
            seen+=1
            if seen%10000==0: print(f'pharmgkb progress rows={seen} facts={w.by_source[source]}',flush=True)
            if max_records and seen>=max_records: w.summary(source,'partial',seen,time.time()-start,f'max_records={max_records}'); return
    w.summary(source,'done',seen,time.time()-start)

def analyze_onsides(raw,w,max_records=0):
    source='onsides'; start=time.time(); seen=0
    for path in sorted((raw/'onsides').glob('*.zip')):
        print(f'onsides file={path.name}',flush=True)
        with zipfile.ZipFile(path) as z:
            labels={}; effects={}
            with z.open('csv/product_label.csv') as h:
                for row in csv.DictReader(io.TextIOWrapper(h,encoding='utf-8-sig',errors='replace')): labels[row.get('label_id','')]=row.get('source_product_name','')
            with z.open('csv/vocab_meddra_adverse_effect.csv') as h:
                for row in csv.DictReader(io.TextIOWrapper(h,encoding='utf-8-sig',errors='replace')): effects[row.get('meddra_id','')]=row.get('meddra_name','')
            with z.open('csv/product_adverse_effect.csv') as h:
                for row in csv.DictReader(io.TextIOWrapper(h,encoding='utf-8-sig',errors='replace')):
                    product=labels.get(row.get('product_label_id',''),''); event=effects.get(row.get('effect_meddra_id',''),'')
                    if not product or not event: continue
                    w.emit(source,'adverse_event',[slugify(product)],{'event':event,'meddra_id':row.get('effect_meddra_id'),'label_section':row.get('label_section'),'match_method':row.get('match_method'),'pred0':row.get('pred0'),'pred1':row.get('pred1')},name=product,section='adverse_event',confidence='Low',source_tier='Signal',source_name='OnSIDES bulk',source_url='https://github.com/tatonetti-lab/onsides',evidence_quote=event,extraction_method='bulk_csv')
                    seen+=1
                    if seen%50000==0: print(f'onsides progress events={seen} facts={w.by_source[source]}',flush=True)
                    if max_records and seen>=max_records: w.summary(source,'partial',seen,time.time()-start,f'max_records={max_records}'); return
    w.summary(source,'done',seen,time.time()-start)

def parse_sql_scalar(v):
    t=v.strip()
    if t.upper()=='NULL': return None
    if re.fullmatch(r'-?\d+',t): return int(t)
    if re.fullmatch(r'-?\d+\.\d+',t): return float(t)
    return t

def iter_sql_tuples(line):
    i=0; n=len(line)
    while i<n:
        if line[i]!='(': i+=1; continue
        i+=1; row=[]; val=[]; ins=False; esc=False
        while i<n:
            ch=line[i]; i+=1
            if ins:
                if esc: val.append(ch); esc=False
                elif ch=='\\': esc=True
                elif ch=="'": ins=False
                else: val.append(ch)
            else:
                if ch=="'": ins=True
                elif ch==',': row.append(parse_sql_scalar(''.join(val))); val=[]
                elif ch==')': row.append(parse_sql_scalar(''.join(val))); yield row; break
                else: val.append(ch)

def analyze_foodrugs(raw,w,max_records=0):
    source='foodrugs'; start=time.time(); seen=0
    for path in sorted((raw/'foodrugs').glob('*.sql')):
        print(f'foodrugs file={path.name}',flush=True)
        with path.open('r',encoding='utf-8',errors='replace') as h:
            for line in h:
                if not line.startswith('INSERT INTO `TM_interactions` VALUES'): continue
                for row in iter_sql_tuples(line):
                    if len(row)<6: continue
                    food=str(row[4] or '').strip(); drug=str(row[5] or '').strip()
                    if not food or not drug: continue
                    w.emit(source,'food_interaction',[slugify(drug),slugify(food)],{'drug':drug,'food_or_bioactive':food,'text_id':row[1],'start_index':row[2],'end_index':row[3],'note':f'FooDrugs text-mined food-drug interaction candidate: {food} / {drug}'},name=drug,section='food_interaction',risk_level='Unknown',confidence='Low',source_tier='Signal',source_name='FooDrugs bulk',source_url='https://zenodo.org/records/8192515',evidence_quote=f'{food} / {drug}',extraction_method='mysql_dump_tm_interactions')
                    seen+=1
                    if seen%50000==0: print(f'foodrugs progress pairs={seen} facts={w.by_source[source]}',flush=True)
                    if max_records and seen>=max_records: w.summary(source,'partial',seen,time.time()-start,f'max_records={max_records}'); return
    w.summary(source,'done',seen,time.time()-start)

def main():
    ap=argparse.ArgumentParser(description='Analyze mirrored raw pharmacology sources into structured facts')
    ap.add_argument('--raw-dir',default='D:/metabolic-safety-data/raw')
    ap.add_argument('--out-dir',default='D:/metabolic-safety-data/structured')
    ap.add_argument('--sources',default='openfda_label,dailymed,chembl,foodrugs,onsides,pharmgkb')
    ap.add_argument('--max-records-per-source',type=int,default=0)
    args=ap.parse_args(); raw=Path(args.raw_dir); w=Writer(Path(args.out_dir))
    analyzers={'openfda_label':analyze_openfda,'dailymed':analyze_dailymed,'chembl':analyze_chembl,'foodrugs':analyze_foodrugs,'onsides':analyze_onsides,'pharmgkb':analyze_pharmgkb}
    try:
        for s in [x.strip() for x in args.sources.split(',') if x.strip()]:
            if s not in analyzers: print(f'unsupported source={s}',flush=True); continue
            try: analyzers[s](raw,w,args.max_records_per_source)
            except Exception as exc:
                w.summary(s,'error',0,0.0,f'{type(exc).__name__}: {exc}'); print(f'error source={s} {type(exc).__name__}: {exc}',flush=True)
    finally: w.close()
    print(f'structured_db={Path(args.out_dir)/"structured_facts.sqlite"}',flush=True)
    print(f'summary={Path(args.out_dir)/"summary.json"}',flush=True)

if __name__=='__main__': raise SystemExit(main())
