#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,re
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('matrix',type=Path); ap.add_argument('--root',type=Path,required=True); ap.add_argument('--commit-file',type=Path,required=True); ap.add_argument('--manifest',type=Path,required=True); a=ap.parse_args(); errs=[]
    root=a.root.resolve()
    commit=a.commit_file.read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'[0-9a-f]{40}',commit): errs.append('commit.txt must contain exactly 40 lowercase hex characters')
    manifest={}
    for line in a.manifest.read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if not line or line.startswith('#'): continue
        parts=line.split(maxsplit=1)
        if len(parts)!=2 or not re.fullmatch(r'[0-9a-f]{64}',parts[0]): errs.append(f'bad manifest line: {line}'); continue
        rel=parts[1]
        p=(root/rel).resolve()
        try: p.relative_to(root)
        except ValueError: errs.append(f'path escapes root: {rel}'); continue
        manifest[rel]=parts[0]
    import yaml
    d=yaml.safe_load(Path(a.matrix).read_text(encoding='utf-8'))
    paths={r['artifact_path'] for r in d['acceptance_rows']}
    for rel in paths:
        prefix=rel.rstrip('/')+'/' if rel.endswith('/') else rel
        if rel not in manifest and not any(k.startswith(prefix) for k in manifest):
            errs.append(f'artifact_path missing from manifest: {rel}')
    for rel,h in manifest.items():
        p=(root/rel).resolve()
        try: p.relative_to(root)
        except ValueError: continue
        if not p.is_file(): errs.append(f'missing artifact: {rel}'); continue
        if p.stat().st_size==0: errs.append(f'empty artifact: {rel}'); continue
        if hashlib.sha256(p.read_bytes()).hexdigest()!=h: errs.append(f'hash mismatch: {rel}')
    if errs:
        print(f'FAIL: {len(errs)} evidence integrity error(s)'); [print(' -',e) for e in errs]; return 1
    print(f'PASS: evidence manifest and {len(paths)} acceptance artifact paths verified'); return 0
if __name__=='__main__': raise SystemExit(main())
