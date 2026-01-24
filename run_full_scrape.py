#!/usr/bin/env python3
"""
Full DOHA scrape - gets links with browser, downloads PDFs directly
"""
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "sead4_llm"))

from rag.browser_scraper import DOHABrowserScraper
from loguru import logger
import requests
import time

def run_full_scrape(case_types='both'):
    """Run comprehensive scrape of DOHA cases

    Args:
        case_types: What to scrape - 'hearings', 'appeals', or 'both' (default)
    """
    from datetime import datetime

    output_dir = Path("./doha_full_scrape")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Path for combined links file
    all_links_file = output_dir / "all_case_links.json"

    def save_all_links():
        """Save combined links file (checkpoint)"""
        with open(all_links_file, 'w') as f:
            json.dump(all_links, f, indent=2)
        logger.debug(f"Checkpoint: saved {len(all_links)} total links")

    # Years to scrape - automatically include current year + 1 (for early postings)
    current_year = datetime.now().year
    years = list(range(2019, current_year + 2))  # 2019 through current year + 1
    archived_years = [2017, 2018]

    all_links = []

    # Determine what to scrape
    scrape_hearings = case_types in ('hearings', 'both')
    scrape_appeals = case_types in ('appeals', 'both')

    case_types_str = case_types.capitalize() if case_types != 'both' else 'Hearings + Appeals'
    logger.info(f"Starting DOHA scrape ({case_types_str})...")
    logger.info(f"Current year: {current_year}")
    logger.info(f"Will scrape years: {years + archived_years}")

    with DOHABrowserScraper(
        output_dir=output_dir,
        rate_limit=3.0,
        headless=True
    ) as scraper:
        # Scrape HEARING current years
        if scrape_hearings:
            for year in years:
                logger.info(f"\n{'='*60}")
                logger.info(f"Scraping HEARINGS for year {year}")
                logger.info(f"{'='*60}")

                # Check if already scraped
                links_file = output_dir / f"hearing_links_{year}.json"
                if links_file.exists():
                    logger.info(f"⏭️  Hearing year {year} already scraped, loading from {links_file}")
                    try:
                        with open(links_file) as f:
                            existing_links = json.load(f)
                        all_links.extend(existing_links)
                        logger.success(f"Loaded {len(existing_links)} hearing cases for {year}")
                        save_all_links()
                        continue
                    except Exception as e:
                        logger.warning(f"Failed to load existing hearing links, will re-scrape: {e}")

                try:
                    links = scraper.get_case_links(year, is_archived=False)
                    logger.success(f"Found {len(links)} hearing cases for {year}")
                    year_links = [("hearing", year, case_num, url) for case_num, url in links]
                    all_links.extend(year_links)

                    # Save intermediate results
                    with open(links_file, 'w') as f:
                        json.dump(year_links, f, indent=2)
                    save_all_links()

                except Exception as e:
                    logger.error(f"Error scraping hearings for {year}: {e}")

        # Scrape APPEAL current years
        if scrape_appeals:
            for year in years:
                logger.info(f"\n{'='*60}")
                logger.info(f"Scraping APPEALS for year {year}")
                logger.info(f"{'='*60}")

                # Check if already scraped
                links_file = output_dir / f"appeal_links_{year}.json"
                if links_file.exists():
                    logger.info(f"⏭️  Appeal year {year} already scraped, loading from {links_file}")
                    try:
                        with open(links_file) as f:
                            existing_links = json.load(f)
                        all_links.extend(existing_links)
                        logger.success(f"Loaded {len(existing_links)} appeal cases for {year}")
                        save_all_links()
                        continue
                    except Exception as e:
                        logger.warning(f"Failed to load existing appeal links, will re-scrape: {e}")

                try:
                    links = scraper.get_appeal_case_links(year, is_archived=False)
                    logger.success(f"Found {len(links)} appeal cases for {year}")
                    year_links = [("appeal", year, case_num, url) for case_num, url in links]
                    all_links.extend(year_links)

                    # Save intermediate results
                    with open(links_file, 'w') as f:
                        json.dump(year_links, f, indent=2)
                    save_all_links()

                except Exception as e:
                    logger.error(f"Error scraping appeals for {year}: {e}")

        # Scrape HEARING archived years
        if scrape_hearings:
            for year in archived_years:
                logger.info(f"\n{'='*60}")
                logger.info(f"Scraping ARCHIVED HEARINGS for year {year}")
                logger.info(f"{'='*60}")

                # Check if already scraped
                links_file = output_dir / f"hearing_links_{year}.json"
                if links_file.exists():
                    logger.info(f"⏭️  Archived hearing year {year} already scraped, loading from {links_file}")
                    try:
                        with open(links_file) as f:
                            existing_links = json.load(f)
                        all_links.extend(existing_links)
                        logger.success(f"Loaded {len(existing_links)} archived hearing cases for {year}")
                        save_all_links()
                        continue
                    except Exception as e:
                        logger.warning(f"Failed to load existing links, will re-scrape: {e}")

                try:
                    links = scraper.get_case_links(year, is_archived=True)
                    logger.success(f"Found {len(links)} archived hearing cases for {year}")
                    year_links = [("hearing", year, case_num, url) for case_num, url in links]
                    all_links.extend(year_links)

                    # Save intermediate results
                    with open(links_file, 'w') as f:
                        json.dump(year_links, f, indent=2)
                    save_all_links()

                except Exception as e:
                    logger.error(f"Error scraping archived hearings for {year}: {e}")

        # Scrape APPEAL archived years
        if scrape_appeals:
            for year in archived_years:
                logger.info(f"\n{'='*60}")
                logger.info(f"Scraping ARCHIVED APPEALS for year {year}")
                logger.info(f"{'='*60}")

                # Check if already scraped
                links_file = output_dir / f"appeal_links_{year}.json"
                if links_file.exists():
                    logger.info(f"⏭️  Archived appeal year {year} already scraped, loading from {links_file}")
                    try:
                        with open(links_file) as f:
                            existing_links = json.load(f)
                        all_links.extend(existing_links)
                        logger.success(f"Loaded {len(existing_links)} archived appeal cases for {year}")
                        save_all_links()
                        continue
                    except Exception as e:
                        logger.warning(f"Failed to load existing links, will re-scrape: {e}")

                try:
                    links = scraper.get_appeal_case_links(year, is_archived=True)
                    logger.success(f"Found {len(links)} archived appeal cases for {year}")
                    year_links = [("appeal", year, case_num, url) for case_num, url in links]
                    all_links.extend(year_links)

                    # Save intermediate results
                    with open(links_file, 'w') as f:
                        json.dump(year_links, f, indent=2)
                    save_all_links()

                except Exception as e:
                    logger.error(f"Error scraping archived appeals for {year}: {e}")

        # Scrape 2016 and prior HEARINGS (17 pages)
        if scrape_hearings:
            logger.info(f"\n{'='*60}")
            logger.info(f"Scraping 2016 and Prior HEARINGS (17 pages)")
            logger.info(f"{'='*60}")

            # Check if already scraped
            prior_links_file = output_dir / "hearing_links_2016.json"
            if prior_links_file.exists():
                logger.info(f"⏭️  2016 and Prior hearings already scraped, loading from {prior_links_file}")
                try:
                    with open(prior_links_file) as f:
                        existing_links = json.load(f)
                    all_links.extend(existing_links)
                    logger.success(f"Loaded {len(existing_links)} pre-2017 hearing cases")
                    save_all_links()
                except Exception as e:
                    logger.warning(f"Failed to load existing links, will re-scrape: {e}")
            else:
                try:
                    prior_links = scraper.get_2016_and_prior_links()
                    logger.success(f"Found {len(prior_links)} pre-2017 hearing cases")
                    prior_year_links = [("hearing", 2016, case_num, url) for case_num, url in prior_links]
                    all_links.extend(prior_year_links)

                    # Save results
                    with open(prior_links_file, 'w') as f:
                        json.dump(prior_year_links, f, indent=2)
                    save_all_links()

                except Exception as e:
                    logger.error(f"Error scraping 2016 and prior: {e}")

    # Save all links (final)
    save_all_links()

    logger.info(f"\n{'='*60}")
    logger.success(f"LINK COLLECTION COMPLETE!")
    logger.info(f"{'='*60}")
    logger.info(f"Total cases found: {len(all_links)}")
    logger.info(f"Links saved to: {all_links_file}")

    # Print summary by case type and year
    from collections import Counter, defaultdict
    type_counts = Counter(case_type for case_type, _, _, _ in all_links)
    year_counts = Counter(year for _, year, _, _ in all_links)
    type_year_counts = defaultdict(lambda: defaultdict(int))
    for case_type, year, _, _ in all_links:
        type_year_counts[case_type][year] += 1

    logger.info("\nCases by type:")
    for case_type in sorted(type_counts.keys()):
        logger.info(f"  {case_type}: {type_counts[case_type]} cases")

    logger.info("\nCases by year:")
    for year in sorted(year_counts.keys()):
        logger.info(f"  {year}: {year_counts[year]} cases")

    logger.info("\nDetailed breakdown:")
    for case_type in sorted(type_year_counts.keys()):
        logger.info(f"\n  {case_type.upper()}:")
        for year in sorted(type_year_counts[case_type].keys()):
            logger.info(f"    {year}: {type_year_counts[case_type][year]} cases")

    return all_links

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape DOHA case links (Hearings and/or Appeals)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_full_scrape.py                    # Scrape both hearings and appeals (default)
  python run_full_scrape.py --case-type hearings   # Scrape only hearings (~30,850 cases)
  python run_full_scrape.py --case-type appeals    # Scrape only appeals (~1,010 cases)
        """
    )
    parser.add_argument(
        "--case-type",
        choices=["hearings", "appeals", "both"],
        default="both",
        help="Type of cases to scrape (default: both)"
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("DOHA FULL SCRAPE - LINK COLLECTION")
    logger.info("=" * 80)

    links = run_full_scrape(case_types=args.case_type)

    logger.info(f"\n{'='*80}")
    logger.info(f"Scrape complete! Found {len(links)} total cases")
    logger.info(f"{'='*80}")
    logger.info("\nNext step: Download PDFs using the collected links")
    logger.info("Run: python download_pdfs.py")
