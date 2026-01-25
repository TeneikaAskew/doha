#!/usr/bin/env python3
"""
Reprocess existing cases to re-extract metadata from full_text.
This updates judge, outcome, guidelines, sections, etc. without re-downloading PDFs.
Also fixes case_number values by extracting from PDF text.
"""
import sys
import json
import argparse
import gc
import os
import re
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "sead4_llm"))

from rag.scraper import DOHAScraper
from loguru import logger

# Parquet support
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

# GitHub file size limit with buffer
MAX_PARQUET_SIZE_MB = 90  # Stay under GitHub's 100MB limit

def is_bad_case_number(case_number: str) -> bool:
    """Check if case_number is missing or invalid.

    Good case numbers: "17-01990", "14-06484", "19-02453" (XX-XXXXX format)
    Bad case numbers: empty, "pre2016-*", "Unknown*", "YYYY-NNNNNN" patterns

    Args:
        case_number: The case number to check

    Returns:
        True if the case number is invalid or missing
    """
    if not case_number:
        return True
    if case_number.startswith('pre2016-'):
        return True
    if case_number.startswith('Unknown'):
        return True
    # Bad patterns: YYYY-NNNNNN (4-digit year + 6-digit number)
    if re.match(r'^\d{4}-\d{6}$', case_number):
        return True
    return False


def extract_case_number_from_text(text: str) -> str:
    """Extract case number from PDF text as fallback.

    Patterns found in DOHA cases:
    - "ISCR Case No. 17-01990"
    - "CAC Case No. 17-01990"
    - "ADP Case No. 17-01990"
    - "Case No. 17-01990"
    - "Case No: 17-01990"

    Args:
        text: Full text from PDF

    Returns:
        Case number like "17-01990" or None if not found
    """
    match = re.search(
        r'(?:ISCR|CAC|ADP)?\s*Case\s*No\.?\s*:?\s*(\d{2}-\d{4,6})',
        text,
        re.IGNORECASE
    )
    return match.group(1) if match else None


def verify_and_fix_case_numbers(
    input_file: str = "doha_parsed_cases/all_cases.json",
    output_file: str = None,
    fix: bool = False,
    report_file: str = None
) -> dict:
    """
    Verify all case numbers by extracting from PDF text.

    This compares EVERY case number (not just "bad" ones) against
    the case number extracted from full_text.

    Args:
        input_file: Path to cases file
        output_file: Path to save fixed cases (only if fix=True)
        fix: If True, fix mismatched case numbers
        report_file: Path to save mismatch report JSON

    Returns:
        Dict with verification stats and mismatches
    """
    input_path = Path(input_file)
    is_parquet = input_path.suffix == '.parquet'

    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return {}

    # Load cases
    logger.info(f"Loading cases from {input_path}")
    if is_parquet:
        if not HAS_PANDAS:
            logger.error("pandas not installed - cannot read parquet files")
            return {}
        df = pd.read_parquet(input_path)
        cases = df.to_dict('records')
    else:
        with open(input_path) as f:
            cases = json.load(f)

    logger.info(f"Loaded {len(cases)} cases")

    # Verification results
    mismatches = []
    no_text_match = []
    fixes_applied = 0

    logger.info("Verifying all case numbers using text extraction...")

    for i, case in enumerate(cases):
        current_case_number = case.get('case_number', '')
        full_text = case.get('full_text', '')

        # Extract case number from text
        text_case_number = extract_case_number_from_text(full_text) if full_text else None

        # Check for mismatch
        if text_case_number and text_case_number != current_case_number:
            mismatch_info = {
                'index': i,
                'current': current_case_number,
                'text_extracted': text_case_number,
                'source_url': case.get('source_url', '')
            }
            mismatches.append(mismatch_info)

            if fix:
                case['case_number'] = text_case_number
                fixes_applied += 1

        # Track cases where text extraction failed
        if not text_case_number and full_text:
            no_text_match.append({
                'index': i,
                'case_number': current_case_number,
                'text_preview': full_text[:200] if full_text else ''
            })

        # Progress logging
        if (i + 1) % 1000 == 0:
            logger.info(f"Verified {i+1}/{len(cases)} cases, {len(mismatches)} mismatches found")

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("CASE NUMBER VERIFICATION COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Total cases: {len(cases)}")
    logger.info(f"Mismatches found: {len(mismatches)}")
    logger.info(f"Text extraction failed: {len(no_text_match)}")

    if fix:
        logger.info(f"Fixes applied: {fixes_applied}")

    # Show sample mismatches
    if mismatches:
        logger.warning(f"\nSample mismatches (first 10):")
        for m in mismatches[:10]:
            logger.warning(f"  [{m['index']}] {m['current']} -> {m['text_extracted']}")

    # Save report
    report = {
        'total_cases': len(cases),
        'mismatches_count': len(mismatches),
        'no_text_match_count': len(no_text_match),
        'fixes_applied': fixes_applied if fix else 0,
        'mismatches': mismatches,
        'no_text_match': no_text_match[:100]  # Limit to first 100
    }

    if report_file:
        report_path = Path(report_file)
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        logger.info(f"Report saved to: {report_path}")

    # Save fixed cases
    if fix and fixes_applied > 0:
        output_path = Path(output_file) if output_file else input_path

        if output_path.suffix == '.parquet':
            df = pd.DataFrame(cases)
            df.to_parquet(output_path, index=False)
            validate_parquet_file(output_path, len(cases), "case number fix")
        else:
            atomic_write_json(cases, output_path)

        logger.success(f"Fixed cases saved to: {output_path}")

    return report


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


