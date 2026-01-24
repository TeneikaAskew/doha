#!/usr/bin/env python3
"""
Download and parse DOE OHA case PDFs

Uses Playwright browser automation to download PDFs from energy.gov.
The PDFs are then parsed with PyMuPDF to extract text content.
"""
import sys
import json
import time
import re
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent / "sead4_llm"))

from rag.doe_scraper import DOEBrowserScraper, DOECase
from loguru import logger

# PDF parsing
try:
    import fitz  # PyMuPDF
    HAS_PDF = True
except ImportError:
    HAS_PDF = False
    logger.warning("PyMuPDF not installed. Install with: pip install pymupdf")

# Optional progress bar
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


def download_and_parse_doe_pdfs(
    links_file: Path,
    output_dir: Path,
    max_cases: int = None,
    force: bool = False,
    rate_limit: float = 2.0,
    skip_pdf_fetch: bool = False
):
    """
    Download DOE OHA PDFs and parse them

    Args:
        links_file: Path to JSON file with case links
        output_dir: Output directory for parsed cases and PDFs
        max_cases: Maximum number of cases to download (for testing)
        force: Force re-download even if PDFs exist
        rate_limit: Seconds to wait between requests
        skip_pdf_fetch: If True and PDF URL is missing, skip (don't try to fetch from article)
    """
    if not HAS_PDF:
        logger.error("PyMuPDF required for PDF parsing. Install with: pip install pymupdf")
        sys.exit(1)

    # Load links
    with open(links_file) as f:
        all_links = json.load(f)

    logger.info(f"Loaded {len(all_links)} case links")

    if max_cases:
        all_links = all_links[:max_cases]
        logger.info(f"Limited to {max_cases} cases")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create PDF directory
    pdf_dir = output_dir / "pdfs"
    pdf_dir.mkdir(exist_ok=True)

    # Load existing parsed cases (for resume support)
    processed_cases = set()
    existing_cases = []

    if (output_dir / "all_cases.json").exists() and not force:
        try:
            with open(output_dir / "all_cases.json") as f:
                existing_cases = json.load(f)
                processed_cases = {c["case_number"] for c in existing_cases}
            logger.info(f"Found {len(processed_cases)} already processed cases")
        except Exception as e:
            logger.warning(f"Could not load existing cases: {e}")

    # Filter links to only unprocessed cases
    links_to_process = []
    for link in all_links:
        case_number = link.get('case_number', '')
        pdf_path = pdf_dir / f"{case_number}.pdf"

        if force or (case_number not in processed_cases or not pdf_path.exists()):
            links_to_process.append(link)

    logger.info(f"Will process {len(links_to_process)} cases (skipped {len(all_links) - len(links_to_process)})")

    if not links_to_process:
        logger.success("All cases already processed!")
        return existing_cases

    # Download and parse
    cases = []
    failed = []

    with DOEBrowserScraper(
        output_dir=output_dir,
        rate_limit=rate_limit,
        headless=True
    ) as scraper:

        iterator = enumerate(links_to_process, 1)
        if HAS_TQDM:
            iterator = tqdm(iterator, total=len(links_to_process), desc="Downloading PDFs", unit="case")

        for i, link in iterator:
            case_number = link.get('case_number', f'unknown-{i}')
            pdf_url = link.get('pdf_url', '')
            article_url = link.get('article_url', '')
            summary = link.get('summary', '')
            date = link.get('date', '')

            pdf_path = pdf_dir / f"{case_number}.pdf"

            try:
                # Get PDF URL if not already present
                if not pdf_url and not skip_pdf_fetch:
                    if article_url:
                        logger.debug(f"Fetching PDF URL from article page for {case_number}")
                        pdf_url = scraper.get_pdf_url_from_article(article_url)

                if not pdf_url:
                    logger.warning(f"[{i}/{len(links_to_process)}] {case_number}: No PDF URL available")
                    failed.append({
                        "error": "No PDF URL",
                        "case_number": case_number,
                        "article_url": article_url
                    })
                    continue

                # Download PDF
                logger.debug(f"Downloading PDF from {pdf_url}")
                pdf_bytes = scraper.download_pdf_bytes(pdf_url)

                if pdf_bytes is None:
                    logger.error(f"[{i}/{len(links_to_process)}] {case_number}: Failed to download PDF")
                    failed.append({
                        "error": "Failed to download (no bytes returned)",
                        "case_number": case_number,
                        "pdf_url": pdf_url
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
                case = scraper.parse_case_text(
                    case_number=case_number,
                    text=full_text,
                    source_url=article_url,
                    pdf_url=pdf_url
                )

                # Add metadata from listing page
                if summary and not case.guidelines:
                    # Extract guidelines from summary like "G: Alcohol Consumption"
                    guidelines = extract_guidelines_from_summary(summary)
                    if guidelines:
                        case.guidelines = guidelines

                if date and case.date == "Unknown":
                    case.date = date

                cases.append(case)

                outcome = case.outcome
                logger.success(f"[{i}/{len(links_to_process)}] {case_number}: {outcome}")

                # Save checkpoint every 50 cases
                if i % 50 == 0:
                    save_checkpoint(output_dir, existing_cases, cases, i)

            except Exception as e:
                logger.error(f"[{i}/{len(links_to_process)}] {case_number}: {str(e)}")
                failed.append({
                    "error": f"Parse error: {str(e)}",
                    "case_number": case_number,
                    "pdf_url": pdf_url
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
    print_statistics(cases, all_parsed_cases, failed, output_dir, pdf_dir)

    return all_parsed_cases


def extract_guidelines_from_summary(summary: str) -> List[str]:
    """
    Extract guideline letters from summary text like "G: Alcohol Consumption; I: Psychological Conditions"
    """
    guidelines = []

    # Pattern to match guideline letters followed by colon
    # e.g., "G: Alcohol Consumption" -> "G"
    matches = re.findall(r'\b([A-M]):\s*\w+', summary)
    for match in matches:
        if match not in guidelines:
            guidelines.append(match)

    return guidelines


def save_checkpoint(output_dir: Path, existing_cases: List, new_cases: List, checkpoint_num: int):
    """Save checkpoint file"""
    checkpoint_file = output_dir / f"checkpoint_{checkpoint_num}.json"
    all_parsed = existing_cases + [
        c.to_dict() if hasattr(c, 'to_dict') else c
        for c in new_cases
    ]
    try:
        with open(checkpoint_file, 'w') as f:
            json.dump(all_parsed, f, indent=2)
        logger.info(f"  Checkpoint saved: {checkpoint_file}")
    except Exception as e:
        logger.error(f"  Failed to save checkpoint: {e}")


def print_statistics(new_cases, all_cases, failed, output_dir, pdf_dir):
    """Print final statistics"""
    from collections import Counter

    logger.info(f"\n{'='*80}")
    logger.success(f"DOE OHA PDF DOWNLOAD COMPLETE!")
    logger.info(f"{'='*80}")
    logger.info(f"Successfully parsed: {len(new_cases)} new cases")

    # Count by outcome
    outcome_counts = Counter()
    for case in new_cases:
        outcome = case.outcome if hasattr(case, 'outcome') else case.get('outcome', 'UNKNOWN')
        outcome_counts[outcome] += 1

    logger.info(f"\nNew cases by outcome:")
    for outcome, count in sorted(outcome_counts.items()):
        logger.info(f"  - {outcome}: {count}")

    # Count by year
    year_counts = Counter()
    for case in new_cases:
        case_num = case.case_number if hasattr(case, 'case_number') else case.get('case_number', '')
        year_match = re.search(r'PSH-(\d{2})-', case_num)
        if year_match:
            year = int(year_match.group(1))
            year = year + 2000 if year < 50 else year + 1900
            year_counts[year] += 1

    if year_counts:
        logger.info(f"\nNew cases by year:")
        for year in sorted(year_counts.keys(), reverse=True):
            logger.info(f"  - {year}: {year_counts[year]}")

    logger.info(f"\nTotal cases in index: {len(all_cases)}")
    logger.info(f"Failed: {len(failed)} cases")
    logger.info(f"\nResults saved to: {output_dir / 'all_cases.json'}")
    logger.info(f"PDFs saved to: {pdf_dir}")

    if failed:
        logger.info(f"Failed cases logged to: {output_dir / 'failed_cases.json'}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Download and parse DOE OHA case PDFs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python download_doe_pdfs.py                                    # Download all cases
  python download_doe_pdfs.py --max-cases 10                     # Test with 10 cases
  python download_doe_pdfs.py --links ./my_links.json            # Use custom links file
  python download_doe_pdfs.py --force                            # Re-download all
        """
    )
    parser.add_argument(
        "--links",
        default="./doe_full_scrape/all_case_links.json",
        help="Path to links JSON file"
    )
    parser.add_argument(
        "--output",
        default="./doe_parsed_cases",
        help="Output directory for parsed cases"
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        help="Maximum number of cases to download (for testing)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if PDFs exist"
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=2.0,
        help="Seconds to wait between requests (default: 2.0)"
    )
    parser.add_argument(
        "--skip-pdf-fetch",
        action="store_true",
        help="Skip cases without PDF URL (don't try to fetch from article page)"
    )

    args = parser.parse_args()

    links_file = Path(args.links)

    if not links_file.exists():
        logger.error(f"Links file not found: {links_file}")
        logger.info("Run 'python run_doe_scrape.py' first to collect links")
        sys.exit(1)

    cases = download_and_parse_doe_pdfs(
        links_file=links_file,
        output_dir=Path(args.output),
        max_cases=args.max_cases,
        force=args.force,
        rate_limit=args.rate_limit,
        skip_pdf_fetch=args.skip_pdf_fetch
    )

    logger.info(f"\nNext step: Build index from parsed cases")
    logger.info(f"Run: python sead4_llm/build_index.py --from-json {args.output}/all_cases.json --output ./doe_index")
