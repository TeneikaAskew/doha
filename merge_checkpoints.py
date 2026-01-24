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

# GitHub file size limit with buffer
MAX_PARQUET_SIZE_MB = 90  # Stay under GitHub's 100MB limit


def save_parquet_with_size_limit(df: "pd.DataFrame", output_path: Path, max_size_mb: float = MAX_PARQUET_SIZE_MB):
    """Save DataFrame to Parquet, splitting into multiple files if needed to stay under size limit.

    Args:
        df: DataFrame to save
        output_path: Base path for output (e.g., all_cases.parquet)
        max_size_mb: Maximum file size in MB (default: 90MB to stay under GitHub's 100MB limit)

    Returns:
        List of created file paths
    """
    import tempfile
    import os

    # First, try saving the whole thing to estimate size
    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        df.to_parquet(tmp_path, index=False, engine='pyarrow', compression='gzip')
        total_size_mb = os.path.getsize(tmp_path) / (1024 * 1024)
    finally:
        os.unlink(tmp_path)

    # If it fits in one file, save directly
    if total_size_mb <= max_size_mb:
        df.to_parquet(output_path, index=False, engine='pyarrow', compression='gzip')
        size_mb = output_path.stat().st_size / (1024 * 1024)
        logger.success(f"Saved {len(df)} cases to {output_path} ({size_mb:.1f}MB)")
        return [output_path]

    # Need to split - estimate cases per file
    bytes_per_case = (total_size_mb * 1024 * 1024) / len(df)
    cases_per_file = int((max_size_mb * 1024 * 1024) / bytes_per_case * 0.95)  # 5% buffer

    logger.info(f"Total size would be {total_size_mb:.1f}MB, splitting into ~{cases_per_file} cases per file")

    created_files = []
    base_name = output_path.stem  # e.g., "all_cases"
    suffix = output_path.suffix   # e.g., ".parquet"
    parent = output_path.parent

    for i, start_idx in enumerate(range(0, len(df), cases_per_file), 1):
        chunk = df.iloc[start_idx:start_idx + cases_per_file]
        chunk_path = parent / f"{base_name}_{i}{suffix}"
        chunk.to_parquet(chunk_path, index=False, engine='pyarrow', compression='gzip')
        size_mb = chunk_path.stat().st_size / (1024 * 1024)
        logger.success(f"Saved {len(chunk)} cases to {chunk_path} ({size_mb:.1f}MB)")
        created_files.append(chunk_path)

    return created_files


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
            save_parquet_with_size_limit(df, parquet_file, max_size_mb=MAX_PARQUET_SIZE_MB)

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
