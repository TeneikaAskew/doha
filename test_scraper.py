#!/usr/bin/env python3
"""
Test script to verify DOHA scraper functionality
"""
import sys
from pathlib import Path

# Add sead4_llm to path
sys.path.insert(0, str(Path(__file__).parent / "sead4_llm"))

from rag.scraper import DOHAScraper
from loguru import logger

def test_single_year():
    """Test scraping a single recent year"""
    logger.info("Testing DOHA scraper with year 2024...")

    scraper = DOHAScraper(
        output_dir=Path("./test_doha_scrape"),
        rate_limit=2.0
    )

    # Try to get links for 2024
    logger.info("Attempting to fetch case links for 2024...")
    links = scraper.get_case_links(2024, is_archived=False)

    if links:
        logger.success(f"Successfully found {len(links)} cases for 2024!")
        logger.info(f"First 5 cases: {links[:5]}")

        # Try to scrape just one case
        if len(links) > 0:
            case_num, case_url = links[0]
            logger.info(f"Attempting to scrape sample case: {case_num} from {case_url}")
            try:
                case = scraper.scrape_case(case_num, case_url)
                if case:
                    logger.success(f"Successfully scraped case!")
                    logger.info(f"  Case Number: {case.case_number}")
                    logger.info(f"  Date: {case.date}")
                    logger.info(f"  Outcome: {case.outcome}")
                    logger.info(f"  Guidelines: {case.guidelines}")
                    logger.info(f"  Judge: {case.judge}")
                    logger.info(f"  Summary: {case.summary[:200]}...")
                    return True
                else:
                    logger.error("Failed to scrape case")
                    return False
            except Exception as e:
                logger.error(f"Error scraping case: {e}")
                return False
    else:
        logger.error("No links found - likely blocked by 403 error")
        logger.info("The DOHA website may be blocking automated access.")
        logger.info("Possible solutions:")
        logger.info("  1. Run from a different network/IP")
        logger.info("  2. Use a VPN")
        logger.info("  3. Manually download files and use DOHALocalParser")
        logger.info("  4. Contact DOHA for bulk data access")
        return False

if __name__ == "__main__":
    success = test_single_year()
    sys.exit(0 if success else 1)
