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

# GitHub file size limits
GITHUB_FILE_LIMIT_MB = 100  # GitHub's actual hard limit
MAX_PARQUET_SIZE_MB = 95  # Target for splitting (leaves room for compression variance)


def validate_parquet_file(file_path: Path, expected_rows: int, operation: str = "save") -> None:
    """
    Validate a parquet file after write to ensure data integrity.

    Args:
        file_path: Path to parquet file
        expected_rows: Number of rows expected
        operation: Description of the operation for logging

    Raises:
        ValueError: If validation fails
    """
    try:
        # Verify file exists
        if not file_path.exists():
            raise FileNotFoundError(f"Parquet file not found after {operation}: {file_path}")

        # Verify round-trip
        df_verify = pd.read_parquet(file_path)
        actual_rows = len(df_verify)

        if actual_rows != expected_rows:
            raise ValueError(f"Parquet validation failed: expected {expected_rows} rows, got {actual_rows}")

        # Verify PAR1 magic bytes in footer
        with open(file_path, 'rb') as f:
            f.seek(-4, 2)  # Seek to last 4 bytes
            footer = f.read(4)
            if footer != b'PAR1':
                raise ValueError(f"Invalid parquet footer: expected b'PAR1', got {footer!r}")

        logger.debug(f"✓ Validated parquet file: {actual_rows} rows, {file_path.stat().st_size / (1024*1024):.1f}MB")

    except Exception as e:
        logger.error(f"Parquet validation failed for {file_path}: {e}")
        raise


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
        # Clean up any old split files first
        base_name = output_path.stem
        suffix = output_path.suffix
        old_split_files = list(output_path.parent.glob(f"{base_name}_*{suffix}"))
        if old_split_files:
            logger.info(f"Cleaning up {len(old_split_files)} old split files (data now fits in single file)")
            for old_file in old_split_files:
                old_file.unlink()

        df.to_parquet(output_path, index=False, engine='pyarrow', compression='gzip')
        validate_parquet_file(output_path, len(df), "single file save")
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

    # Clean up old single file if it exists (we're creating split files now)
    if output_path.exists():
        logger.info(f"Removing old single file {output_path.name} (will be replaced by split files)")
        output_path.unlink()

    # Also clean up any old split files (in case number of splits changed)
    old_split_files = list(parent.glob(f"{base_name}_*{suffix}"))
    if old_split_files:
        logger.info(f"Cleaning up {len(old_split_files)} old split files before creating new ones")
        for old_file in old_split_files:
            old_file.unlink()

    for i, start_idx in enumerate(range(0, len(df), cases_per_file), 1):
        chunk = df.iloc[start_idx:start_idx + cases_per_file]
        chunk_path = parent / f"{base_name}_{i}{suffix}"
        chunk.to_parquet(chunk_path, index=False, engine='pyarrow', compression='gzip')
        validate_parquet_file(chunk_path, len(chunk), f"chunk {i} save")
        size_mb = chunk_path.stat().st_size / (1024 * 1024)

        # Verify chunk doesn't exceed GitHub's limit
        if size_mb > GITHUB_FILE_LIMIT_MB:
            logger.error(f"❌ Chunk {i} exceeds GitHub's {GITHUB_FILE_LIMIT_MB}MB limit: {size_mb:.1f}MB")
            raise ValueError(f"Parquet splitting failed, chunk {i} too large: {size_mb:.1f}MB > {GITHUB_FILE_LIMIT_MB}MB")

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
            # Handle both numeric (50) and batch (batch27) formats
            num_str = parts[2]
            if num_str.startswith('batch'):
                num = int(num_str.replace('batch', ''))
            else:
                try:
                    num = int(num_str)
                except ValueError:
                    num = 0  # Fallback for unexpected formats
            return (case_type, num)
        # Old format: checkpoint_50
        elif len(parts) == 2:
            try:
                return ('', int(parts[1]))
            except ValueError:
                return ('', 0)
        else:
            return ('', 0)

    # Find checkpoint files in main directory and all archive subdirectories
    checkpoint_files = list(input_path.glob("checkpoint_*.json"))

    # Also search in archive directories
    archive_dir = input_path / "checkpoints_archive"
    if archive_dir.exists():
        archive_checkpoints = list(archive_dir.glob("**/checkpoint_*.json"))
        checkpoint_files.extend(archive_checkpoints)
        if archive_checkpoints:
            logger.info(f"Found {len(archive_checkpoints)} checkpoint files in archive directories")

    checkpoint_files = sorted(checkpoint_files, key=checkpoint_sort_key)

    logger.info(f"Found {len(checkpoint_files)} total checkpoint files")

    # Merge all cases, tracking by case_number to dedupe
    cases_by_number = {}

    for checkpoint_file in checkpoint_files:
        try:
            with open(checkpoint_file) as f:
                cases = json.load(f)

            # Validate structure
            if not isinstance(cases, list):
                logger.error(f"{checkpoint_file.name}: Invalid format (expected list, got {type(cases).__name__}), skipping")
                continue

            new_count = 0
            for case in cases:
                if not isinstance(case, dict):
                    logger.warning(f"{checkpoint_file.name}: Skipping non-dict case")
                    continue
                case_number = case.get('case_number')
                if case_number and case_number not in cases_by_number:
                    cases_by_number[case_number] = case
                    new_count += 1

            logger.info(f"{checkpoint_file.name}: {len(cases)} cases ({new_count} new)")
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
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
