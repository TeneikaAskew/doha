#!/usr/bin/env python3
"""
Merge checkpoint files into all_cases.json.
Combines all checkpoint_*.json files, deduplicating by case_number.
"""
import json
from pathlib import Path
from loguru import logger


def merge_checkpoints(input_dir: str = "doha_parsed_cases"):
    """Merge all checkpoint files into all_cases.json"""
    input_path = Path(input_dir)

    # Find all checkpoint files
    checkpoint_files = sorted(input_path.glob("checkpoint_*.json"),
                              key=lambda f: int(f.stem.split('_')[1]))

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

    # Save merged result
    output_file = input_path / "all_cases.json"
    with open(output_file, 'w') as f:
        json.dump(all_cases, f, indent=2)

    logger.success(f"\nSaved {len(all_cases)} cases to {output_file}")

    return all_cases


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Merge checkpoint files into all_cases.json")
    parser.add_argument("--input", "-i", default="doha_parsed_cases",
                        help="Directory containing checkpoint files")
    args = parser.parse_args()

    merge_checkpoints(args.input)
