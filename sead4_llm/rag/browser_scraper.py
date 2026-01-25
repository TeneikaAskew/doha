"""
DOHA Case Browser-Based Scraper

Uses Playwright to scrape DOHA cases with a real browser,
bypassing bot protection that blocks requests-based scraping.
"""
import json
import time
import threading
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue

try:
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
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
        output_dir: Path = None,
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

        # Navigate to DOHA main page to establish session/cookies
        # This is important for the request context API to work properly
        try:
            # Use commit wait strategy (faster) - just need to establish connection, not load full page
            self.page.goto("https://doha.ogc.osd.mil/Industrial-Security-Program/", wait_until="commit", timeout=10000)
            logger.debug("Established session with DOHA website")
        except Exception as e:
            logger.warning(f"Could not navigate to DOHA homepage: {e}")

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
            response = self.page.goto(url, wait_until="domcontentloaded", timeout=120000)

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

    def get_case_links(self, year: int, is_archived: bool = None) -> List[Tuple[str, str, str, str]]:
        """
        Get links to case decisions for a given year using browser

        Args:
            year: The year to scrape
            is_archived: Whether to use archived URL pattern (auto-detect if None)

        Returns:
            List of (case_number, url, file_type, filename) tuples
            - case_number: e.g., "19-02453"
            - url: FileId URL
            - file_type: "pdf" or "txt"
            - filename: e.g., "19-02453.h1.pdf"
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
                # Extract filename from span element (e.g., "19-02453.h1.pdf")
                span = a.find('span')
                if not span:
                    continue

                filename = span.get_text().strip()
                if not filename:
                    continue

                # Detect file type from filename extension
                if filename.lower().endswith('.pdf'):
                    file_type = 'pdf'
                elif filename.lower().endswith('.txt'):
                    file_type = 'txt'
                else:
                    continue  # Skip unknown file types

                # Extract case number from filename (e.g., "19-02453" from "19-02453.h1.pdf")
                case_match = re.match(r'(\d{2}-\d+)', filename)
                if case_match:
                    case_number = case_match.group(1)
                else:
                    # Fallback to FileId-based case number
                    file_id_match = re.search(r'/FileId/(\d+)', href)
                    if file_id_match:
                        case_number = f"{year}-{file_id_match.group(1)}"
                    else:
                        continue

                # Make absolute URL
                if not href.startswith('http'):
                    if href.startswith('/'):
                        href = 'https://doha.ogc.osd.mil' + href
                    else:
                        href = url + href

                links.append((case_number, href, file_type, filename))

        # Remove duplicates based on (case_number, file_type) combination
        seen = set()
        unique_links = []
        for case_num, case_url, file_type, filename in links:
            key = (case_num, file_type)
            if key not in seen:
                seen.add(key)
                unique_links.append((case_num, case_url, file_type, filename))

        # Count by file type
        pdf_count = sum(1 for l in unique_links if l[2] == 'pdf')
        txt_count = sum(1 for l in unique_links if l[2] == 'txt')
        logger.info(f"Found {len(unique_links)} links for year {year} (PDF: {pdf_count}, TXT: {txt_count})")
        return unique_links

    def get_2016_and_prior_links(self) -> List[Tuple[str, str, str, str]]:
        """Get links from all "2016 and Prior" pages using browser

        Returns:
            List of (case_number, url, file_type, filename) tuples
        """
        from bs4 import BeautifulSoup
        import re

        all_links = []

        for page in range(1, self.DOHA_2016_PRIOR_PAGES + 1):
            # Page 2: flat URL works reliably, nested times out - just use flat for all pages
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
                    # Extract filename from span element
                    span = a.find('span')
                    if not span:
                        continue

                    filename = span.get_text().strip()
                    if not filename:
                        continue

                    # Detect file type from filename extension
                    if filename.lower().endswith('.pdf'):
                        file_type = 'pdf'
                    elif filename.lower().endswith('.txt'):
                        file_type = 'txt'
                    else:
                        continue  # Skip unknown file types

                    # Extract case number from filename
                    case_match = re.match(r'(\d{2}-\d+)', filename)
                    if case_match:
                        case_number = case_match.group(1)
                    else:
                        # Fallback to FileId-based case number
                        file_id_match = re.search(r'/FileId/(\d+)', href)
                        if file_id_match:
                            case_number = f"pre2016-{file_id_match.group(1)}"
                        else:
                            continue

                    if not href.startswith('http'):
                        if href.startswith('/'):
                            href = 'https://doha.ogc.osd.mil' + href
                        else:
                            href = url + href

                    page_links.append((case_number, href, file_type, filename))

            # Remove duplicates based on (case_number, file_type)
            seen_on_page = set()
            for case_num, case_url, file_type, filename in page_links:
                key = (case_num, file_type)
                if key not in seen_on_page:
                    seen_on_page.add(key)
                    all_links.append((case_num, case_url, file_type, filename))

            logger.info(f"Found {len(page_links)} links on page {page}")

        # Count by file type
        pdf_count = sum(1 for l in all_links if l[2] == 'pdf')
        txt_count = sum(1 for l in all_links if l[2] == 'txt')
        logger.info(f"Found total of {len(all_links)} links in 2016 and Prior pages (PDF: {pdf_count}, TXT: {txt_count})")
        return all_links

    def get_2016_and_prior_appeal_links(self) -> List[Tuple[str, str, str, str]]:
        """Get appeal links from all "2016 and Prior" appeal pages using browser

        Returns:
            List of (case_number, url, file_type, filename) tuples
        """
        from bs4 import BeautifulSoup
        import re

        all_links = []

        for page in range(1, self.DOHA_APPEAL_2016_PRIOR_PAGES + 1):
            url = self.DOHA_APPEAL_2016_PRIOR_PATTERN.format(page=page)
            logger.info(f"Fetching 2016 and Prior appeals page {page}/{self.DOHA_APPEAL_2016_PRIOR_PAGES}...")

            html = self._browser_get(url)

            if not html or len(html) < 100:
                logger.warning(f"Failed to get content for appeal page {page}")
                continue

            soup = BeautifulSoup(html, 'html.parser')

            page_links = []
            for a in soup.find_all('a', href=True):
                href = a['href']

                if '/FileId/' in href:
                    # Extract filename from span element
                    span = a.find('span')
                    if not span:
                        continue

                    filename = span.get_text().strip()
                    if not filename:
                        continue

                    # Detect file type from filename extension
                    if filename.lower().endswith('.pdf'):
                        file_type = 'pdf'
                    elif filename.lower().endswith('.txt'):
                        file_type = 'txt'
                    else:
                        continue  # Skip unknown file types

                    # Extract case number from filename
                    case_match = re.match(r'(\d{2}-\d+)', filename)
                    if case_match:
                        case_number = case_match.group(1)
                    else:
                        # Fallback to FileId-based case number
                        file_id_match = re.search(r'/FileId/(\d+)', href)
                        if file_id_match:
                            case_number = f"appeal-pre2016-{file_id_match.group(1)}"
                        else:
                            continue

                    if not href.startswith('http'):
                        if href.startswith('/'):
                            href = 'https://doha.ogc.osd.mil' + href
                        else:
                            href = url + href

                    page_links.append((case_number, href, file_type, filename))

            # Remove duplicates based on (case_number, file_type)
            seen_on_page = set()
            for case_num, case_url, file_type, filename in page_links:
                key = (case_num, file_type)
                if key not in seen_on_page:
                    seen_on_page.add(key)
                    all_links.append((case_num, case_url, file_type, filename))

            logger.info(f"Found {len(page_links)} appeal links on page {page}")

        # Count by file type
        pdf_count = sum(1 for l in all_links if l[2] == 'pdf')
        txt_count = sum(1 for l in all_links if l[2] == 'txt')
        logger.info(f"Found total of {len(all_links)} appeal links in 2016 and Prior pages (PDF: {pdf_count}, TXT: {txt_count})")
        return all_links

    def get_appeal_case_links(self, year: int, is_archived: bool = None) -> List[Tuple[str, str, str, str]]:
        """
        Get links to Appeal Board decisions for a given year using browser

        Args:
            year: The year to scrape
            is_archived: Whether to use archived URL pattern (auto-detect if None)

        Returns:
            List of (case_number, url, file_type, filename) tuples
        """
        from bs4 import BeautifulSoup
        import re

        # Auto-detect if year should use archive pattern
        if is_archived is None:
            is_archived = year < 2019

        # Choose URL pattern based on year
        # Appeal Board has different URL patterns for different years
        if is_archived:
            # Archived appeals (2017, 2018) have year-specific URLs
            url = self.DOHA_APPEAL_ARCHIVE_YEAR_PATTERN.format(year=year)
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
                # Extract filename from span element
                span = a.find('span')
                if not span:
                    continue

                filename = span.get_text().strip()
                if not filename:
                    continue

                # Detect file type from filename extension
                if filename.lower().endswith('.pdf'):
                    file_type = 'pdf'
                elif filename.lower().endswith('.txt'):
                    file_type = 'txt'
                else:
                    continue  # Skip unknown file types

                # Extract case number from filename
                case_match = re.match(r'(\d{2}-\d+)', filename)
                if case_match:
                    case_number = case_match.group(1)
                else:
                    # Fallback to FileId-based case number
                    file_id_match = re.search(r'/FileId/(\d+)', href)
                    if file_id_match:
                        case_number = f"appeal-{year}-{file_id_match.group(1)}"
                    else:
                        continue

                # Make absolute URL
                if not href.startswith('http'):
                    if href.startswith('/'):
                        href = 'https://doha.ogc.osd.mil' + href
                    else:
                        href = url + href

                links.append((case_number, href, file_type, filename))

        # Remove duplicates based on (case_number, file_type)
        seen = set()
        unique_links = []
        for case_num, case_url, file_type, filename in links:
            key = (case_num, file_type)
            if key not in seen:
                seen.add(key)
                unique_links.append((case_num, case_url, file_type, filename))

        # Count by file type
        pdf_count = sum(1 for l in unique_links if l[2] == 'pdf')
        txt_count = sum(1 for l in unique_links if l[2] == 'txt')
        logger.info(f"Found {len(unique_links)} Appeal Board links for year {year} (PDF: {pdf_count}, TXT: {txt_count})")
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

        The URL may be:
        1. A direct PDF file (FileId URLs now return PDF directly)
        2. An HTML page containing links to PDF and TXT files

        We first check if the response is a PDF, and if not, parse as HTML.

        Args:
            url: URL to case page or direct PDF

        Returns:
            PDF bytes or None on failure
        """
        from bs4 import BeautifulSoup

        try:
            logger.debug(f"Fetching case page: {url}")

            # Fetch the URL
            response = self.page.context.request.get(url, timeout=60000)

            if response.status != 200:
                logger.error(f"Failed to fetch page: HTTP {response.status}")
                return None

            # Get response body as bytes first
            body = response.body()

            # Check if response is already a PDF (magic bytes: %PDF)
            if body and len(body) >= 4 and body[:4] == b'%PDF':
                logger.debug(f"URL returned PDF directly: {url}")
                return body

            # Not a PDF, try to parse as HTML to find PDF link
            try:
                html = body.decode('utf-8')
            except UnicodeDecodeError:
                # Binary data that's not a PDF - can't parse
                logger.warning(f"Response is binary but not a PDF: {url}")
                return None

            # Parse HTML to find PDF link (skip .txt files)
            soup = BeautifulSoup(html, 'html.parser')
            pdf_link = None

            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.lower().endswith('.pdf'):
                    # Make absolute URL
                    if not href.startswith('http'):
                        if href.startswith('/'):
                            pdf_link = 'https://doha.ogc.osd.mil' + href
                        else:
                            pdf_link = url.rstrip('/') + '/' + href
                    else:
                        pdf_link = href
                    break

            if not pdf_link:
                logger.warning(f"No PDF link found on page: {url}")
                return None

            logger.debug(f"Downloading PDF: {pdf_link}")

            # Download the actual PDF
            pdf_response = self.page.context.request.get(pdf_link, timeout=60000)

            if pdf_response.status != 200:
                logger.error(f"Failed to download PDF: HTTP {pdf_response.status}")
                return None

            pdf_bytes = pdf_response.body()

            # Validate we got a PDF
            if not pdf_bytes or len(pdf_bytes) < 4 or not pdf_bytes[:4].startswith(b'%PDF'):
                logger.warning(f"Response is not a PDF for {pdf_link}")
                return None

            return pdf_bytes

        except Exception as e:
            logger.error(f"Failed to download PDF from {url}: {e}")
            return None


