#!/usr/bin/env python3
"""Check cases that changed from GRANTED to DENIED/UNKNOWN."""

import sys
import pandas as pd
from pathlib import Path

# Add the sead4_llm directory to the path
sys.path.insert(0, str(Path(__file__).parent / "sead4_llm"))

from rag.scraper import DOHAScraper

def check_case(case_num, df, scraper):
    """Check a specific case and show details."""
    case_row = df[df['case_number'] == case_num]
    if case_row.empty:
        print(f"❌ Case {case_num} not found")
        return

    old_outcome = case_row.iloc[0]['outcome']
    full_text = case_row.iloc[0]['full_text']
    case_type = case_row.iloc[0].get('case_type', 'hearing')

    print(f"\n{'='*80}")
    print(f"Case: {case_num}")
    print(f"Type: {case_type}")
    print(f"Old outcome: {old_outcome}")

    # Extract new outcome
    if case_type == 'appeal':
        new_outcome = scraper._extract_appeal_outcome(full_text)
    else:
        new_outcome = scraper._extract_outcome(full_text)

    print(f"New outcome: {new_outcome}")

    if new_outcome != old_outcome:
        print(f"⚠️  CHANGED: {old_outcome} → {new_outcome}")
    else:
        print(f"✓ No change")

    # Show relevant sections
    print(f"\n--- ORDER/DECISION section (first 800 chars) ---")
    if case_type == 'appeal':
        order = scraper._extract_order(full_text)
        print(order[:800])
    else:
        # For hearing decisions, look for the decision section
        decision_match = full_text.lower().find('decision')
        if decision_match != -1:
            print(full_text[decision_match:decision_match+800])
        else:
            print(full_text[-800:])

def main():
    print("Loading cases...")
    df = pd.read_parquet('doha_parsed_cases/all_cases.parquet')
    scraper = DOHAScraper()

    # Cases to check
    cases = [
        'pre2016-128009',
        'pre2016-128270',
        'pre2016-128288',
        'pre2016-128306',
        'pre2016-128513',
    ]

    for case_num in cases:
        check_case(case_num, df, scraper)

    print(f"\n{'='*80}")

if __name__ == "__main__":
    main()
