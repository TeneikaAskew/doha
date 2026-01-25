"""
DOHA Case Browser-Based Scraper

Uses Playwright to scrape DOHA cases with a real browser,
bypassing bot protection that blocks requests-based scraping.
"""
import json
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, Union
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue

try:
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
    from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    PlaywrightTimeoutError = Exception  # Fallback for type hints
    logger.warning("playwright not installed. Install with: pip install playwright && playwright install chromium")

from .scraper import DOHAScraper, ScrapedCase


# =============================================================================
# Error Taxonomy for Download Operations
# =============================================================================

class DownloadErrorType(Enum):
    """Types of download errors for debugging and tracking."""
    HTTP_ERROR = "http_error"           # Non-200 HTTP status code
    TIMEOUT = "timeout"                 # Request timed out
    NO_PDF_LINK = "no_pdf_link"         # HTML page but no PDF link found
    INVALID_PDF = "invalid_pdf"         # Response wasn't valid PDF data
    DECODE_ERROR = "decode_error"       # Couldn't decode response as text
    NETWORK_ERROR = "network_error"     # Network-level failure (DNS, connection)
    PARSE_ERROR = "parse_error"         # PDF parsing failed (fitz)
    UNKNOWN = "unknown"                 # Unexpected error


@dataclass
class DownloadError:
    """Structured error information from download operations."""
    error_type: DownloadErrorType
    message: str
    http_status: Optional[int] = None
    url: Optional[str] = None
    details: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "error_type": self.error_type.value,
            "message": self.message,
            "http_status": self.http_status,
            "url": self.url,
            "details": self.details
        }

    def __str__(self) -> str:
        """Human-readable error string."""
        parts = [f"{self.error_type.value}: {self.message}"]
        if self.http_status:
            parts.append(f"(HTTP {self.http_status})")
        if self.details:
            parts.append(f"- {self.details}")
        return " ".join(parts)


