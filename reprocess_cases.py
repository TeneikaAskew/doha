#!/usr/bin/env python3
"""
Reprocess existing cases to re-extract metadata from full_text.
This updates judge, outcome, guidelines, sections, etc. without re-downloading PDFs.
"""
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "sead4_llm"))

from rag.scraper import DOHAScraper
from loguru import logger


def reprocess_cases(input_file: str, output_file: str = None, force_all: bool = False):
    """
    Reprocess cases to re-extract metadata from existing full_text.

    Args:
        input_file: Path to existing all_cases.json
        output_file: Path to save updated cases (defaults to input_file)
        force_all: If True, reprocess all cases. If False, only reprocess cases with Unknown values.
    """
    input_path = Path(input_file)
    output_path = Path(output_file) if output_file else input_path

    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return

    # Load existing cases
    logger.info(f"Loading cases from {input_path}")
    with open(input_path) as f:
        cases = json.load(f)

    logger.info(f"Loaded {len(cases)} cases")

    # Create scraper instance for extraction methods
    scraper = DOHAScraper(output_dir=input_path.parent)

    updated_count = 0
    skipped_count = 0
    error_count = 0

    for i, case in enumerate(cases):
        case_number = case.get('case_number', f'Unknown-{i}')
        full_text = case.get('full_text', '')

        if not full_text:
            logger.warning(f"[{i+1}/{len(cases)}] {case_number}: No full_text, skipping")
            skipped_count += 1
            continue

        # Check if needs reprocessing
        needs_update = force_all or any([
            case.get('outcome') in ('Unknown', 'UNKNOWN', None, ''),
            case.get('judge') in ('Unknown', None, ''),
            not case.get('guidelines'),
            not case.get('formal_findings'),
        ])

        if not needs_update:
            skipped_count += 1
            continue

        try:
            # Re-extract all metadata from full_text
            old_outcome = case.get('outcome', 'Unknown')
            old_judge = case.get('judge', 'Unknown')

            case['date'] = scraper._extract_date(full_text)
            case['outcome'] = scraper._extract_outcome(full_text)
            case['guidelines'] = scraper._extract_guidelines(full_text)
            case['sor_allegations'] = scraper._extract_sor_allegations(full_text)
            case['mitigating_factors'] = scraper._extract_mitigating_factors(full_text)
            case['judge'] = scraper._extract_judge(full_text)
            case['summary'] = scraper._create_summary(full_text)
            case['formal_findings'] = scraper._extract_formal_findings(full_text)

            new_outcome = case['outcome']
            new_judge = case['judge']

            changes = []
            if old_outcome != new_outcome:
                changes.append(f"outcome: {old_outcome} -> {new_outcome}")
            if old_judge != new_judge:
                changes.append(f"judge: {old_judge} -> {new_judge}")

            if changes:
                logger.success(f"[{i+1}/{len(cases)}] {case_number}: {', '.join(changes)}")
            else:
                logger.info(f"[{i+1}/{len(cases)}] {case_number}: reprocessed (no changes)")

            updated_count += 1

            # Save checkpoint every 100 cases
            if updated_count % 100 == 0:
                with open(output_path, 'w') as f:
                    json.dump(cases, f, indent=2)
                logger.info(f"  Checkpoint saved: {updated_count} cases updated")

        except Exception as e:
            logger.error(f"[{i+1}/{len(cases)}] {case_number}: Error - {e}")
            error_count += 1

    # Save final results
    with open(output_path, 'w') as f:
        json.dump(cases, f, indent=2)

    logger.info(f"\n{'='*60}")
    logger.success(f"REPROCESSING COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Total cases: {len(cases)}")
    logger.info(f"Updated: {updated_count}")
    logger.info(f"Skipped: {skipped_count}")
    logger.info(f"Errors: {error_count}")
    logger.info(f"Saved to: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Reprocess cases to re-extract metadata from full_text"
    )
    parser.add_argument(
        "--input", "-i",
        default="doha_parsed_cases/all_cases.json",
        help="Input JSON file with cases (default: doha_parsed_cases/all_cases.json)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output JSON file (default: same as input)"
    )
    parser.add_argument(
        "--force-all", "-f",
        action="store_true",
        help="Reprocess all cases, not just those with Unknown values"
    )

    args = parser.parse_args()

    reprocess_cases(
        input_file=args.input,
        output_file=args.output,
        force_all=args.force_all
    )
