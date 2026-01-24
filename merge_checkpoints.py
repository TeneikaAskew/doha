#!/usr/bin/env python3
"""
Merge checkpoint files into all_cases.json and all_cases.parquet.
Combines all checkpoint_*.json files, deduplicating by case_number.
"""
import json
from pathlib import Path
from loguru import logger

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


def merge_checkpoints(input_dir: str = "doha_parsed_cases", output_parquet: bool = True, output_json: bool = True):
    """Merge all checkpoint files into all_cases.json and/or all_cases.parquet.

    Args:
        input_dir: Directory containing checkpoint files
        output_parquet: Save as Parquet format (much smaller file size)
        output_json: Save as JSON format
    """
    input_path = Path(input_dir)

    # Find all checkpoint files (handles both old format checkpoint_50.json and new format checkpoint_hearing_50.json)
    def checkpoint_sort_key(f):
        parts = f.stem.split('_')
        # New format: checkpoint_hearing_50 or checkpoint_appeal_50
        if len(parts) == 3:
            case_type = parts[1]
            num = int(parts[2])
            return (case_type, num)
        # Old format: checkpoint_50
        else:
            return ('', int(parts[1]))

    checkpoint_files = sorted(input_path.glob("checkpoint_*.json"), key=checkpoint_sort_key)

    logger.info(f"Found {len(checkpoint_files)} checkpoint files")

    # Merge all cases, tracking by case_number to dedupe
    cases_by_number = {}

    for checkpoint_file in checkpoint_files:
        try:
            with open(checkpoint_file) as f:
                cases = json.load(f)

            new_count = 0
            for case in cases:
                case_number = case.get('case_number')
                if case_number and case_number not in cases_by_number:
                    cases_by_number[case_number] = case
                    new_count += 1

            logger.info(f"{checkpoint_file.name}: {len(cases)} cases ({new_count} new)")
        except Exception as e:
            logger.error(f"Error loading {checkpoint_file}: {e}")

    # Convert to list
    all_cases = list(cases_by_number.values())

    # Count by case type
    from collections import Counter
    type_counts = Counter(c.get('case_type', 'unknown') for c in all_cases)

    logger.info(f"\nTotal unique cases: {len(all_cases)}")
    for case_type, count in sorted(type_counts.items()):
        logger.info(f"  {case_type}: {count}")

    # Save merged results
    if output_json:
        output_file = input_path / "all_cases.json"
        with open(output_file, 'w') as f:
            json.dump(all_cases, f, indent=2)
        size_mb = output_file.stat().st_size / (1024 * 1024)
        logger.success(f"Saved {len(all_cases)} cases to {output_file} ({size_mb:.1f}MB)")

    if output_parquet:
        if not HAS_PANDAS:
            logger.warning("pandas not installed, skipping Parquet output. Install with: pip install pandas pyarrow")
        else:
            parquet_file = input_path / "all_cases.parquet"
            df = pd.DataFrame(all_cases)
            df.to_parquet(parquet_file, index=False, engine='pyarrow', compression='gzip')
            size_mb = parquet_file.stat().st_size / (1024 * 1024)
            logger.success(f"Saved {len(all_cases)} cases to {parquet_file} ({size_mb:.1f}MB)")

    return all_cases


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Merge checkpoint files into all_cases.json and/or all_cases.parquet")
    parser.add_argument("--input", "-i", default="doha_parsed_cases",
                        help="Directory containing checkpoint files")
    parser.add_argument("--no-parquet", action="store_true",
                        help="Skip Parquet output")
    parser.add_argument("--no-json", action="store_true",
                        help="Skip JSON output")
    args = parser.parse_args()

    merge_checkpoints(args.input, output_parquet=not args.no_parquet, output_json=not args.no_json)
