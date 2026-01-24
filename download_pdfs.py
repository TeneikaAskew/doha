#!/usr/bin/env python3
"""
Download and parse PDFs from collected links

Uses Playwright browser automation to bypass Akamai bot protection.
Individual PDF URLs are protected and return 403 Forbidden with standard HTTP requests.
"""
import sys
import json
import time
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).parent / "sead4_llm"))

from rag.scraper import DOHAScraper, ScrapedCase
from rag.browser_scraper import DOHABrowserScraper
from loguru import logger
import fitz  # PyMuPDF

# Optional progress bar
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# Parquet support
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    logger.warning("pandas not installed - parquet output will be skipped. Install with: pip install pandas pyarrow")

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


def download_and_parse_pdfs(
    links_file: Path,
    output_dir: Path,
    max_cases: int = None,
    force: bool = False,
    rate_limit: float = 0.15,
    case_type: str = "both"
):
    """Download PDFs using browser automation and parse them

    Args:
        links_file: Path to JSON file with case links
        output_dir: Output directory for parsed cases and PDFs
        max_cases: Maximum number of cases to download (for testing)
        force: Force re-download even if PDFs exist
        rate_limit: Seconds to wait between requests (default: 0.15, currently unused by PDF downloads)
        case_type: Which case types to download - 'hearings', 'appeals', or 'both' (default)
    """

    # Load links
    with open(links_file) as f:
        all_links = json.load(f)

    logger.info(f"Loaded {len(all_links)} case links")

    # Filter by case type if specified
    if case_type != "both":
        # Map plural CLI argument to singular data format
        case_type_singular = case_type.rstrip('s')  # "appeals" -> "appeal", "hearings" -> "hearing"

        original_count = len(all_links)
        all_links = [
            link for link in all_links
            if (len(link) == 4 and link[0] == case_type_singular) or
               (len(link) == 3 and case_type == "hearings")  # Old format assumes hearings
        ]
        logger.info(f"Filtered to {len(all_links)} {case_type} (excluded {original_count - len(all_links)})")

    if max_cases:
        all_links = all_links[:max_cases]
        logger.info(f"Limited to {max_cases} cases")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Create separate PDF directories for hearings and appeals
    hearing_pdf_dir = output_dir / "hearing_pdfs"
    appeal_pdf_dir = output_dir / "appeal_pdfs"
    hearing_pdf_dir.mkdir(exist_ok=True)
    appeal_pdf_dir.mkdir(exist_ok=True)

    # Load existing parsed cases (for resume support)
    processed_cases = set()
    existing_cases = []
    scraper = DOHAScraper(output_dir=output_dir)

    if (output_dir / "all_cases.json").exists() and not force:
        try:
            with open(output_dir / "all_cases.json") as f:
                existing_cases = json.load(f)
                processed_cases = {c["case_number"] for c in existing_cases}
            logger.info(f"Found {len(processed_cases)} already processed cases")

            # Check for cases with UNKNOWN outcome - warn user to run reprocess script
            unknown_count = sum(1 for c in existing_cases if c.get('outcome') in ('UNKNOWN', 'Unknown', None, ''))
            if unknown_count > 0:
                logger.warning(f"Found {unknown_count} cases with UNKNOWN outcome. Run 'python reprocess_cases.py' to fix.")
        except Exception as e:
            logger.warning(f"Could not load existing cases: {e}")

    # Filter links to only unprocessed cases
    links_to_process = []
    for link in all_links:
        # Handle both old format (year, case_number, url) and new format (case_type, year, case_number, url)
        if len(link) == 3:
            # Old format - assume hearing type
            year, case_number, url = link
            link_case_type = "hearing"
            link = (link_case_type, year, case_number, url)  # Convert to new format
        else:
            link_case_type, year, case_number, url = link

        # Choose PDF directory based on case type
        pdf_dir = hearing_pdf_dir if link_case_type == "hearing" else appeal_pdf_dir
        pdf_path = pdf_dir / f"{case_number}.pdf"

        if force or (case_number not in processed_cases or not pdf_path.exists()):
            links_to_process.append(link)

    logger.info(f"Will process {len(links_to_process)} cases (skipped {len(all_links) - len(links_to_process)})")

    if not links_to_process:
        logger.success("All cases already processed!")
        return existing_cases

    # Download with browser - restart browser every 5000 cases to prevent memory buildup
    cases = []
    failed = []
    browser_restart_interval = 5000  # Restart browser every N cases to clear memory

    # Process in batches to restart browser periodically
    total_processed = 0

    iterator = enumerate(links_to_process, 1)
    if HAS_TQDM:
        iterator = tqdm(iterator, total=len(links_to_process), desc="Downloading PDFs", unit="case")

    # Create browser context for first batch
    browser_scraper = DOHABrowserScraper(
        output_dir=output_dir,
        rate_limit=rate_limit,
        headless=True
    )
    browser_scraper.start_browser()

    try:
        for i, (case_type, year, case_number, url) in iterator:
            # Restart browser every N cases to prevent memory buildup
            if total_processed > 0 and total_processed % browser_restart_interval == 0:
                logger.info(f"  Restarting browser after {browser_restart_interval} cases to clear memory...")
                browser_scraper.stop_browser()
                time.sleep(1)  # Brief pause before restart
                browser_scraper.start_browser()
            # Choose PDF directory based on case type
            pdf_dir = hearing_pdf_dir if case_type == "hearing" else appeal_pdf_dir
            pdf_path = pdf_dir / f"{case_number}.pdf"

            try:
                # Download PDF through browser
                pdf_bytes = browser_scraper.download_case_pdf_bytes(url)

                if pdf_bytes is None:
                    logger.error(f"[{i}/{len(links_to_process)}] ✗ [{case_type}] {case_number}: Failed to download")
                    failed.append({
                        "error": "Failed to download (no bytes returned)",
                        "case_type": case_type,
                        "case_number": case_number,
                        "url": url
                    })
                    total_processed += 1
                    continue

                # Save PDF
                pdf_path.write_bytes(pdf_bytes)

                # Parse PDF
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                text_parts = []
                for page in doc:
                    text_parts.append(page.get_text())
                doc.close()

                full_text = "\n".join(text_parts)

                # Clear large objects to help with memory
                del pdf_bytes
                del text_parts

                # Parse case text
                case = scraper.parse_case_text(case_number, full_text, url)
                # Add case_type to the case metadata
                if hasattr(case, '__dict__'):
                    case.case_type = case_type
                elif isinstance(case, dict):
                    case['case_type'] = case_type
                cases.append(case)

                outcome = case.outcome if hasattr(case, 'outcome') else case.get('outcome', 'Unknown')
                logger.success(f"[{i}/{len(links_to_process)}] ✓ [{case_type}] {case_number}: {outcome}")

                total_processed += 1

                # Save checkpoint every 50 cases - only save the last 50 cases, not cumulative
                if i % 50 == 0:
                    # Get only the last 50 cases for this checkpoint
                    checkpoint_cases = cases[-50:]
                    checkpoint_cases_dicts = [
                        c.to_dict() if hasattr(c, 'to_dict') else c
                        for c in checkpoint_cases
                    ]

                    # Determine checkpoint type based on majority of cases in batch
                    batch_types = [c.get('case_type', 'hearing') if isinstance(c, dict) else getattr(c, 'case_type', 'hearing') for c in checkpoint_cases]
                    checkpoint_type = max(set(batch_types), key=batch_types.count) if batch_types else 'hearing'

                    # Use type-specific checkpoint naming
                    checkpoint_file = output_dir / f"checkpoint_{checkpoint_type}_{i}.json"

                    try:
                        with open(checkpoint_file, 'w') as f:
                            json.dump(checkpoint_cases_dicts, f, indent=2)
                        logger.info(f"  Checkpoint saved: {checkpoint_file} ({len(checkpoint_cases_dicts)} cases)")
                    except Exception as e:
                        logger.error(f"  Failed to save checkpoint: {e}")

            except Exception as e:
                logger.error(f"[{i}/{len(links_to_process)}] ✗ [{case_type}] {case_number}: {str(e)}")
                failed.append({
                    "error": f"Parse error: {str(e)}",
                    "case_type": case_type,
                    "case_number": case_number,
                    "url": url
                })
                total_processed += 1  # Count failed attempts too

    finally:
        # Always stop the browser
        browser_scraper.stop_browser()

    # Merge new cases with existing
    all_parsed_cases = existing_cases + [
        c.to_dict() if hasattr(c, 'to_dict') else c
        for c in cases
    ]

    # Save final results
    final_file = output_dir / "all_cases.json"
    with open(final_file, 'w') as f:
        json.dump(all_parsed_cases, f, indent=2)

    json_size_mb = final_file.stat().st_size / (1024 * 1024)
    logger.info(f"Saved JSON: {final_file} ({json_size_mb:.1f}MB)")

    if json_size_mb > 90:
        logger.warning(f"⚠️  JSON file is {json_size_mb:.1f}MB - too large for GitHub (<100MB limit)")
        logger.warning(f"⚠️  Parquet files will be used for version control")

    # Save as parquet (mandatory for GitHub compatibility)
    if HAS_PANDAS:
        parquet_file = output_dir / "all_cases.parquet"
        df = pd.DataFrame(all_parsed_cases)
        parquet_files = save_parquet_with_size_limit(df, parquet_file, max_size_mb=MAX_PARQUET_SIZE_MB)
        logger.info(f"Created {len(parquet_files)} parquet file(s) for Git-friendly storage")
    else:
        logger.error("❌ pandas/pyarrow not installed - cannot create parquet files!")
        logger.error("   Install with: pip install pandas pyarrow")
        logger.error("   Parquet files are REQUIRED to avoid GitHub 100MB file size limit")

    failed_file = output_dir / "failed_cases.json"
    with open(failed_file, 'w') as f:
        json.dump(failed, f, indent=2)

    # Calculate statistics
    from collections import Counter
    new_case_types = Counter()
    all_case_types = Counter()

    for case in cases:
        case_type = case.case_type if hasattr(case, 'case_type') else case.get('case_type', 'unknown')
        new_case_types[case_type] += 1

    for case in all_parsed_cases:
        case_type = case.get('case_type', 'unknown')
        all_case_types[case_type] += 1

    logger.info(f"\n{'='*80}")
    logger.success(f"DOWNLOAD COMPLETE!")
    logger.info(f"{'='*80}")
    logger.info(f"Successfully parsed: {len(cases)} new cases")
    for case_type, count in sorted(new_case_types.items()):
        logger.info(f"  - {case_type}: {count}")

    logger.info(f"\nTotal cases in index: {len(all_parsed_cases)} cases")
    for case_type, count in sorted(all_case_types.items()):
        logger.info(f"  - {case_type}: {count}")

    logger.info(f"\nFailed: {len(failed)} cases")
    logger.info(f"Results saved to: {final_file}")
    logger.info(f"PDFs organized in:")
    logger.info(f"  - Hearings: {hearing_pdf_dir}")
    logger.info(f"  - Appeals: {appeal_pdf_dir}")
    if failed:
        logger.info(f"Failed cases logged to: {failed_file}")

    return all_parsed_cases


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Download and parse DOHA case PDFs using browser automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python download_pdfs.py                         # Download all cases (hearings + appeals)
  python download_pdfs.py --case-type appeals     # Download only appeals
  python download_pdfs.py --case-type hearings    # Download only hearings
  python download_pdfs.py --max-cases 10          # Test with 10 cases

