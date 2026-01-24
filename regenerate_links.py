#!/usr/bin/env python3
"""Regenerate all_case_links.json from individual link files"""
import json
from pathlib import Path

all_links = []
d = Path('doha_full_scrape')

for f in sorted(d.glob('hearing_links_*.json')):
    try:
        with open(f, 'r') as file:
            links = json.load(file)
        if not isinstance(links, list):
            print(f'⚠️  {f.name}: Invalid format (expected list, got {type(links).__name__}), skipping')
            continue
        all_links.extend(links)
        print(f'{f.name}: {len(links)}')
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f'❌ {f.name}: Failed to load - {e}')
        continue

for f in sorted(d.glob('appeal_links_*.json')):
    try:
        with open(f, 'r') as file:
            links = json.load(file)
        if not isinstance(links, list):
            print(f'⚠️  {f.name}: Invalid format (expected list, got {type(links).__name__}), skipping')
            continue
        all_links.extend(links)
        print(f'{f.name}: {len(links)}')
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f'❌ {f.name}: Failed to load - {e}')
        continue

with open(d / 'all_case_links.json', 'w') as f:
    json.dump(all_links, f, indent=2)

hearing = sum(1 for l in all_links if l[0] == 'hearing')
appeal = sum(1 for l in all_links if l[0] == 'appeal')
print(f'\nTotal: {len(all_links)} (hearing: {hearing}, appeal: {appeal})')
print(f'Saved to: {d}/all_case_links.json')
