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


def download_and_parse_pdfs(
    links_file: Path,
    output_dir: Path,
    max_cases: int = None,
    force: bool = False,
    rate_limit: float = 2.0,
    case_type: str = "both"
):
    """Download PDFs using browser automation and parse them

    Args:
        links_file: Path to JSON file with case links
        output_dir: Output directory for parsed cases and PDFs
        max_cases: Maximum number of cases to download (for testing)
        force: Force re-download even if PDFs exist
        rate_limit: Seconds to wait between requests (default: 2.0)
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

    # Download with browser
    cases = []
    failed = []

    with DOHABrowserScraper(
        output_dir=output_dir,
        rate_limit=rate_limit,
        headless=True
    ) as browser_scraper:

        iterator = enumerate(links_to_process, 1)
        if HAS_TQDM:
            iterator = tqdm(iterator, total=len(links_to_process), desc="Downloading PDFs", unit="case")

        for i, (case_type, year, case_number, url) in iterator:
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

                # Save checkpoint every 50 cases
                if i % 50 == 0:
                    checkpoint_file = output_dir / f"checkpoint_{i}.json"
                    all_cases_file = output_dir / "all_cases.json"
                    all_parsed = existing_cases + [
                        c.to_dict() if hasattr(c, 'to_dict') else c
                        for c in cases
                    ]
                    try:
                        with open(checkpoint_file, 'w') as f:
                            json.dump(all_parsed, f, indent=2)
                        with open(all_cases_file, 'w') as f:
                            json.dump(all_parsed, f, indent=2)
                        logger.info(f"  Checkpoint saved: {checkpoint_file} + all_cases.json ({len(all_parsed)} cases)")
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

    # Merge new cases with existing
    all_parsed_cases = existing_cases + [
        c.to_dict() if hasattr(c, 'to_dict') else c
        for c in cases
    ]

    # Save final results
    final_file = output_dir / "all_cases.json"
    with open(final_file, 'w') as f:
        json.dump(all_parsed_cases, f, indent=2)

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
    parser.add_argument("--rate-limit", type=float, default=2.0,
                       help="Seconds to wait between requests (default: 2.0)")

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
