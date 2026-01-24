#!/usr/bin/env python3
"""Archive current checkpoint files before starting a new download."""

import shutil
from pathlib import Path
from datetime import datetime
from loguru import logger

def archive_checkpoints(
    checkpoint_dir: Path = Path("doha_parsed_cases"),
    archive_base: Path = Path("doha_parsed_cases/checkpoints_archive")
):
    """
    Move all checkpoint_*.json files to an archive folder with timestamp.

    Args:
        checkpoint_dir: Directory containing checkpoint files
        archive_base: Base directory for archives
    """
    checkpoint_dir = Path(checkpoint_dir)
    archive_base = Path(archive_base)

    # Find all checkpoint files
    checkpoint_files = list(checkpoint_dir.glob("checkpoint_*.json"))

    if not checkpoint_files:
        logger.info("No checkpoint files found to archive")
        return

    # Create timestamped archive directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = archive_base / f"checkpoints_{timestamp}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Archiving {len(checkpoint_files)} checkpoint files to {archive_dir}")

    # Move each checkpoint file
    moved_count = 0
    for checkpoint_file in checkpoint_files:
        try:
            dest = archive_dir / checkpoint_file.name
            shutil.move(str(checkpoint_file), str(dest))
            moved_count += 1
        except Exception as e:
            logger.error(f"Failed to move {checkpoint_file.name}: {e}")

    logger.success(f"Archived {moved_count}/{len(checkpoint_files)} checkpoint files to {archive_dir}")

    # Show archive size
    total_size = sum(f.stat().st_size for f in archive_dir.glob("*.json"))
    size_mb = total_size / (1024 * 1024)
    logger.info(f"Archive size: {size_mb:.1f}MB")

if __name__ == "__main__":
    archive_checkpoints()