Output:
  Creates both all_cases.json (local use) and all_cases.parquet (Git-friendly <90MB)
  Build index with: python sead4_llm/build_index.py --from-json doha_parsed_cases/all_cases.json
        """
    )
    parser.add_argument("--links", default="./doha_full_scrape/all_case_links.json",
                       help="Path to links JSON file")
    parser.add_argument("--output", default="./doha_parsed_cases",
                       help="Output directory for parsed cases")
    parser.add_argument("--case-type", choices=["hearings", "appeals", "both"], default="both",
                       help="Type of cases to download (default: both)")
    parser.add_argument("--max-cases", type=int,
                       help="Maximum number of cases to download (for testing)")
    parser.add_argument("--force", action="store_true",
                       help="Force re-download even if PDFs exist")
    parser.add_argument("--rate-limit", type=float, default=0.15,
                       help="Seconds to wait between requests (default: 0.15 for ~6 cases/sec)")

    args = parser.parse_args()

    links_file = Path(args.links)

    if not links_file.exists():
        logger.error(f"Links file not found: {links_file}")
        logger.info("Run 'python run_full_scrape.py' first to collect links")
        sys.exit(1)

    cases = download_and_parse_pdfs(
        links_file=links_file,
        output_dir=Path(args.output),
        max_cases=args.max_cases,
        force=args.force,
        rate_limit=args.rate_limit,
        case_type=args.case_type
    )

    logger.info(f"\nNext step: Build index from parsed cases")
    logger.info(f"Run: python sead4_llm/build_index.py --from-json {args.output}/all_cases.json --output ./doha_index")
    logger.info(f"\nNote: Index builder prefers Parquet (most consistent), falls back to JSON if needed")
