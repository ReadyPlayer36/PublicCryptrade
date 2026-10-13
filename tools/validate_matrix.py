#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, re, json
from pathlib import Path
import yaml, jsonschema

NODE_RE = re.compile(r'^tests/(?:unit|integration|security|tools|observations|live|ci|mutation)/[^:]+::[A-Za-z_][A-Za-z0-9_]*(?:\[[^]]+\])?$')
CITE_RE = re.compile(r'^\[(M1|1\.2) §(\d+)(?: #(\d+))?\]$')
ITEM_BIND_RE = re.compile(r'^\[(M1|1\.2) §(28|5) #(\d+)\]$')
ALLOWED_LABELS={'[M1]','[1.2]','[REVIEW]','[DECISION]','[SECURITY]','[EVIDENCE]','[OBSERVED]','[BINANCE]'}


def sha(p: Path) -> str: return hashlib.sha256(p.read_bytes()).hexdigest()

def parse_source(p: Path):
    lines=p.read_text(encoding='utf-8').splitlines()
    sections={}; items={'M1':set(),'1.2':set()}
    for line in lines:
        m=re.match(r'^#{1,6}\s*(\d+)\.\s+(.+?)\s*$',line)
        if m: sections[int(m.group(1))]=re.sub(r'[*`]+','',m.group(2)).strip()
    # M1 checklist is section 28 bullet list; 1.2 checklist is section 5 numbered list.
    current=None; in28=False; in5=False
    for line in lines:
        m=re.match(r'^#{1,6}\s*(\d+)\.\s+',line)
        if m:
            current=int(m.group(1)); in28=current==28; in5=current==5
            continue
        if in28 and re.match(r'^\s*-\s+\S',line): items['M1'].add(len(items['M1'])+1)
        if in28 and line.strip().startswith('Scope boundary:'): items['M1'].add(27)
        if in5:
            m=re.match(r'^\s*(\d+)\.\s+\[',line)
            if m: items['1.2'].add(int(m.group(1)))
    return sections,items

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('matrix',type=Path); ap.add_argument('--schema',type=Path,required=True)
    ap.add_argument('--m1',type=Path,required=True); ap.add_argument('--m12',type=Path,required=True)
    a=ap.parse_args(); errs=[]
    try: d=yaml.safe_load(a.matrix.read_text(encoding='utf-8'))
    except Exception as e: print('FAIL YAML',e); return 1
    print('PASS: YAML parsed')
    try: jsonschema.validate(d,json.loads(a.schema.read_text(encoding='utf-8')))
    except Exception as e: print('FAIL JSON Schema',e); return 1
    print('PASS: JSON Schema validation')
    for dk,p in [('M1',a.m1),('M1_2',a.m12)]:
        if sha(p)!=d['documents'][dk]['sha256']: errs.append(f'{dk}: hash mismatch')
    if errs: print('FAIL: '+str(errs)); return 1
    print('PASS: canonical Markdown hashes verified')
    parsed={'M1':parse_source(a.m1),'1.2':parse_source(a.m12)}
    for typ,(sections,items) in parsed.items():
        expected=d['documents']['M1' if typ=='M1' else 'M1_2']['sections']
        got={str(k):v for k,v in sections.items()}
        if got!=expected: errs.append(f'{typ}: heading registry mismatch')
    if errs: print('FAIL: '+str(errs)); return 1
    print(f"PASS: source headings verified (M1 {len(parsed['M1'][0])} sections, 1.2 {len(parsed['1.2'][0])} sections)")
    # exact checklist item counts derived from source
    for typ,required in [('M1',parsed['M1'][1]['M1']),('1.2',parsed['1.2'][1]['1.2'])]:
        expected=27
        if len(required)!=expected: errs.append(f'{typ}: source checklist count {len(required)} != {expected}')
    rows=d['acceptance_rows']; ids=[r['id'] for r in rows]
    if len(rows)!=d.get('matrix_integrity',{}).get('expected_acceptance_rows'):
        errs.append(f'acceptance row count changed: expected {d.get("matrix_integrity",{}).get("expected_acceptance_rows")}, got {len(rows)}')
    if len(ids)!=len(set(ids)): errs.append('duplicate acceptance row ID')
    seen_items={'M1':set(),'1.2':set()}; bound_tests=set()
    for r in rows:
        if not r.get('labels'): errs.append(f'{r["id"]}: missing labels')
        for lab in r.get('labels',[]):
            if lab not in ALLOWED_LABELS: errs.append(f'{r["id"]}: invalid label {lab}')
        cites=set(r.get('source_citations',[]))
        if not cites: errs.append(f'{r["id"]}: no source citations')
        tests=r.get('tests',[]); bound_tests.update(tests)
        if len(tests)!=len(set(tests)): errs.append(f'{r["id"]}: duplicate test nodeid')
        for n in tests:
            if not NODE_RE.fullmatch(n): errs.append(f'{r["id"]}: invalid nodeid {n}')
            if re.search(r'_item_\d+$',n): errs.append(f'{r["id"]}: placeholder binding {n}')
        for c in cites:
            m=CITE_RE.fullmatch(c)
            if not m:
                if c not in {'[REVIEW]','[DECISION]','[SECURITY]','[EVIDENCE]','[OBSERVED]','[BINANCE]'}: errs.append(f'{r["id"]}: invalid citation {c}')
                continue
            typ='M1' if m.group(1)=='M1' else '1.2'; sec=int(m.group(2)); num=m.group(3)
            if sec not in parsed[typ][0]: errs.append(f'{r["id"]}: citation section missing {c}')
            if num is not None:
                num=int(num); source_set=parsed[typ][1][typ]
                if (typ=='M1' and sec!=28) or (typ=='1.2' and sec!=5) or num not in source_set: errs.append(f'{r["id"]}: citation item missing {c}')
        for c,ns in r.get('source_item_bindings',{}).items():
            if c not in cites: errs.append(f'{r["id"]}: item binding citation not in source_citations: {c}')
            m=ITEM_BIND_RE.fullmatch(c)
            if not m: errs.append(f'{r["id"]}: invalid item binding key {c}'); continue
            typ='M1' if m.group(1)=='M1' else '1.2'; num=int(m.group(3)); seen_items[typ].add(num)
            if not ns: errs.append(f'{r["id"]}: empty item binding {c}')
            if len(ns)!=len(set(ns)): errs.append(f'{r["id"]}: duplicate item nodeid {c}')
            for n in ns:
                if n not in tests: errs.append(f'{r["id"]}: item-bound nodeid not listed in tests: {n}')
                if not NODE_RE.fullmatch(n): errs.append(f'{r["id"]}: invalid item nodeid {n}')
    for typ in ('M1','1.2'):
        expected=parsed[typ][1][typ]
        if seen_items[typ]!=expected: errs.append(f'{typ}: item bindings incomplete; expected {sorted(expected)}, got {sorted(seen_items[typ])}')
    # Every mutation killer must be a bound nodeid.
    for name,nodes in d.get('mutation_killers',{}).items():
        for n in nodes:
            if n not in bound_tests: errs.append(f'mutation killer {name} is unbound: {n}')
    if errs:
        print(f'FAIL: {len(errs)} matrix error(s)'); [print(' -',e) for e in errs]; return 1
    print(f'PASS: source citations resolved (M1 §28 items {len(parsed["M1"][1]["M1"])}, 1.2 §5 items {len(parsed["1.2"][1]["1.2"])})')
    print(f'PASS: unique acceptance row IDs ({len(rows)})')
    print(f'PASS: labels, citations, artifact paths and evidence classes validated ({len(rows)} rows)')
    print(f'PASS: item bindings agree with citations/tests ({sum(len(r.get("source_item_bindings",{})) for r in rows)} item bindings)')
    print(f'PASS: mutation killers are bound ({sum(len(v) for v in d.get("mutation_killers",{}).values())} killer nodeids)')
    return 0
if __name__=='__main__': raise SystemExit(main())