def atomic_write_json(data, output_path: Path):
    """Atomically write JSON data to a file (write to temp, then rename).

    This prevents corruption if the process is killed during write.
    """
    output_path = Path(output_path)
    temp_path = output_path.with_suffix('.tmp')

    try:
        with open(temp_path, 'w') as f:
            json.dump(data, f, indent=2)

        # Atomic rename (on same filesystem)
        os.replace(temp_path, output_path)
        logger.debug(f"Atomically saved JSON to {output_path}")

    except Exception as e:
        # Clean up temp file on error
        if temp_path.exists():
            temp_path.unlink()
        raise


def atomic_write_parquet(df: "pd.DataFrame", output_path: Path):
    """Atomically write DataFrame to parquet (write to temp, then rename).

    This prevents corruption if the process is killed during write.
    """
    output_path = Path(output_path)
    temp_path = output_path.with_suffix('.parquet.tmp')

    try:
        df.to_parquet(temp_path, index=False, engine='pyarrow', compression='gzip')

        # Validate before replacing
        validate_parquet_file(temp_path, len(df), "atomic write")

        # Atomic rename (on same filesystem)
        os.replace(temp_path, output_path)
        logger.debug(f"Atomically saved parquet to {output_path}")

    except Exception as e:
        # Clean up temp file on error
        if temp_path.exists():
            temp_path.unlink()
        raise


def save_parquet_with_size_limit(df: "pd.DataFrame", output_path: Path, max_size_mb: float = MAX_PARQUET_SIZE_MB):
    """Save DataFrame to Parquet, splitting into multiple files if needed to stay under size limit.

    Uses atomic writes to prevent corruption if process is killed.

    Args:
        df: DataFrame to save
        output_path: Base path for output (e.g., all_cases.parquet)
        max_size_mb: Maximum file size in MB (default: 90MB to stay under GitHub's 100MB limit)

    Returns:
        List of created file paths
    """
    # First, try saving the whole thing to estimate size
    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        df.to_parquet(tmp_path, index=False, engine='pyarrow', compression='gzip')
        total_size_mb = os.path.getsize(tmp_path) / (1024 * 1024)
    finally:
        os.unlink(tmp_path)

    # If it fits in one file, save atomically
    if total_size_mb <= max_size_mb:
        atomic_write_parquet(df, output_path)
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
        atomic_write_parquet(chunk, chunk_path)
        size_mb = chunk_path.stat().st_size / (1024 * 1024)

        # Verify chunk doesn't exceed size limit
        if size_mb > max_size_mb:
            logger.error(f"❌ Chunk {i} exceeds {max_size_mb}MB: {size_mb:.1f}MB")
            raise ValueError(f"Parquet splitting failed, chunk {i} too large: {size_mb:.1f}MB > {max_size_mb}MB")

        logger.success(f"Saved {len(chunk)} cases to {chunk_path} ({size_mb:.1f}MB)")
        created_files.append(chunk_path)

    return created_files


def is_empty_or_unknown(value):
    """Safely check if a value is empty, None, or Unknown - handles both scalars and pandas arrays"""
    if value is None:
        return True
    if isinstance(value, str):
        return value in ('', 'Unknown', 'UNKNOWN')
    # Handle pandas/numpy arrays and lists
    if hasattr(value, '__len__'):
        try:
            return len(value) == 0
        except (TypeError, AttributeError):
            # TypeError: object has __len__ but it's not implemented properly
            # AttributeError: __len__ exists but raises AttributeError
            return False
    return False


