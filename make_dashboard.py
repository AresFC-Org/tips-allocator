#!/usr/bin/env python3
"""Bake data/tips_data.json and dashboard_engine.js into the published page.

Usage:  python3 make_dashboard.py

Full refresh:  python3 fetch_direct.py && python3 build_data.py && python3 make_dashboard.py
Writes the same self-contained page (fonts aside) to two places:
  docs/index.html                GitHub Pages site (served from main /docs)
  dist/TIPS_ETF_Allocator.html   local copy / Claude artifact
"""
import json, os

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTS = [os.path.join(ROOT, 'docs', 'index.html'), os.path.join(ROOT, 'dist', 'TIPS_ETF_Allocator.html')]

# The artifact viewer adds its own document skeleton; GitHub Pages serves the file
# as-is, so docs/index.html gets one (standards mode, UTF-8, phone viewport).
SKELETON = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<style>body{margin:0}</style>\n</head>\n<body>\n%s\n</body>\n</html>\n')

def main():
    html = open(os.path.join(ROOT, 'dashboard_template.html'), encoding='utf-8').read()
    engine = open(os.path.join(ROOT, 'dashboard_engine.js'), encoding='utf-8').read()
    data = json.load(open(os.path.join(ROOT, 'data', 'tips_data.json')))
    html = html.replace('/*ENGINE*/', engine).replace('/*DATA*/null', json.dumps(data, separators=(',', ':')))
    for out in OUTS:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w', encoding='utf-8') as fh:
            fh.write(SKELETON % html if out == OUTS[0] else html)
        print(f'wrote {out}')
    print(f'holdings as of {", ".join(sorted(set(data["asOf"].values())))}')

if __name__ == '__main__':
    main()