class ParallelBrowserDownloader:
    """
    Parallel PDF downloader using thread-local browser instances.

    Each worker thread gets its own playwright/browser/context to avoid
    thread-safety issues with Playwright's sync API.
    """

    def __init__(self, num_workers: int = 4, headless: bool = True, rate_limit: float = 0.5):
        if not HAS_PLAYWRIGHT:
            raise ImportError("playwright required. Install with: pip install playwright && playwright install chromium")

        self.num_workers = num_workers
        self.headless = headless
        self.rate_limit = rate_limit  # Seconds between requests per worker
        self._local = threading.local()
        self._workers_started = threading.Event()
        self._shutdown = threading.Event()

    def _get_thread_browser(self):
        """Get or create a browser instance for the current thread"""
        if not hasattr(self._local, 'playwright'):
            # Initialize playwright for this thread
            self._local.playwright = sync_playwright().start()
            self._local.browser = self._local.playwright.chromium.launch(headless=self.headless)
            self._local.context = self._local.browser.new_context(
                viewport={"width": 1920, "height": 1080}
            )

            # Establish session by navigating to homepage
            page = self._local.context.new_page()
            try:
                page.goto("https://doha.ogc.osd.mil/Industrial-Security-Program/",
                         wait_until="commit", timeout=15000)
                logger.debug(f"Thread {threading.current_thread().name}: Session established")
            except Exception as e:
                logger.warning(f"Thread {threading.current_thread().name}: Could not establish session: {e}")
            page.close()

        return self._local.context

    def _cleanup_thread_browser(self):
        """Clean up browser instance for current thread"""
        if hasattr(self._local, 'context'):
            try:
                self._local.context.close()
            except Exception:
                pass
        if hasattr(self._local, 'browser'):
            try:
                self._local.browser.close()
            except Exception:
                pass
        if hasattr(self._local, 'playwright'):
            try:
                self._local.playwright.stop()
            except Exception:
                pass

    def start(self):
        """Initialize (actual browser start happens per-thread)"""
        logger.info(f"Parallel downloader ready with {self.num_workers} workers")
        self._shutdown.clear()

    def stop(self):
        """Signal shutdown (cleanup happens in threads)"""
        self._shutdown.set()
        logger.info("Parallel downloader stopped")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def _download_one(self, url: str, case_id: str = None) -> Optional[bytes]:
        """Download a single PDF using thread-local browser context.

        The URL may be:
        1. A direct PDF file (FileId URLs now return PDF directly)
        2. An HTML page containing links to PDF and TXT files

        We first check if the response is a PDF, and if not, parse as HTML.

        Args:
            url: URL to download
            case_id: Optional case identifier for logging
        """
        from bs4 import BeautifulSoup

        ctx = self._get_thread_browser()
        log_prefix = f"[{case_id}] " if case_id else ""

        # Rate limiting per thread
        if not hasattr(self._local, 'last_request'):
            self._local.last_request = 0
        elapsed = time.time() - self._local.last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)

        logger.info(f"{log_prefix}Fetching: {url}")
        try:
            # Fetch the URL
            response = ctx.request.get(url, timeout=60000)
            self._local.last_request = time.time()

            if response.status != 200:
                logger.warning(f"{log_prefix}Failed to fetch page: HTTP {response.status} for {url}")
                return None

            # Get response body as bytes first
            body = response.body()

            # Check if response is already a PDF (magic bytes: %PDF)
            if body and len(body) >= 4 and body[:4] == b'%PDF':
                logger.debug(f"{log_prefix}URL returned PDF directly: {url}")
                return body

            # Not a PDF, try to parse as HTML to find PDF link
            try:
                html = body.decode('utf-8')
            except UnicodeDecodeError:
                # Binary data that's not a PDF - can't parse
                logger.warning(f"{log_prefix}Response is binary but not a PDF: {url}")
                return None

            # Parse HTML to find PDF link
            soup = BeautifulSoup(html, 'html.parser')
            pdf_link = None

            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.lower().endswith('.pdf'):
                    # Make absolute URL
                    if not href.startswith('http'):
                        if href.startswith('/'):
                            pdf_link = 'https://doha.ogc.osd.mil' + href
                        else:
                            pdf_link = url.rstrip('/') + '/' + href
                    else:
                        pdf_link = href
                    break

            if not pdf_link:
                logger.warning(f"{log_prefix}No PDF link found on page: {url}")
                return None

            logger.info(f"{log_prefix}Downloading PDF: {pdf_link}")

            # Rate limit again before PDF download
            elapsed = time.time() - self._local.last_request
            if elapsed < self.rate_limit:
                time.sleep(self.rate_limit - elapsed)

            # Download the actual PDF
            pdf_response = ctx.request.get(pdf_link, timeout=60000)
            self._local.last_request = time.time()

            if pdf_response.status != 200:
                logger.warning(f"{log_prefix}Failed to download PDF: HTTP {pdf_response.status} for {pdf_link}")
                return None

            body = pdf_response.body()

            # Validate we got a PDF (check magic bytes)
            if not body or len(body) < 4 or not body[:4] == b'%PDF':
                preview = body[:100].decode('utf-8', errors='replace') if body else '(empty)'
                logger.warning(f"{log_prefix}Not a PDF: {pdf_link} - starts with: {preview[:50]}...")
                return None

            return body

        except Exception as e:
            logger.warning(f"{log_prefix}Download error for {url}: {e}")
            return None

    def download_batch(
        self,
        links: List[Tuple[str, str, str, str]],  # (case_type, year, case_number, url)
        callback=None
    ) -> List[Dict[str, Any]]:
        """
        Download multiple PDFs in parallel.

        Args:
            links: List of (case_type, year, case_number, url) tuples
            callback: Optional callback(case_number, pdf_bytes_or_none, error_or_none) called for each result

        Returns:
            List of result dicts with keys: case_type, year, case_number, url, pdf_bytes, error
        """
        results = []
        results_lock = threading.Lock()

        def download_task(link):
            case_type, year, case_number, url = link
            try:
                pdf_bytes = self._download_one(url, case_id=case_number)
                result = {
                    "case_type": case_type,
                    "year": year,
                    "case_number": case_number,
                    "url": url,
                    "pdf_bytes": pdf_bytes,
                    "error": None if pdf_bytes else "No bytes returned"
                }
            except Exception as e:
                result = {
                    "case_type": case_type,
                    "year": year,
                    "case_number": case_number,
                    "url": url,
                    "pdf_bytes": None,
                    "error": str(e)
                }

            with results_lock:
                results.append(result)

            if callback:
                callback(
                    result["case_number"],
                    result["pdf_bytes"],
                    result["error"]
                )

            return result

        # Use thread pool with cleanup
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            futures = [executor.submit(download_task, link) for link in links]

            # Wait for all to complete
            for future in as_completed(futures):
                try:
                    future.result()  # Raise any exceptions
                except Exception as e:
                    logger.error(f"Worker error: {e}")

        return results


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
        print("  scrape_with_browser('./doha_full_scrape', include_2016_and_prior=True)")