def reprocess_cases(input_file: str, output_file: str = None, force_all: bool = False):
    """
    Reprocess cases to re-extract metadata from existing full_text.

    Args:
        input_file: Path to existing all_cases.json or all_cases.parquet
        output_file: Path to save updated cases (defaults to input_file)
        force_all: If True, reprocess all cases. If False, only reprocess cases with Unknown values.
    """
    input_path = Path(input_file)
    output_path = Path(output_file) if output_file else input_path
    is_parquet = input_path.suffix == '.parquet'

    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return

    # Load existing cases (support both JSON and Parquet)
    logger.info(f"Loading cases from {input_path}")

    if is_parquet:
        if not HAS_PANDAS:
            logger.error("pandas not installed - cannot read parquet files")
            logger.error("Install with: pip install pandas pyarrow")
            return
        df = pd.read_parquet(input_path)
        cases = df.to_dict('records')
        logger.info(f"Loaded {len(cases)} cases from parquet")
    else:
        try:
            with open(input_path) as f:
                cases = json.load(f)

            # Validate structure
            if not isinstance(cases, list):
                logger.error(f"Invalid cases file format: expected list, got {type(cases).__name__}")
                raise ValueError(f"Cases file must contain a list, not {type(cases).__name__}")

            logger.info(f"Loaded {len(cases)} cases from JSON")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load cases from {input_path}: {e}")
            raise

    # Create scraper instance for extraction methods
    scraper = DOHAScraper(output_dir=input_path.parent)

    case_number_fixes = 0
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

        # Check if needs reprocessing (including bad case_number)
        has_bad_case_number = is_bad_case_number(case_number)
        needs_update = force_all or has_bad_case_number or any([
            is_empty_or_unknown(case.get('outcome')),
            is_empty_or_unknown(case.get('judge')),
            is_empty_or_unknown(case.get('guidelines')),
            is_empty_or_unknown(case.get('formal_findings')),
        ])

        if not needs_update:
            skipped_count += 1
            continue

        try:
            changes = []

            # Always verify case_number using text extraction from PDF
            old_case_number = case_number
            new_case_number = extract_case_number_from_text(full_text)

            if new_case_number and new_case_number != old_case_number:
                case['case_number'] = new_case_number
                case_number = new_case_number  # Update for logging
                changes.append(f"case_number: {old_case_number} -> {new_case_number}")
                case_number_fixes += 1

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

            # Track metadata changes (case_number changes already tracked above)
            if old_outcome != new_outcome:
                changes.append(f"outcome: {old_outcome} -> {new_outcome}")
            if old_judge != new_judge:
                changes.append(f"judge: {old_judge} -> {new_judge}")

            if changes:
                logger.success(f"[{i+1}/{len(cases)}] {case_number}: {', '.join(changes)}")
            else:
                logger.info(f"[{i+1}/{len(cases)}] {case_number}: reprocessed (no changes)")

            updated_count += 1

            # Save checkpoint every 5000 cases (using atomic writes to prevent corruption)
            if updated_count % 5000 == 0:
                if is_parquet:
                    df = pd.DataFrame(cases)
                    save_parquet_with_size_limit(df, output_path, max_size_mb=MAX_PARQUET_SIZE_MB)
                    del df  # Explicitly delete DataFrame
                else:
                    atomic_write_json(cases, output_path)
                gc.collect()  # Force garbage collection after checkpoint
                logger.info(f"  Checkpoint saved: {updated_count} cases updated")

        except Exception as e:
            logger.error(f"[{i+1}/{len(cases)}] {case_number}: Error - {e}")
            error_count += 1

    # Save final results (using atomic writes to prevent corruption)
    if is_parquet:
        logger.info(f"Saving to parquet: {output_path}")
        df = pd.DataFrame(cases)
        save_parquet_with_size_limit(df, output_path, max_size_mb=MAX_PARQUET_SIZE_MB)
        del df  # Explicitly delete DataFrame
        gc.collect()  # Force garbage collection
    else:
        logger.info(f"Saving to JSON: {output_path}")
        atomic_write_json(cases, output_path)
        gc.collect()

    logger.info(f"\n{'='*60}")
    logger.success(f"REPROCESSING COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Total cases: {len(cases)}")
    logger.info(f"Updated: {updated_count}")
    logger.info(f"Case numbers fixed: {case_number_fixes}")
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
        help="Input file with cases - JSON or Parquet (default: doha_parsed_cases/all_cases.json)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file (default: same as input, preserves format)"
    )
    parser.add_argument(
        "--force-all", "-f",
        action="store_true",
        help="Reprocess all cases, not just those with Unknown values"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify all case numbers against FileId lookup and text extraction (report only)"
    )
    parser.add_argument(
        "--fix-case-numbers",
        action="store_true",
        help="Verify AND fix all mismatched case numbers"
    )
    parser.add_argument(
        "--report",
        default="doha_parsed_cases/case_number_report.json",
        help="Path to save verification report (default: doha_parsed_cases/case_number_report.json)"
    )

    args = parser.parse_args()

    if args.verify or args.fix_case_numbers:
        # Run verification/fix mode
        verify_and_fix_case_numbers(
            input_file=args.input,
            output_file=args.output,
            fix=args.fix_case_numbers,
            report_file=args.report
        )
    else:
        # Run normal reprocessing
        reprocess_cases(
            input_file=args.input,
            output_file=args.output,
            force_all=args.force_all
        )
