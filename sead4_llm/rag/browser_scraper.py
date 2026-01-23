"""
DOHA Case Browser-Based Scraper

Uses Playwright to scrape DOHA cases with a real browser,
bypassing bot protection that blocks requests-based scraping.
"""
import json
import time
from pathlib import Path
from typing import List, Tuple, Optional
from loguru import logger

try:
    from playwright.sync_api import sync_playwright, Page, Browser
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    logger.warning("playwright not installed. Install with: pip install playwright && playwright install chromium")

from .scraper import DOHAScraper, ScrapedCase


class DOHABrowserScraper(DOHAScraper):
    """
    Browser-based DOHA scraper using Playwright

    This bypasses bot protection by using a real browser instance.
    """

    def __init__(
        self,
        output_dir: Path = Path("./doha_cases"),
        rate_limit: float = 3.0,  # Longer delays for browser-based scraping
        headless: bool = True
    ):
        if not HAS_PLAYWRIGHT:
            raise ImportError("playwright required. Install with: pip install playwright && playwright install chromium")

        # Initialize parent class
        super().__init__(output_dir=output_dir, rate_limit=rate_limit)

        self.headless = headless
        self.playwright = None
        self.browser = None
        self.page = None

    def __enter__(self):
        """Context manager entry"""
        self.start_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop_browser()

    def start_browser(self):
        """Start the Playwright browser"""
        logger.info("Starting browser...")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.page = self.browser.new_page()

        # Set realistic viewport
        self.page.set_viewport_size({"width": 1920, "height": 1080})

        logger.info("Browser started successfully")

    def stop_browser(self):
        """Stop the Playwright browser"""
        if self.page:
            self.page.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        logger.info("Browser stopped")

    def _browser_get(self, url: str) -> str:
        """Get page content using browser"""
        if not self.page:
            raise RuntimeError("Browser not started. Call start_browser() first or use context manager.")

        # Rate limiting
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)

        logger.debug(f"Browser fetching: {url}")

        try:
            # Navigate to page
            response = self.page.goto(url, wait_until="domcontentloaded", timeout=60000)

            self._last_request = time.time()

            if response is None:
                logger.error(f"Failed to load {url}: No response")
                return ""

            # Check status
            status = response.status
            if status == 403:
                logger.warning(f"Got 403 even with browser for {url}")
                # Wait a bit longer and try to get content anyway
                time.sleep(5)

            # Wait a bit for dynamic content
            time.sleep(2)

            # Get HTML content
            content = self.page.content()
            return content

        except Exception as e:
            logger.error(f"Browser error fetching {url}: {e}")
            return ""

    def get_case_links(self, year: int, is_archived: bool = None) -> List[Tuple[str, str]]:
        """
        Get links to case decisions for a given year using browser

        Args:
            year: The year to scrape
            is_archived: Whether to use archived URL pattern (auto-detect if None)

        Returns:
            List of (case_number, url) tuples
        """
        from bs4 import BeautifulSoup
        import re

        # Auto-detect if year should use archive pattern
        if is_archived is None:
            is_archived = year < 2019  # Years 2019-2022 are in main section, 2017-2018 in archive

        # Choose URL pattern based on year
        # Special case for 2024 which has different URL structure
        if year == 2024:
            url = self.DOHA_2024_PATTERN
        elif year >= 2019 and not is_archived:
            url = self.DOHA_YEAR_PATTERN.format(year=year)
        else:
            url = self.DOHA_ARCHIVE_YEAR_PATTERN.format(year=year)

        logger.info(f"Fetching case list for year {year} from {url}")

        html = self._browser_get(url)

        if not html or len(html) < 100:
            logger.error(f"Failed to get content for year {year}")
            return []

        soup = BeautifulSoup(html, 'html.parser')

        links = []
        # Look for FileId links which point to individual cases
        for a in soup.find_all('a', href=True):
            href = a['href']

            # New structure uses /FileId/{number}/ pattern
            if '/FileId/' in href:
                file_id_match = re.search(r'/FileId/(\d+)', href)
                if file_id_match:
                    file_id = file_id_match.group(1)
                    case_number = f"{year}-{file_id}"

                    # Make absolute URL
                    if not href.startswith('http'):
                        if href.startswith('/'):
                            href = 'https://doha.ogc.osd.mil' + href
                        else:
                            href = url + href

                    links.append((case_number, href))

            # Also look for old-style case number patterns as fallback
            elif re.search(r'\d{2}-\d+', href):
                case_match = re.search(r'(\d{2}-\d+)', href)
                if case_match:
                    case_number = case_match.group(1)
                    if not href.startswith('http'):
                        if href.startswith('/'):
                            href = 'https://doha.ogc.osd.mil' + href
                        else:
                            href = url + href
                    links.append((case_number, href))

        # Remove duplicates
        seen = set()
        unique_links = []
        for case_num, case_url in links:
            if case_num not in seen:
                seen.add(case_num)
                unique_links.append((case_num, case_url))

        logger.info(f"Found {len(unique_links)} cases for year {year}")
        return unique_links

    def get_2016_and_prior_links(self) -> List[Tuple[str, str]]:
        """Get links from all "2016 and Prior" pages using browser"""
        from bs4 import BeautifulSoup
        import re

        all_links = []

        for page in range(1, self.DOHA_2016_PRIOR_PAGES + 1):
            url = self.DOHA_2016_PRIOR_PATTERN.format(page=page)
            logger.info(f"Fetching 2016 and Prior page {page}/{self.DOHA_2016_PRIOR_PAGES}...")

            html = self._browser_get(url)

            if not html or len(html) < 100:
                logger.warning(f"Failed to get content for page {page}")
                continue

            soup = BeautifulSoup(html, 'html.parser')

            page_links = []
            for a in soup.find_all('a', href=True):
                href = a['href']

                if '/FileId/' in href:
                    file_id_match = re.search(r'/FileId/(\d+)', href)
                    if file_id_match:
                        file_id = file_id_match.group(1)
                        case_number = f"pre2016-{file_id}"

                        if not href.startswith('http'):
                            if href.startswith('/'):
                                href = 'https://doha.ogc.osd.mil' + href
                            else:
                                href = url + href

                        page_links.append((case_number, href))

                elif re.search(r'\d{2}-\d+', href):
                    case_match = re.search(r'(\d{2}-\d+)', href)
                    if case_match:
                        case_number = case_match.group(1)
                        if not href.startswith('http'):
                            if href.startswith('/'):
                                href = 'https://doha.ogc.osd.mil' + href
                            else:
                                href = url + href
                        page_links.append((case_number, href))

            # Remove duplicates
            seen_on_page = set()
            for case_num, case_url in page_links:
                if case_num not in seen_on_page:
                    seen_on_page.add(case_num)
                    all_links.append((case_num, case_url))

            logger.info(f"Found {len(page_links)} cases on page {page}")

        logger.info(f"Found total of {len(all_links)} cases in 2016 and Prior pages")
        return all_links

    def get_appeal_case_links(self, year: int, is_archived: bool = None) -> List[Tuple[str, str]]:
        """
        Get links to Appeal Board decisions for a given year using browser

        Args:
            year: The year to scrape
            is_archived: Whether to use archived URL pattern (auto-detect if None)

        Returns:
            List of (case_number, url) tuples
        """
        from bs4 import BeautifulSoup
        import re

        # Auto-detect if year should use archive pattern
        if is_archived is None:
            is_archived = year < 2019

        # Choose URL pattern based on year
        # Appeal Board has different URL patterns for different years
        if is_archived:
            url = self.DOHA_APPEAL_ARCHIVE_BASE
        elif year == 2022:
            url = self.DOHA_APPEAL_2022_PATTERN
        elif year == 2021:
            url = self.DOHA_APPEAL_2021_PATTERN
        elif year == 2020:
            url = self.DOHA_APPEAL_2020_PATTERN
        elif year == 2019:
            url = self.DOHA_APPEAL_2019_PATTERN
        else:
            # 2023 and later use the standard pattern
            url = self.DOHA_APPEAL_YEAR_PATTERN.format(year=year)

        logger.info(f"Fetching Appeal Board case list for year {year} from {url}")

        html = self._browser_get(url)

        if not html or len(html) < 100:
            logger.error(f"Failed to get Appeal Board content for year {year}")
            return []

        soup = BeautifulSoup(html, 'html.parser')

        links = []
        # Look for FileId links which point to individual cases
        for a in soup.find_all('a', href=True):
            href = a['href']

            # New structure uses /FileId/{number}/ pattern
            if '/FileId/' in href:
                file_id_match = re.search(r'/FileId/(\d+)', href)
                if file_id_match:
                    file_id = file_id_match.group(1)
                    case_number = f"appeal-{year}-{file_id}"

                    # Make absolute URL
                    if not href.startswith('http'):
                        if href.startswith('/'):
                            href = 'https://doha.ogc.osd.mil' + href
                        else:
                            href = url + href

                    links.append((case_number, href))

            # Also look for old-style case number patterns as fallback
            elif re.search(r'\d{2}-\d+', href):
                case_match = re.search(r'(\d{2}-\d+)', href)
                if case_match:
                    case_number = f"appeal-{case_match.group(1)}"
                    if not href.startswith('http'):
                        if href.startswith('/'):
                            href = 'https://doha.ogc.osd.mil' + href
                        else:
                            href = url + href
                    links.append((case_number, href))

        # Remove duplicates
        seen = set()
        unique_links = []
        for case_num, case_url in links:
            if case_num not in seen:
                seen.add(case_num)
                unique_links.append((case_num, case_url))

        logger.info(f"Found {len(unique_links)} Appeal Board cases for year {year}")
        return unique_links

    def scrape_case_html(self, url: str) -> Optional[str]:
        """Scrape case text from HTML page using browser"""
        from bs4 import BeautifulSoup

        html = self._browser_get(url)

        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')

        # Remove script and style elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer']):
            element.decompose()

        # Get main content
        main = soup.find('main') or soup.find('article') or soup.find('body')
        if main:
            return main.get_text(separator='\n', strip=True)
        return soup.get_text(separator='\n', strip=True)

    def scrape_case_pdf(self, url: str) -> Optional[str]:
        """
        Download and parse PDF using browser

        For PDFs, we navigate to the URL and download the file,
        then parse it with PyMuPDF
        """
        try:
            import fitz  # PyMuPDF

            logger.debug(f"Downloading PDF from {url}")

            # Navigate to PDF URL
            response = self.page.goto(url, wait_until="commit", timeout=60000)

            if response is None or response.status != 200:
                logger.error(f"Failed to download PDF: HTTP {response.status if response else 'no response'}")
                return None

            # Get PDF content from response body (through browser)
            pdf_bytes = response.body()

            # Parse PDF from bytes
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text_parts = []

            for page in doc:
                text_parts.append(page.get_text())

            doc.close()
            return "\n".join(text_parts)

        except Exception as e:
            logger.error(f"Failed to scrape PDF from {url}: {e}")
            return None

    def download_case_pdf_bytes(self, url: str) -> Optional[bytes]:
        """
        Download PDF bytes using browser (bypasses bot protection)

        Args:
            url: URL to PDF file

        Returns:
            PDF bytes or None on failure
        """
        try:
            logger.debug(f"Downloading PDF bytes from {url}")

            # Use playwright's request context to fetch the PDF
            # This goes through the browser's session (with cookies, etc.) but doesn't navigate
            response = self.page.context.request.get(url, timeout=60000)

            if response.status != 200:
                logger.error(f"Failed to download PDF: HTTP {response.status}")
                return None

            # Get the response body
            pdf_bytes = response.body()

            return pdf_bytes

        except Exception as e:
            logger.error(f"Failed to download PDF from {url}: {e}")
            return None


