#!/usr/bin/env python3
"""
Split existing checkpoint files into separate appeals and hearings checkpoints.
Each new checkpoint will contain only 50 cases max.
"""
import json
from pathlib import Path
from loguru import logger
from collections import defaultdict


def split_checkpoints(input_dir: Path, output_dir: Path = None):
    """Split large checkpoint files into type-specific 50-case checkpoints.

    Args:
        input_dir: Directory containing existing checkpoint files
        output_dir: Output directory (defaults to input_dir)
    """
    if output_dir is None:
        output_dir = input_dir

    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all checkpoint files
    checkpoint_files = sorted(input_dir.glob("checkpoint_*.json"))

    # Skip already-split checkpoints (have type in name like checkpoint_hearing_50.json)
    old_checkpoints = [f for f in checkpoint_files if not any(t in f.name for t in ['_hearing_', '_appeal_'])]

    if not old_checkpoints:
        logger.info("No old-format checkpoint files found to split")
        return

    logger.info(f"Found {len(old_checkpoints)} checkpoint files to split")

    # Collect all cases by type
    all_hearings = []
    all_appeals = []
    seen_case_numbers = set()

    for checkpoint_file in old_checkpoints:
        logger.info(f"Reading {checkpoint_file.name}...")
        try:
            with open(checkpoint_file) as f:
                cases = json.load(f)

            for case in cases:
                case_number = case.get('case_number', '')
                if case_number in seen_case_numbers:
                    continue  # Skip duplicates
                seen_case_numbers.add(case_number)

                # Determine case type from case_number (appeals have "appeal" in the name)
                # or fall back to case_type field
                if 'appeal' in case_number.lower():
                    case_type = 'appeal'
                else:
                    case_type = case.get('case_type', 'hearing')

                if case_type == 'appeal':
                    all_appeals.append(case)
                else:
                    all_hearings.append(case)

        except Exception as e:
            logger.error(f"Error reading {checkpoint_file}: {e}")

    logger.info(f"Total unique cases: {len(all_hearings)} hearings, {len(all_appeals)} appeals")

    # Save new checkpoints - 50 cases each
    def save_in_batches(cases, case_type):
        for i in range(0, len(cases), 50):
            batch = cases[i:i+50]
            batch_num = (i // 50) + 1
            checkpoint_file = output_dir / f"checkpoint_{case_type}_{batch_num * 50}.json"

            with open(checkpoint_file, 'w') as f:
                json.dump(batch, f, indent=2)

            # Get file size
            size_mb = checkpoint_file.stat().st_size / (1024 * 1024)
            logger.success(f"Saved {checkpoint_file.name}: {len(batch)} cases, {size_mb:.1f}MB")

    save_in_batches(all_hearings, 'hearing')
    save_in_batches(all_appeals, 'appeal')

    # Ask before deleting old checkpoints
    logger.info(f"\nOld checkpoint files that can be deleted:")
    for f in old_checkpoints:
        size_mb = f.stat().st_size / (1024 * 1024)
        logger.info(f"  {f.name}: {size_mb:.1f}MB")

    return old_checkpoints


def cleanup_old_checkpoints(input_dir: Path):
    """Delete old-format checkpoint files after splitting."""
    checkpoint_files = sorted(input_dir.glob("checkpoint_*.json"))
    old_checkpoints = [f for f in checkpoint_files if not any(t in f.name for t in ['_hearing_', '_appeal_'])]

    for f in old_checkpoints:
        logger.info(f"Deleting {f.name}")
        f.unlink()

    logger.success(f"Deleted {len(old_checkpoints)} old checkpoint files")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Split checkpoint files by case type")
    parser.add_argument("--input", default="./doha_parsed_cases",
                       help="Input directory with checkpoint files")
    parser.add_argument("--output", default=None,
                       help="Output directory (defaults to input)")
    parser.add_argument("--cleanup", action="store_true",
                       help="Delete old checkpoint files after splitting")

    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output) if args.output else None

    old_files = split_checkpoints(input_dir, output_dir)

    if args.cleanup and old_files:
        response = input("\nDelete old checkpoint files? [y/N]: ")
        if response.lower() == 'y':
            cleanup_old_checkpoints(input_dir)
