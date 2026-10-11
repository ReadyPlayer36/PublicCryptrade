#!/usr/bin/env python3
from __future__ import annotations
import argparse
import difflib
import re
from pathlib import Path

def normalize_line(line: str) -> str:
    line = line.rstrip()
    line = re.sub(r'^\s*#{1,6}\s*', '', line)
    line = re.sub(r'^\s*[-*+]\s+', '', line)
    line = re.sub(r'\*+([^*]+)\*+', r'\1', line)
    line = re.sub(r'`([^`]+)`', r'\1', line)
    line = re.sub(r'\s*\|\s*', '|', line)
    line = re.sub(r'\|[-: ]+\|', '|---|', line)
    line = re.sub(r'[ \t]+', ' ', line)
    return line.strip()

def norm(s: str) -> list[str]:
    s = s.replace('\r\n', '\n').replace('\r', '\n')
    return [x for x in (normalize_line(line) for line in s.splitlines()) if x]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('canonical', type=Path)
    ap.add_argument('project', type=Path)
    ap.add_argument('--output', type=Path)
    a = ap.parse_args()
    x, y = norm(a.canonical.read_text(encoding='utf-8')), norm(a.project.read_text(encoding='utf-8'))
    if x != y:
        diff = ''.join(difflib.unified_diff(x, y, fromfile=str(a.canonical), tofile=str(a.project), lineterm='\n'))
        out = 'FAIL: normalized canonical/project source content differs\n' + diff
        print(out, end='')
        if a.output: a.output.write_text(out, encoding='utf-8')
        return 1
    out = 'PASS: normalized canonical/project source content identical\n'
    print(out, end='')
    if a.output: a.output.write_text(out, encoding='utf-8')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
