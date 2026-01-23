#!/usr/bin/env python3
"""
Download and parse PDFs from collected links

⚠️ WARNING: This script does NOT work due to Akamai bot protection!
All PDF downloads return 403 Forbidden errors.

Use download_pdfs_browser.py instead, which bypasses bot protection
using Playwright's browser request context API.

This file is kept for reference showing the parallel download implementation.
"""
import sys
import json
import time
from pathlib import Path
from typing import List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

sys.path.insert(0, str(Path(__file__).parent / "sead4_llm"))

from rag.scraper import DOHAScraper, ScrapedCase
from loguru import logger
import requests
from requests.exceptions import RequestException, Timeout, HTTPError
import fitz  # PyMuPDF

# Optional progress bar
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


def download_single_case(case_info: Tuple, pdf_dir: Path, output_dir: Path):
    """Download and parse a single case (thread-safe)

    Args:
        case_info: Tuple of (year, case_number, url)
        pdf_dir: Directory to save PDFs
        output_dir: Output directory for scraper

    Returns:
        Dict with either {"case": ScrapedCase, "case_number": str} on success
        or {"error": str, "case_number": str, "url": str} on failure
    """
    year, case_number, url = case_info
    max_retries = 3

    # Create thread-local session
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    pdf_path = pdf_dir / f"{case_number}.pdf"
    scraper = DOHAScraper(output_dir=output_dir)

    for attempt in range(max_retries):
        try:
            # Download PDF
            response = session.get(url, timeout=30)
            response.raise_for_status()

            # Save PDF
            pdf_path.write_bytes(response.content)

            # Parse PDF
            doc = fitz.open(stream=response.content, filetype="pdf")
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text())
            doc.close()

            full_text = "\n".join(text_parts)

            # Parse case text
            case = scraper.parse_case_text(case_number, full_text, url)

            return {"case": case, "case_number": case_number}

        except Timeout:
            if attempt < max_retries - 1:
                logger.warning(f"Timeout downloading {case_number}, retry {attempt + 1}/{max_retries}")
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            return {
                "error": f"Timeout after {max_retries} attempts",
                "case_number": case_number,
                "url": url
            }

        except HTTPError as e:
            if e.response.status_code == 404:
                return {
                    "error": "Case not found (404)",
                    "case_number": case_number,
                    "url": url
                }
            elif e.response.status_code == 403:
                return {
                    "error": "Access denied (403)",
                    "case_number": case_number,
                    "url": url
                }
            else:
                if attempt < max_retries - 1:
                    logger.warning(f"HTTP {e.response.status_code} for {case_number}, retry {attempt + 1}/{max_retries}")
                    time.sleep(2 ** attempt)
                    continue
                return {
                    "error": f"HTTP {e.response.status_code}",
                    "case_number": case_number,
                    "url": url
                }

        except RequestException as e:
            if attempt < max_retries - 1:
                logger.warning(f"Network error for {case_number}, retry {attempt + 1}/{max_retries}")
                time.sleep(2 ** attempt)
                continue
            return {
                "error": f"Network error: {str(e)}",
                "case_number": case_number,
                "url": url
            }

        except Exception as e:
            # PDF parsing or other errors - don't retry
            logger.error(f"Parse error for {case_number}: {e}")
            return {
                "error": f"Parse error: {str(e)}",
                "case_number": case_number,
                "url": url
            }

    return {
        "error": "Max retries exceeded",
        "case_number": case_number,
        "url": url
    }


def download_and_parse_pdfs(links_file: Path, output_dir: Path, max_cases: int = None, workers: int = 5, force: bool = False):
    """Download PDFs and parse them with parallel workers and resume support

    Args:
        links_file: Path to JSON file with case links
        output_dir: Output directory for parsed cases and PDFs
        max_cases: Maximum number of cases to download (for testing)
        workers: Number of parallel download workers
        force: Force re-download even if PDFs exist
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

    # Thread-safe result accumulation
    cases = []
    failed = []
    lock = threading.Lock()
    success_count = 0
    fail_count = 0

    # Parallel download with ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as executor:
        # Submit all download jobs
        futures = {
            executor.submit(download_single_case, link, pdf_dir, output_dir): link
            for link in links_to_process
        }

        # Process results as they complete
        iterator = as_completed(futures)
        if HAS_TQDM:
            iterator = tqdm(iterator, total=len(futures), desc="Downloading PDFs", unit="case")

        for future in iterator:
            result = future.result()

            with lock:
                if "error" in result:
                    failed.append(result)
                    fail_count += 1
                    logger.error(
                        f"[{success_count + fail_count}/{len(links_to_process)}] "
                        f"✗ {result['case_number']}: {result['error']}"
                    )
                else:
                    cases.append(result["case"])
                    success_count += 1
                    case = result["case"]
                    logger.success(
                        f"[{success_count + fail_count}/{len(links_to_process)}] "
                        f"✓ {case.case_number}: {case.outcome}"
                    )

                # Save checkpoint every 50 cases
                if (success_count + fail_count) % 50 == 0:
                    checkpoint_file = output_dir / f"checkpoint_{success_count + fail_count}.json"
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

    parser = argparse.ArgumentParser(description="Download and parse DOHA case PDFs")
    parser.add_argument("--links", default="./doha_full_scrape/all_case_links.json",
                       help="Path to links JSON file")
    parser.add_argument("--output", default="./doha_parsed_cases",
                       help="Output directory for parsed cases")
    parser.add_argument("--max-cases", type=int,
                       help="Maximum number of cases to download (for testing)")
    parser.add_argument("--workers", type=int, default=5,
                       help="Number of parallel download workers (default: 5)")
    parser.add_argument("--force", action="store_true",
                       help="Force re-download even if PDFs exist")

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
        workers=args.workers,
        force=args.force
    )

    logger.info(f"\nNext step: Build index from parsed cases")
    logger.info(f"Run: python sead4_llm/build_index.py --from-json {args.output}/all_cases.json --output ./doha_index")
