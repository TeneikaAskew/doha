#!/usr/bin/env python3
"""Verify the fix for the 2 regression cases."""

import sys
import pandas as pd
from pathlib import Path

# Add the sead4_llm directory to the path
sys.path.insert(0, str(Path(__file__).parent / "sead4_llm"))

from rag.scraper import DOHAScraper

def verify_cases():
    """Test the 2 regression cases to verify the fix works."""

    # Load the dataset
    print("Loading cases...")
    df = pd.read_parquet('doha_parsed_cases/all_cases.parquet')

    # Test cases
    test_cases = ['appeal-2023-210780', 'appeal-2023-211514']

    scraper = DOHAScraper()

    for case_num in test_cases:
        case_row = df[df['case_number'] == case_num]
        if case_row.empty:
            print(f"❌ Case {case_num} not found")
            continue

        old_outcome = case_row.iloc[0]['outcome']
        full_text = case_row.iloc[0]['full_text']

        # Re-extract the case with the fixed patterns
        print(f"\n{'='*80}")
        print(f"Testing: {case_num}")
        print(f"Old outcome: {old_outcome}")

        # Extract appeal outcome with new patterns
        new_outcome = scraper._extract_appeal_outcome(full_text)

        print(f"New outcome: {new_outcome}")

        if new_outcome != old_outcome:
            print(f"✅ Changed: {old_outcome} → {new_outcome}")
        else:
            print(f"⚠️  No change: {old_outcome}")

        # Show what patterns matched
        order_text = scraper._extract_order(full_text).lower()
        print(f"\nOrder text (first 500 chars):")
        print(order_text[:500])

        # Check if it found the decision
        if 'affirmed' in order_text:
            print("\n✓ Found AFFIRMED in order")
        if 'reversed' in order_text:
            print("\n✓ Found REVERSED in order")
        if 'remanded' in order_text:
            print("\n✓ Found REMANDED in order")

    print(f"\n{'='*80}")
    print("Verification complete!")

if __name__ == "__main__":
    verify_cases()
