#!/usr/bin/env python3
"""
DOE OHA Full Scrape - Collects case links from energy.gov security cases

This script scrapes all case links from:
https://www.energy.gov/oha/listings/security-cases

It saves the links to JSON files for later PDF downloading.
"""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent / "sead4_llm"))

from rag.doe_scraper import DOEBrowserScraper, DOESimpleScraper, DOECaseLink
from loguru import logger

# Optional progress bar
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


def run_doe_scrape(
    output_dir: Path = Path("./doe_full_scrape"),
    start_page: int = 0,
    end_page: int = None,
    fetch_pdf_urls: bool = True,
    use_browser: bool = True,
    rate_limit: float = 2.0
):
    """
    Run comprehensive scrape of DOE OHA security cases

    Args:
        output_dir: Directory to save scraped links
        start_page: Starting page number (0-indexed)
        end_page: Ending page number (exclusive), None for all
        fetch_pdf_urls: Whether to fetch PDF URLs from article pages
        use_browser: Use Playwright browser (recommended)
        rate_limit: Seconds between requests
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 80)
    logger.info("DOE OHA SECURITY CASES - LINK COLLECTION")
    logger.info("=" * 80)
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Start page: {start_page}")
    logger.info(f"End page: {end_page if end_page else 'all'}")
    logger.info(f"Fetch PDF URLs: {fetch_pdf_urls}")

    all_links = []

    # Check for existing progress
    progress_file = output_dir / "scrape_progress.json"
    if progress_file.exists():
        try:
            with open(progress_file) as f:
                progress = json.load(f)
            last_page = progress.get('last_completed_page', -1)
            if last_page >= start_page:
                logger.info(f"Resuming from page {last_page + 1} (previously completed up to page {last_page})")
                start_page = last_page + 1

                # Load existing links
                existing_links_file = output_dir / "all_case_links.json"
                if existing_links_file.exists():
                    with open(existing_links_file) as f:
                        existing_data = json.load(f)
                    all_links = [DOECaseLink(**c) for c in existing_data]
                    logger.info(f"Loaded {len(all_links)} existing links")
        except Exception as e:
            logger.warning(f"Could not load progress: {e}")

    if use_browser:
        scraper_class = DOEBrowserScraper
        logger.info("Using Playwright browser scraper")
    else:
        scraper_class = DOESimpleScraper
        logger.info("Using simple HTTP scraper")

    with DOEBrowserScraper(
        output_dir=output_dir,
        rate_limit=rate_limit,
        headless=True
    ) as scraper:
        # Get total pages if not specified
        if end_page is None:
            end_page = scraper.get_total_pages()
            logger.info(f"Total pages to scrape: {end_page}")

        if start_page >= end_page:
            logger.info("All pages already scraped!")
            return [link.to_dict() for link in all_links]

        # Scrape pages
        pages_to_scrape = range(start_page, end_page)
        if HAS_TQDM:
            pages_to_scrape = tqdm(pages_to_scrape, desc="Scraping pages", unit="page")

        for page_num in pages_to_scrape:
            try:
                logger.info(f"\n{'='*60}")
                logger.info(f"Scraping page {page_num + 1}/{end_page}")
                logger.info(f"{'='*60}")

                # Check if page already scraped
                page_links_file = output_dir / f"page_{page_num:04d}_links.json"
                if page_links_file.exists():
                    logger.info(f"Page {page_num} already scraped, loading from cache")
                    try:
                        with open(page_links_file) as f:
                            page_data = json.load(f)
                        page_links = [DOECaseLink(**c) for c in page_data]
                        all_links.extend(page_links)
                        logger.success(f"Loaded {len(page_links)} cases from page {page_num}")
                        continue
                    except Exception as e:
                        logger.warning(f"Failed to load cached page, will re-scrape: {e}")

                # Scrape the page
                cases = scraper.get_case_links_from_page(page_num)

                if fetch_pdf_urls:
                    logger.info(f"Fetching PDF URLs for {len(cases)} cases...")
                    for i, case in enumerate(cases, 1):
                        try:
                            pdf_url = scraper.get_pdf_url_from_article(case.article_url)
                            if pdf_url:
                                case.pdf_url = pdf_url
                                logger.debug(f"  [{i}/{len(cases)}] {case.case_number}: {pdf_url}")
                            else:
                                logger.warning(f"  [{i}/{len(cases)}] {case.case_number}: No PDF found")
                        except Exception as e:
                            logger.error(f"  [{i}/{len(cases)}] {case.case_number}: Error fetching PDF URL: {e}")

                all_links.extend(cases)

                # Save page results
                with open(page_links_file, 'w') as f:
                    json.dump([c.to_dict() for c in cases], f, indent=2)

                # Update progress
                with open(progress_file, 'w') as f:
                    json.dump({
                        'last_completed_page': page_num,
                        'total_pages': end_page,
                        'timestamp': datetime.now().isoformat()
                    }, f, indent=2)

                logger.success(f"Completed page {page_num}: {len(cases)} cases (total: {len(all_links)})")

                # Save checkpoint every 10 pages
                if (page_num + 1) % 10 == 0:
                    checkpoint_file = output_dir / f"checkpoint_page_{page_num}.json"
                    with open(checkpoint_file, 'w') as f:
                        json.dump([c.to_dict() for c in all_links], f, indent=2)
                    logger.info(f"Checkpoint saved: {checkpoint_file}")

            except Exception as e:
                logger.error(f"Error scraping page {page_num}: {e}")
                # Save what we have so far
                with open(output_dir / "all_case_links_partial.json", 'w') as f:
                    json.dump([c.to_dict() for c in all_links], f, indent=2)
                continue

    # Save final results
    all_links_file = output_dir / "all_case_links.json"
    all_links_data = [c.to_dict() for c in all_links]
    with open(all_links_file, 'w') as f:
        json.dump(all_links_data, f, indent=2)

    # Generate summary
    logger.info(f"\n{'='*80}")
    logger.success("DOE OHA LINK COLLECTION COMPLETE!")
    logger.info(f"{'='*80}")
    logger.info(f"Total cases found: {len(all_links)}")
    logger.info(f"Links saved to: {all_links_file}")

    # Print statistics
    cases_with_pdf = sum(1 for c in all_links if c.pdf_url)
    cases_without_pdf = len(all_links) - cases_with_pdf

    logger.info(f"\nStatistics:")
    logger.info(f"  Cases with PDF URL: {cases_with_pdf}")
    logger.info(f"  Cases without PDF URL: {cases_without_pdf}")

    # Group by year (extract from case number like PSH-25-0181)
    from collections import Counter
    year_counts = Counter()
    for link in all_links:
        year_match = re.search(r'PSH-(\d{2})-', link.case_number)
        if year_match:
            year = int(year_match.group(1))
            year = year + 2000 if year < 50 else year + 1900
            year_counts[year] += 1

    if year_counts:
        logger.info(f"\nCases by year:")
        for year in sorted(year_counts.keys(), reverse=True):
            logger.info(f"  {year}: {year_counts[year]} cases")

    return all_links_data


# Import re for the year extraction
import re


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape DOE OHA security case links from energy.gov",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_doe_scrape.py                           # Scrape all pages
  python run_doe_scrape.py --start-page 0 --end-page 10   # Scrape first 10 pages
  python run_doe_scrape.py --no-pdf-urls             # Skip fetching PDF URLs (faster)
  python run_doe_scrape.py --rate-limit 3.0          # Slower scraping (more polite)
        """
    )
    parser.add_argument(
        "--output", "-o",
        default="./doe_full_scrape",
        help="Output directory for scraped links (default: ./doe_full_scrape)"
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=0,
        help="Starting page number (0-indexed, default: 0)"
    )
    parser.add_argument(
        "--end-page",
        type=int,
        default=None,
        help="Ending page number (exclusive, default: all pages)"
    )
    parser.add_argument(
        "--no-pdf-urls",
        action="store_true",
        help="Skip fetching PDF URLs from article pages (faster but requires second pass)"
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=2.0,
        help="Seconds between requests (default: 2.0)"
    )

    args = parser.parse_args()

    links = run_doe_scrape(
        output_dir=Path(args.output),
        start_page=args.start_page,
        end_page=args.end_page,
        fetch_pdf_urls=not args.no_pdf_urls,
        rate_limit=args.rate_limit
    )

    logger.info(f"\nNext step: Download PDFs using the collected links")
    logger.info(f"Run: python download_doe_pdfs.py --links {args.output}/all_case_links.json")
