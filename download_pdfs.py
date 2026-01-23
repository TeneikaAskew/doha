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
    rate_limit: float = 2.0
):
    """Download PDFs using browser automation and parse them

    Args:
        links_file: Path to JSON file with case links
        output_dir: Output directory for parsed cases and PDFs
        max_cases: Maximum number of cases to download (for testing)
        force: Force re-download even if PDFs exist
        rate_limit: Seconds to wait between requests (default: 2.0)
    """

    # Load links
    with open(links_file) as f:
        all_links = json.load(f)

    logger.info(f"Loaded {len(all_links)} case links")

    if max_cases:
        all_links = all_links[:max_cases]
        logger.info(f"Limited to {max_cases} cases")

    output_dir.mkdir(parents=True, exist_ok=True)
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
        year, case_number, url = link
        pdf_path = pdf_dir / f"{case_number}.pdf"

        if force or (case_number not in processed_cases or not pdf_path.exists()):
            links_to_process.append(link)
        else:
            logger.debug(f"Skipping already processed: {case_number}")

    logger.info(f"Will process {len(links_to_process)} cases (skipped {len(all_links) - len(links_to_process)})")

    if not links_to_process:
        logger.success("All cases already processed!")
        return existing_cases

    # Download with browser
    cases = []
    failed = []
    scraper = DOHAScraper(output_dir=output_dir)

    with DOHABrowserScraper(
        output_dir=output_dir,
        rate_limit=rate_limit,
        headless=True
    ) as browser_scraper:

        iterator = enumerate(links_to_process, 1)
        if HAS_TQDM:
            iterator = tqdm(iterator, total=len(links_to_process), desc="Downloading PDFs", unit="case")

        for i, (year, case_number, url) in iterator:
            pdf_path = pdf_dir / f"{case_number}.pdf"

            try:
                # Download PDF through browser
                pdf_bytes = browser_scraper.download_case_pdf_bytes(url)

                if pdf_bytes is None:
                    logger.error(f"[{i}/{len(links_to_process)}] ✗ {case_number}: Failed to download")
                    failed.append({
                        "error": "Failed to download (no bytes returned)",
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
                cases.append(case)

                logger.success(f"[{i}/{len(links_to_process)}] ✓ {case_number}: {case.outcome}")

                # Save checkpoint every 50 cases
                if i % 50 == 0:
                    checkpoint_file = output_dir / f"checkpoint_{i}.json"
                    all_parsed = existing_cases + [
                        c.to_dict() if hasattr(c, 'to_dict') else c
                        for c in cases
                    ]
                    try:
                        with open(checkpoint_file, 'w') as f:
                            json.dump(all_parsed, f, indent=2)
                        logger.info(f"  Checkpoint saved: {checkpoint_file}")
                    except Exception as e:
                        logger.error(f"  Failed to save checkpoint: {e}")

            except Exception as e:
                logger.error(f"[{i}/{len(links_to_process)}] ✗ {case_number}: {str(e)}")
                failed.append({
                    "error": f"Parse error: {str(e)}",
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

    logger.info(f"\n{'='*80}")
    logger.success(f"DOWNLOAD COMPLETE!")
    logger.info(f"{'='*80}")
    logger.info(f"Successfully parsed: {len(cases)} new cases")
    logger.info(f"Total cases in index: {len(all_parsed_cases)} cases")
    logger.info(f"Failed: {len(failed)} cases")
    logger.info(f"Results saved to: {final_file}")
    if failed:
        logger.info(f"Failed cases logged to: {failed_file}")

    return all_parsed_cases


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download and parse DOHA case PDFs using browser automation")
    parser.add_argument("--links", default="./doha_full_scrape/all_case_links.json",
                       help="Path to links JSON file")
    parser.add_argument("--output", default="./doha_parsed_cases",
                       help="Output directory for parsed cases")
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
        rate_limit=args.rate_limit
    )

    logger.info(f"\nNext step: Build index from parsed cases")
    logger.info(f"Run: python sead4_llm/build_index.py --from-json {args.output}/all_cases.json --output ./doha_index")
