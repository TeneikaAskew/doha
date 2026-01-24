#!/usr/bin/env python3
"""Regenerate all_case_links.json from individual link files"""
import json
from pathlib import Path

all_links = []
d = Path('doha_full_scrape')

for f in sorted(d.glob('hearing_links_*.json')):
    links = json.load(open(f))
    all_links.extend(links)
    print(f'{f.name}: {len(links)}')

for f in sorted(d.glob('appeal_links_*.json')):
    links = json.load(open(f))
    all_links.extend(links)
    print(f'{f.name}: {len(links)}')

with open(d / 'all_case_links.json', 'w') as f:
    json.dump(all_links, f, indent=2)

hearing = sum(1 for l in all_links if l[0] == 'hearing')
appeal = sum(1 for l in all_links if l[0] == 'appeal')
print(f'\nTotal: {len(all_links)} (hearing: {hearing}, appeal: {appeal})')
print(f'Saved to: {d}/all_case_links.json')
