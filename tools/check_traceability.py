#!/usr/bin/env python3
from __future__ import annotations
import argparse,ast,re,xml.etree.ElementTree as ET
from pathlib import Path
import yaml
NODE_RE=re.compile(r'^tests/(unit|integration|security|tools|observations|live|ci|mutation)/([^:]+)::([A-Za-z_][A-Za-z0-9_]*)(?:\[([^]]+)\])?$')

def static_tests(root):
    out={}; errs=[]
    for p in (root/'tests').rglob('test_*.py'):
        rel=p.relative_to(root).as_posix()
        if not any(rel.startswith('tests/'+x+'/') for x in ['unit','integration','security','tools','observations','live','ci','mutation']): continue
        try: tree=ast.parse(p.read_text(encoding='utf-8'))
        except Exception as e: errs.append(f'{rel}: parse error {e}'); continue
        for n in tree.body:
            if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)): continue
            ids=set(); skipped=False
            for d in n.decorator_list:
                if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and isinstance(d.func.value,ast.Attribute) and getattr(d.func.value.value,'id',None)=='pytest' and d.func.value.attr=='mark':
                    if d.func.attr=='requirement' and d.args and isinstance(d.args[0],ast.Constant): ids.add(d.args[0].value)
                    if d.func.attr in {'skip','skipif','xfail'}: skipped=True
            body=[x for x in n.body if not (isinstance(x,ast.Expr) and isinstance(x.value,ast.Constant))]
            vacuous=not any(isinstance(x,(ast.Assert,ast.Raise,ast.With,ast.Try,ast.If,ast.For,ast.While,ast.Assign,ast.AnnAssign,ast.AugAssign,ast.Return,ast.Expr)) for x in body)
            assert_true=any(isinstance(x,ast.Assert) and isinstance(x.test,ast.Constant) and x.test.value is True for x in body)
            pytestmark='pytestmark' in {getattr(x,'id',None) for x in tree.body if isinstance(x,ast.Assign)}
            out[f'{rel}::{n.name}']=(ids,skipped,vacuous or assert_true,pytestmark)
    return out,errs

def norm_node(tc):
    cls=tc.attrib.get('classname',''); name=tc.attrib.get('name','')
    if cls.startswith('tests.'):
        cls=cls.replace('.','/')+'.py'
    elif cls.startswith(('unit.','integration.','security.','tools.','observations.','live.','ci.','mutation.')):
        cls='tests/'+cls.replace('.','/')+'.py'
    elif cls.startswith('tests/') and not cls.endswith('.py'): cls+='.py'
    return f'{cls}::{name}'

def junit(paths):
    passed=set(); failed=set(); skipped=set(); props={}; errs=[]
    for cls,path in paths:
        try: root=ET.parse(path).getroot()
        except Exception as e: errs.append(f'{path}: {e}'); continue
        for tc in root.iter('testcase'):
            n=norm_node(tc); req=props.setdefault(n,set())
            for pr in tc.findall('./properties/property'):
                if pr.attrib.get('name')=='requirement': req.update(x.strip() for x in pr.attrib.get('value','').split(',') if x.strip())
            if tc.find('failure') is not None or tc.find('error') is not None: failed.add(n); passed.discard(n)
            elif tc.find('skipped') is not None: skipped.add(n); passed.discard(n)
            else: passed.add(n); failed.discard(n); skipped.discard(n)
    return passed,failed,skipped,props,errs

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('matrix'); ap.add_argument('--root',type=Path,required=True); ap.add_argument('--junit',action='append',default=[]); ap.add_argument('--stage',type=int,choices=[1,2],default=2); a=ap.parse_args()
    d=yaml.safe_load(Path(a.matrix).read_text(encoding='utf-8')); errs=[]; st,es=static_tests(a.root); errs+=es
    mandatory=[r for r in d['acceptance_rows'] if r.get('mandatory') and (a.stage==2 or r.get('stage',1)==1)]
    bindings=[]; bound=set()
    for r in mandatory:
        rid=r['id']
        if not r.get('tests'):
            errs.append(f'{rid}: mandatory row has no bound tests')
        for b in r.get('tests',[]):
            bound.add(b)
            if re.search(r'_item_\d+$',b): errs.append(f'{rid}: placeholder binding forbidden: {b}')
            if not NODE_RE.fullmatch(b): errs.append(f'{rid}: invalid nodeid: {b}'); continue
            base=re.sub(r'\[[^]]+\]$','',b)
            if base not in st: errs.append(f'{rid}: bound test not found: {b}'); continue
            ids,sk,vac,pytestmark=st[base]
            if rid not in ids: errs.append(f'{rid}: missing requirement marker on {b}')
            if sk or pytestmark: errs.append(f'{rid}: static skip/xfail on {b}')
            if vac: errs.append(f'{rid}: trivially empty/vacuous test body: {b}')
            bindings.append((rid,b,r.get('evidence_class','offline')))
    if not a.junit: errs.append('no JUnit evidence supplied')
    inputs=[]
    for x in a.junit:
        if '=' not in x: errs.append(f'invalid --junit: {x}'); continue
        cls,path=x.split('=',1)
        if cls not in {'offline','ci','live'}: errs.append(f'bad evidence class: {cls}')
        inputs.append((cls,Path(path)))
    passed,failed,skipped,props,je=junit(inputs); errs+=je; seen={c for c,_ in inputs}
    for rid,b,cls in bindings:
        if cls not in seen: errs.append(f'{rid}: missing {cls} JUnit evidence')
        if b not in passed: errs.append(f'{rid}: nodeid did not pass: {b}')
        if b in skipped: errs.append(f'{rid}: nodeid skipped: {b}')
        if b in failed: errs.append(f'{rid}: nodeid failed: {b}')
        if rid not in props.get(b,set()): errs.append(f'{rid}: JUnit requirement property missing on {b}')
    for r in mandatory:
        for item,nodes in r.get('source_item_bindings',{}).items():
            for n in nodes:
                if n not in r.get('tests',[]): errs.append(f'{r["id"]}: item {item} nodeid not in row tests: {n}')
                if n not in passed: errs.append(f'{item}: nodeid did not pass: {n}')
    if errs:
        print(f'FAIL: {len(errs)} traceability error(s)'); [print(' -',e) for e in errs]; return 1
    print(f'PASS: {len(bindings)} exact behavioral bindings passed'); return 0
if __name__=='__main__': raise SystemExit(main())
