#!/usr/bin/env python3
"""
Full DOHA scrape - gets links with browser, downloads PDFs directly
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "sead4_llm"))

from rag.browser_scraper import DOHABrowserScraper
from loguru import logger
import requests
import time

def run_full_scrape():
    """Run comprehensive scrape of all DOHA cases"""
    from datetime import datetime

    output_dir = Path("./doha_full_scrape")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Years to scrape - automatically include current year + 1 (for early postings)
    current_year = datetime.now().year
    years = list(range(2019, current_year + 2))  # 2019 through current year + 1
    archived_years = [2017, 2018]

    all_links = []

    logger.info(f"Starting comprehensive DOHA scrape...")
    logger.info(f"Current year: {current_year}")
    logger.info(f"Will scrape years: {years + archived_years}")

    with DOHABrowserScraper(
        output_dir=output_dir,
        rate_limit=3.0,
        headless=True
    ) as scraper:
        # Scrape current years
        for year in years:
            logger.info(f"\n{'='*60}")
            logger.info(f"Scraping year {year}")
            logger.info(f"{'='*60}")

            # Check if already scraped
            links_file = output_dir / f"links_{year}.json"
            if links_file.exists():
                logger.info(f"⏭️  Year {year} already scraped, loading from {links_file}")
                try:
                    with open(links_file) as f:
                        existing_links = json.load(f)
                    all_links.extend(existing_links)
                    logger.success(f"Loaded {len(existing_links)} cases for {year}")
                    continue
                except Exception as e:
                    logger.warning(f"Failed to load existing links, will re-scrape: {e}")

            try:
                links = scraper.get_case_links(year, is_archived=False)
                logger.success(f"Found {len(links)} cases for {year}")
                year_links = [(year, case_num, url) for case_num, url in links]
                all_links.extend(year_links)

                # Save intermediate results
                with open(links_file, 'w') as f:
                    json.dump(year_links, f, indent=2)

            except Exception as e:
                logger.error(f"Error scraping {year}: {e}")

        # Scrape archived years
        for year in archived_years:
            logger.info(f"\n{'='*60}")
            logger.info(f"Scraping ARCHIVED year {year}")
            logger.info(f"{'='*60}")

            # Check if already scraped
            links_file = output_dir / f"links_{year}.json"
            if links_file.exists():
                logger.info(f"⏭️  Year {year} already scraped, loading from {links_file}")
                try:
                    with open(links_file) as f:
                        existing_links = json.load(f)
                    all_links.extend(existing_links)
                    logger.success(f"Loaded {len(existing_links)} cases for {year}")
                    continue
                except Exception as e:
                    logger.warning(f"Failed to load existing links, will re-scrape: {e}")

            try:
                links = scraper.get_case_links(year, is_archived=True)
                logger.success(f"Found {len(links)} cases for {year}")
                year_links = [(year, case_num, url) for case_num, url in links]
                all_links.extend(year_links)

                # Save intermediate results
                with open(links_file, 'w') as f:
                    json.dump(year_links, f, indent=2)

            except Exception as e:
                logger.error(f"Error scraping archived {year}: {e}")

        # Scrape 2016 and prior
        logger.info(f"\n{'='*60}")
        logger.info(f"Scraping 2016 and Prior (17 pages)")
        logger.info(f"{'='*60}")

        # Check if already scraped
        prior_links_file = output_dir / "links_2016.json"
        if prior_links_file.exists():
            logger.info(f"⏭️  2016 and Prior already scraped, loading from {prior_links_file}")
            try:
                with open(prior_links_file) as f:
                    existing_links = json.load(f)
                all_links.extend(existing_links)
                logger.success(f"Loaded {len(existing_links)} pre-2017 cases")
            except Exception as e:
                logger.warning(f"Failed to load existing links, will re-scrape: {e}")
        else:
            try:
                prior_links = scraper.get_2016_and_prior_links()
                logger.success(f"Found {len(prior_links)} pre-2017 cases")
                prior_year_links = [(2016, case_num, url) for case_num, url in prior_links]
                all_links.extend(prior_year_links)

                # Save results
                with open(prior_links_file, 'w') as f:
                    json.dump(prior_year_links, f, indent=2)

            except Exception as e:
                logger.error(f"Error scraping 2016 and prior: {e}")

    # Save all links
    all_links_file = output_dir / "all_case_links.json"
    with open(all_links_file, 'w') as f:
        json.dump(all_links, f, indent=2)

    logger.info(f"\n{'='*60}")
    logger.success(f"LINK COLLECTION COMPLETE!")
    logger.info(f"{'='*60}")
    logger.info(f"Total cases found: {len(all_links)}")
    logger.info(f"Links saved to: {all_links_file}")

    # Print summary by year
    from collections import Counter
    year_counts = Counter(y for y, _, _ in all_links)
    logger.info("\nCases by year:")
    for year in sorted(year_counts.keys()):
        logger.info(f"  {year}: {year_counts[year]} cases")

    return all_links

if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("DOHA FULL SCRAPE - LINK COLLECTION")
    logger.info("=" * 80)

    links = run_full_scrape()

    logger.info(f"\n{'='*80}")
    logger.info(f"Scrape complete! Found {len(links)} total cases")
    logger.info(f"{'='*80}")
    logger.info("\nNext step: Download PDFs using the collected links")
    logger.info("Run: python download_pdfs.py")