def scrape_with_browser(
    output_dir: Path,
    start_year: int = 2017,
    end_year: int = 2026,
    max_cases: Optional[int] = None,
    include_2016_and_prior: bool = True,
    headless: bool = True
) -> Path:
    """
    Convenience function to scrape all DOHA cases using browser

    Args:
        output_dir: Directory to store scraped cases
        start_year: Starting year
        end_year: Ending year
        max_cases: Optional maximum number of cases
        include_2016_and_prior: Whether to include pre-2017 archive
        headless: Run browser in headless mode

    Returns:
        Path to the scraped cases directory
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting browser-based scrape from {start_year} to {end_year}")

    with DOHABrowserScraper(output_dir=output_dir, headless=headless) as scraper:
        cases = scraper.scrape_years(
            start_year=start_year,
            end_year=end_year,
            max_cases_per_year=max_cases,
            include_2016_and_prior=include_2016_and_prior
        )

        logger.info(f"Scraped {len(cases)} total cases")

    return output_dir


if __name__ == "__main__":
    print("DOHA Browser-Based Scraper")
    print("=" * 50)

    if not HAS_PLAYWRIGHT:
        print("\nError: playwright required")
        print("Install with: pip install playwright && playwright install chromium")
    else:
        print("\nTo scrape all cases:")
        print("  from rag.browser_scraper import scrape_with_browser")
        print("  scrape_with_browser('./doha_cases', include_2016_and_prior=True)")