@dataclass
class DownloadResult:
    """Result from a download operation - either success with bytes or failure with error."""
    success: bool
    pdf_bytes: Optional[bytes] = None
    error: Optional[DownloadError] = None

    @classmethod
    def ok(cls, pdf_bytes: bytes) -> "DownloadResult":
        """Create a successful result."""
        return cls(success=True, pdf_bytes=pdf_bytes, error=None)

    @classmethod
    def fail(cls, error: DownloadError) -> "DownloadResult":
        """Create a failed result."""
        return cls(success=False, pdf_bytes=None, error=error)


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

    def download_case_pdf(self, url: str) -> DownloadResult:
        """
        Download PDF using browser with detailed error reporting.

        The URL may be:
        1. A direct PDF file (FileId URLs now return PDF directly)
        2. An HTML page containing links to PDF and TXT files

        We first check if the response is a PDF, and if not, parse as HTML.

        Args:
            url: URL to case page or direct PDF

        Returns:
            DownloadResult with pdf_bytes on success or detailed error on failure
        """
        from bs4 import BeautifulSoup

        try:
            logger.debug(f"Fetching case page: {url}")

            # Fetch the URL
            try:
                response = self.page.context.request.get(url, timeout=60000)
            except PlaywrightTimeoutError:
                error = DownloadError(
                    error_type=DownloadErrorType.TIMEOUT,
                    message="Request timed out after 60 seconds",
                    url=url,
                    details="Initial page fetch timeout"
                )
                logger.error(str(error))
                return DownloadResult.fail(error)

            if response.status != 200:
                error = DownloadError(
                    error_type=DownloadErrorType.HTTP_ERROR,
                    message=f"Failed to fetch page",
                    http_status=response.status,
                    url=url,
                    details=self._http_status_details(response.status)
                )
                logger.error(str(error))
                return DownloadResult.fail(error)

            # Get response body as bytes first
            body = response.body()

            # Check if response is already a PDF (magic bytes: %PDF)
            if body and len(body) >= 4 and body[:4] == b'%PDF':
                logger.debug(f"URL returned PDF directly: {url}")
                return DownloadResult.ok(body)

            # Not a PDF, try to parse as HTML to find PDF link
            try:
                html = body.decode('utf-8')
            except UnicodeDecodeError as e:
                # Binary data that's not a PDF - can't parse
                error = DownloadError(
                    error_type=DownloadErrorType.DECODE_ERROR,
                    message="Response is binary but not a PDF",
                    url=url,
                    details=f"Cannot decode as UTF-8: {e}"
                )
                logger.warning(str(error))
                return DownloadResult.fail(error)

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
                # Check what links ARE present for better debugging
                all_links = [a.get('href', '') for a in soup.find_all('a', href=True)]
                file_links = [l for l in all_links if any(l.endswith(ext) for ext in ['.pdf', '.txt', '.doc'])]
                error = DownloadError(
                    error_type=DownloadErrorType.NO_PDF_LINK,
                    message="No PDF link found on page",
                    url=url,
                    details=f"Found {len(all_links)} links total, {len(file_links)} file links: {file_links[:5]}"
                )
                logger.warning(str(error))
                return DownloadResult.fail(error)

            logger.debug(f"Downloading PDF: {pdf_link}")

            # Download the actual PDF
            try:
                pdf_response = self.page.context.request.get(pdf_link, timeout=60000)
            except PlaywrightTimeoutError:
                error = DownloadError(
                    error_type=DownloadErrorType.TIMEOUT,
                    message="PDF download timed out after 60 seconds",
                    url=pdf_link,
                    details="PDF file fetch timeout"
                )
                logger.error(str(error))
                return DownloadResult.fail(error)

            if pdf_response.status != 200:
                error = DownloadError(
                    error_type=DownloadErrorType.HTTP_ERROR,
                    message=f"Failed to download PDF",
                    http_status=pdf_response.status,
                    url=pdf_link,
                    details=self._http_status_details(pdf_response.status)
                )
                logger.error(str(error))
                return DownloadResult.fail(error)

            pdf_bytes = pdf_response.body()

            # Validate we got a PDF
            if not pdf_bytes or len(pdf_bytes) < 4 or not pdf_bytes[:4].startswith(b'%PDF'):
                error = DownloadError(
                    error_type=DownloadErrorType.INVALID_PDF,
                    message="Response is not a valid PDF",
                    url=pdf_link,
                    details=f"Expected %PDF header, got: {pdf_bytes[:20]!r}" if pdf_bytes else "Empty response"
                )
                logger.warning(str(error))
                return DownloadResult.fail(error)

            return DownloadResult.ok(pdf_bytes)

        except Exception as e:
            # Categorize the exception
            error_type = DownloadErrorType.UNKNOWN
            details = str(e)

            if "net::" in str(e).lower() or "network" in str(e).lower():
                error_type = DownloadErrorType.NETWORK_ERROR
            elif "timeout" in str(e).lower():
                error_type = DownloadErrorType.TIMEOUT

            error = DownloadError(
                error_type=error_type,
                message=f"Download failed: {type(e).__name__}",
                url=url,
                details=details
            )
            logger.error(str(error))
            return DownloadResult.fail(error)

    def _http_status_details(self, status: int) -> str:
        """Get human-readable description of HTTP status codes."""
        status_descriptions = {
            400: "Bad Request - malformed URL or parameters",
            401: "Unauthorized - authentication required",
            403: "Forbidden - access denied (may be bot protection)",
            404: "Not Found - case may have been removed",
            408: "Request Timeout - server took too long",
            429: "Too Many Requests - rate limited",
            500: "Internal Server Error - server issue",
            502: "Bad Gateway - upstream server error",
            503: "Service Unavailable - server overloaded or maintenance",
            504: "Gateway Timeout - upstream server timeout",
        }
        return status_descriptions.get(status, f"HTTP status {status}")

    def download_case_pdf_bytes(self, url: str) -> Optional[bytes]:
        """
        Download PDF bytes using browser (bypasses bot protection).

        This is a backward-compatible wrapper around download_case_pdf().
        For detailed error information, use download_case_pdf() instead.

        Args:
            url: URL to case page or direct PDF

        Returns:
            PDF bytes or None on failure
        """
        result = self.download_case_pdf(url)
        return result.pdf_bytes if result.success else None


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

    def _download_one(self, url: str, case_id: str = None) -> DownloadResult:
        """Download a single PDF using thread-local browser context with detailed error reporting.

        The URL may be:
        1. A direct PDF file (FileId URLs now return PDF directly)
        2. An HTML page containing links to PDF and TXT files

        We first check if the response is a PDF, and if not, parse as HTML.

        Args:
            url: URL to download
            case_id: Optional case identifier for logging

        Returns:
            DownloadResult with pdf_bytes on success or detailed error on failure
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
            try:
                response = ctx.request.get(url, timeout=60000)
            except PlaywrightTimeoutError:
                error = DownloadError(
                    error_type=DownloadErrorType.TIMEOUT,
                    message="Request timed out after 60 seconds",
                    url=url,
                    details="Initial page fetch timeout"
                )
                logger.warning(f"{log_prefix}{error}")
                return DownloadResult.fail(error)

            self._local.last_request = time.time()

            if response.status != 200:
                error = DownloadError(
                    error_type=DownloadErrorType.HTTP_ERROR,
                    message=f"Failed to fetch page",
                    http_status=response.status,
                    url=url,
                    details=self._http_status_description(response.status)
                )
                logger.warning(f"{log_prefix}{error}")
                return DownloadResult.fail(error)

            # Get response body as bytes first
            body = response.body()

            # Check if response is already a PDF (magic bytes: %PDF)
            if body and len(body) >= 4 and body[:4] == b'%PDF':
                logger.debug(f"{log_prefix}URL returned PDF directly: {url}")
                return DownloadResult.ok(body)

            # Not a PDF, try to parse as HTML to find PDF link
            try:
                html = body.decode('utf-8')
            except UnicodeDecodeError as e:
                error = DownloadError(
                    error_type=DownloadErrorType.DECODE_ERROR,
                    message="Response is binary but not a PDF",
                    url=url,
                    details=f"Cannot decode as UTF-8: {e}"
                )
                logger.warning(f"{log_prefix}{error}")
                return DownloadResult.fail(error)

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
                all_links = [a.get('href', '') for a in soup.find_all('a', href=True)]
                file_links = [l for l in all_links if any(l.endswith(ext) for ext in ['.pdf', '.txt', '.doc'])]
                error = DownloadError(
                    error_type=DownloadErrorType.NO_PDF_LINK,
                    message="No PDF link found on page",
                    url=url,
                    details=f"Found {len(all_links)} links total, {len(file_links)} file links"
                )
                logger.warning(f"{log_prefix}{error}")
                return DownloadResult.fail(error)

            logger.info(f"{log_prefix}Downloading PDF: {pdf_link}")

            # Rate limit again before PDF download
            elapsed = time.time() - self._local.last_request
            if elapsed < self.rate_limit:
                time.sleep(self.rate_limit - elapsed)

            # Download the actual PDF
            try:
                pdf_response = ctx.request.get(pdf_link, timeout=60000)
            except PlaywrightTimeoutError:
                error = DownloadError(
                    error_type=DownloadErrorType.TIMEOUT,
                    message="PDF download timed out after 60 seconds",
                    url=pdf_link,
                    details="PDF file fetch timeout"
                )
                logger.warning(f"{log_prefix}{error}")
                return DownloadResult.fail(error)

            self._local.last_request = time.time()

            if pdf_response.status != 200:
                error = DownloadError(
                    error_type=DownloadErrorType.HTTP_ERROR,
                    message=f"Failed to download PDF",
                    http_status=pdf_response.status,
                    url=pdf_link,
                    details=self._http_status_description(pdf_response.status)
                )
                logger.warning(f"{log_prefix}{error}")
                return DownloadResult.fail(error)

            body = pdf_response.body()

            # Validate we got a PDF (check magic bytes)
            if not body or len(body) < 4 or not body[:4] == b'%PDF':
                preview = body[:100].decode('utf-8', errors='replace') if body else '(empty)'
                error = DownloadError(
                    error_type=DownloadErrorType.INVALID_PDF,
                    message="Response is not a valid PDF",
                    url=pdf_link,
                    details=f"Expected %PDF header, got: {preview[:50]}..."
                )
                logger.warning(f"{log_prefix}{error}")
                return DownloadResult.fail(error)

            return DownloadResult.ok(body)

        except Exception as e:
            # Categorize the exception
            error_type = DownloadErrorType.UNKNOWN
            if "net::" in str(e).lower() or "network" in str(e).lower():
                error_type = DownloadErrorType.NETWORK_ERROR
            elif "timeout" in str(e).lower():
                error_type = DownloadErrorType.TIMEOUT

            error = DownloadError(
                error_type=error_type,
                message=f"Download failed: {type(e).__name__}",
                url=url,
                details=str(e)
            )
            logger.warning(f"{log_prefix}{error}")
            return DownloadResult.fail(error)

    def _http_status_description(self, status: int) -> str:
        """Get human-readable description of HTTP status codes."""
        status_descriptions = {
            400: "Bad Request - malformed URL or parameters",
            401: "Unauthorized - authentication required",
            403: "Forbidden - access denied (may be bot protection)",
            404: "Not Found - case may have been removed",
            408: "Request Timeout - server took too long",
            429: "Too Many Requests - rate limited",
            500: "Internal Server Error - server issue",
            502: "Bad Gateway - upstream server error",
            503: "Service Unavailable - server overloaded or maintenance",
            504: "Gateway Timeout - upstream server timeout",
        }
        return status_descriptions.get(status, f"HTTP status {status}")

    def download_batch(
        self,
        links: List[Tuple[str, str, str, str]],  # (case_type, year, case_number, url)
        callback=None
    ) -> List[Dict[str, Any]]:
        """
        Download multiple PDFs in parallel with detailed error reporting.

        Args:
            links: List of (case_type, year, case_number, url) tuples
            callback: Optional callback(case_number, pdf_bytes_or_none, error_or_none) called for each result

        Returns:
            List of result dicts with keys:
                - case_type, year, case_number, url: from input
                - pdf_bytes: bytes on success, None on failure
                - error: error message string (for backward compatibility)
                - error_type: DownloadErrorType.value (e.g., "http_error", "timeout")
                - http_status: HTTP status code if applicable
                - error_details: Additional context about the error
        """
        results = []
        results_lock = threading.Lock()

        def download_task(link):
            case_type, year, case_number, url = link
            try:
                download_result = self._download_one(url, case_id=case_number)

                if download_result.success:
                    result = {
                        "case_type": case_type,
                        "year": year,
                        "case_number": case_number,
                        "url": url,
                        "pdf_bytes": download_result.pdf_bytes,
                        "error": None,
                        "error_type": None,
                        "http_status": None,
                        "error_details": None
                    }
                else:
                    error = download_result.error
                    result = {
                        "case_type": case_type,
                        "year": year,
                        "case_number": case_number,
                        "url": url,
                        "pdf_bytes": None,
                        "error": error.message if error else "Unknown error",
                        "error_type": error.error_type.value if error else "unknown",
                        "http_status": error.http_status if error else None,
                        "error_details": error.details if error else None
                    }
            except Exception as e:
                # Shouldn't normally reach here since _download_one handles exceptions
                result = {
                    "case_type": case_type,
                    "year": year,
                    "case_number": case_number,
                    "url": url,
                    "pdf_bytes": None,
                    "error": f"{type(e).__name__}: {str(e)}",
                    "error_type": "unknown",
                    "http_status": None,
                    "error_details": f"Unhandled exception in download task: {type(e).__module__}.{type(e).__name__}"
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

