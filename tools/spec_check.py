#!/usr/bin/env python3
from __future__ import annotations
import argparse,subprocess,sys
from pathlib import Path

def run(cmd):
    p=subprocess.run(cmd,capture_output=True,text=True)
    return p.returncode,p.stdout,p.stderr

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--project-m1',type=Path,required=True); ap.add_argument('--project-m12',type=Path,required=True); a=ap.parse_args(); root=Path(__file__).resolve().parents[1]
    commands=[
      [sys.executable,str(root/'tools/validate_matrix.py'),str(root/'matrix.yaml'),'--schema',str(root/'matrix_schema.json'),'--m1',str(root/'docs/source/milestone_1.md'),'--m12',str(root/'docs/source/milestone_1_2.md')],
      [sys.executable,str(root/'tools/compare_source_markdown.py'),str(root/'docs/source/milestone_1.md'),str(a.project_m1)],
      [sys.executable,str(root/'tools/compare_source_markdown.py'),str(root/'docs/source/milestone_1_2.md'),str(a.project_m12)],
      [sys.executable,'-m','pytest','-q',str(root/'tests/tools/test_spec_tooling.py')]
    ]
    out=[]; code=0
    for c in commands:
        rc,so,se=run(c); out.append('$ '+' '.join(map(str,c))+'\n'+so+se); code=max(code,rc)
    log=root/'evidence'/'spec_check.log'; log.write_text('\n\n'.join(out),encoding='utf-8'); print(log.read_text(),end=''); return code
if __name__=='__main__': raise SystemExit(main())
