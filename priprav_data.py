# připrav_data.py
# Systémové vytvoření rodokmen_data.json z ODS + GEDCOM.
# Přesná shoda s oficiálním GEDCOM jménem má přednost před
# shodou vzniklou pouze z vdaného příjmení.

import json,re,unicodedata
from collections import defaultdict
from pathlib import Path
import pandas as pd

BASE=Path(__file__).parent
ODS=BASE/'rodokmen.ods'
GED=BASE/'rodokmen.ged'
OUT=BASE/'rodokmen_data.json'

def norm(s):
    s=s or ''
    s=re.sub(r'/','',str(s))
    s=unicodedata.normalize('NFKD',s)
    s=''.join(c for c in s if not unicodedata.combining(c))
    s=s.replace(',',' ')
    return re.sub(r'\s+',' ',s).strip().lower()

def parse_ged(path):
    lines=path.read_text(encoding='utf-8-sig').splitlines()
    people={}; families={}; cur=None; event=None
    for line in lines:
        parts=line.split(' ',2); level=int(parts[0]); tag=parts[1] if len(parts)>1 else ''; val=parts[2].strip() if len(parts)>2 else ''
        if level==0:
            cur=None; event=None
            if len(parts)>2 and val=='INDI': cur=parts[1]; people[cur]={"id":cur,"name":"","given":"","surname":"","sex":"","birth":"","birth_place":"","death":"","death_place":"","occupation":"","families_as_spouse":[],"family_as_child":None,"married_names":[]}
            elif len(parts)>2 and val=='FAM': cur=parts[1]; families[cur]={"id":cur,"husband":None,"wife":None,"children":[]}
            continue
        if cur is None: continue
        if cur in people:
            p=people[cur]
            if level==1:
                event=None
                if tag=='NAME': p['name']=val
                elif tag=='SEX': p['sex']=val
                elif tag=='FAMS': p['families_as_spouse'].append(val)
                elif tag=='FAMC': p['family_as_child']=val
                elif tag=='BIRT': event='birth'
                elif tag=='DEAT': event='death'
                elif tag=='OCCU': p['occupation']=val
            elif level==2:
                if tag=='GIVN': p['given']=val
                elif tag=='SURN': p['surname']=val
                elif tag=='_MARNM': p['married_names'].extend([x.strip() for x in val.split(',') if x.strip()])
                elif tag=='DATE' and event: p[event]=val
                elif tag=='PLAC' and event: p[event+'_place']=val
        elif cur in families:
            f=families[cur]
            if level==1:
                if tag=='HUSB': f['husband']=val
                elif tag=='WIFE': f['wife']=val
                elif tag=='CHIL': f['children'].append(val)
    return people,families

people,families=parse_ged(GED)
# Indexes are intentionally separated:
# official GEDCOM name has priority over a married-name variant.
exact_idx=defaultdict(list)
married_idx=defaultdict(list)
for pid,p in people.items():
    for v in [p["name"], (p["given"]+" "+p["surname"]).strip()]:
        if v: exact_idx[norm(v)].append(pid)
    for ms in p["married_names"]:
        v=(p["given"]+" "+ms).strip()
        if v: married_idx[norm(v)].append(pid)

# ODS populated cells, preserving duplicates as distinct nodes
sheet=pd.read_excel(ODS,engine='odf',header=None)
nodes=[]; cell_to_id={}
for r,row in sheet.iterrows():
    for c,v in enumerate(row):
        if pd.isna(v): continue
        s=str(v).strip()
        if not s or r in (0,1) or s.lower()=='kontakt přes facebook': continue
        nid=f'o{r}_{c}'
        nodes.append({'id':nid,'name':re.sub(r'\s+',' ',s),'row':int(r),'col':int(c)})
        cell_to_id[(int(r),int(c))]=nid

# Match GED records.
# Exact official GEDCOM name always wins over a married-name-only match.
for n in nodes:
    key=norm(n['name'])
    exact=list(dict.fromkeys(exact_idx.get(key,[])))
    married=list(dict.fromkeys(married_idx.get(key,[])))
    if len(exact)==1:
        cands=exact
        n['match_type']='exact'
    elif len(exact)>1:
        cands=exact
        n['match_type']='ambiguous'
    elif len(married)==1:
        cands=married
        n['match_type']='married'
    elif len(married)>1:
        cands=married
        n['match_type']='ambiguous'
    else:
        cands=[]
        n['match_type']='unmatched'
    n['ged_ids']=cands
    n['ged_id']=cands[0] if len(cands)==1 else None
    if n['ged_id']:
        p=people[n['ged_id']]
        n['info']={k:p[k] for k in ['name','given','surname','sex','birth','birth_place','death','death_place','occupation','married_names']}
    else:
        n['info']={}

node_by_id={n['id']:n for n in nodes}
ged_to_ods={}
for n in nodes:
    if n['ged_id']:
        ged_to_ods[n['ged_id']]=n['id']

edges=[]
# True family relationships from GEDCOM where both persons are matched.
for fid,f in families.items():
    h=ged_to_ods.get(f['husband']); w=ged_to_ods.get(f['wife'])
    if h and w:
        edges.append({'id':f's{fid}','source':h,'target':w,'type':'spouse','source_data':'GEDCOM'})
    for ch in f['children']:
        co=ged_to_ods.get(ch)
        if not co: continue
        for parent in (h,w):
            if parent:
                edges.append({'id':f'p{fid}_{ch}_{parent}','source':parent,'target':co,'type':'parent','source_data':'GEDCOM'})

# ODS hierarchy fallback: nearest previous person one indentation level up.
# Used only when there is no GED parent edge between the same two nodes.
ged_pairs={(e['source'],e['target']) for e in edges if e['type']=='parent'}
stack={}
for n in nodes:
    c=n['col']
    # discard deeper levels when moving back up
    for k in list(stack):
        if k>=c: del stack[k]
    if c>0 and (c-1) in stack:
        parent=stack[c-1]
        pair=(parent,n['id'])
        if pair not in ged_pairs:
            edges.append({'id':f'o{n["id"]}','source':parent,'target':n['id'],'type':'parent_ods','source_data':'ODS hierarchy'})
    stack[c]=n['id']

# remove duplicate edges
seen=set(); ded=[]
for e in edges:
    key=(e['source'],e['target'],e['type'])
    if key not in seen: seen.add(key); ded.append(e)

# metadata
stats={
    'ods_person_cells':len(nodes),
    'ods_distinct_names':len(set(norm(n['name']) for n in nodes)),
    'ged_people':len(people),
    'ged_families':len(families),
    'matched_unique':sum(1 for n in nodes if n['ged_id']),
    'ambiguous':sum(1 for n in nodes if n['ged_ids'] and not n['ged_id']),
    'unmatched':sum(1 for n in nodes if not n['ged_ids']),
}
OUT.write_text(json.dumps({'nodes':nodes,'edges':ded,'stats':stats},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(stats,ensure_ascii=False,indent=2))
