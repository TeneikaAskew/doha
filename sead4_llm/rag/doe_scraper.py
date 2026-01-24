"""
DOE OHA (Office of Hearings and Appeals) Case Scraper

Scrapes DOE security clearance cases from:
https://www.energy.gov/oha/listings/security-cases

DOE publishes Personnel Security Hearing (PSH) decisions that are similar
to DOHA cases but for Department of Energy security clearances.

Structure:
- Listing page: https://www.energy.gov/oha/listings/security-cases?page=N
- Article page: https://www.energy.gov/oha/articles/psh-XX-XXXX-matter-personnel-security-hearing
- PDF link: https://www.energy.gov/sites/default/files/YYYY-MM/PSH-XX-XXXX.pdf
"""
import json
import re
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from loguru import logger

try:
    from playwright.sync_api import sync_playwright, Page, Browser
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    logger.warning("playwright not installed. Install with: pip install playwright && playwright install chromium")

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    logger.warning("beautifulsoup4 not installed. Install with: pip install beautifulsoup4")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


@dataclass
class DOECase:
    """A scraped DOE OHA case"""
    case_number: str
    date: str
    outcome: str  # GRANTED, DENIED, REVOKED
    guidelines: List[str]
    summary: str
    full_text: str
    sor_allegations: List[str]
    mitigating_factors: List[str]
    judge: str
    source_url: str
    pdf_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DOECaseLink:
    """A case link extracted from the listing page"""
    case_number: str
    date: str
    title: str
    summary: str  # Contains guideline info like "G: Alcohol Consumption"
    article_url: str
    pdf_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class DOEBrowserScraper:
    """
    Browser-based DOE OHA scraper using Playwright

    Scrapes security clearance cases from energy.gov
    """

    # Base URLs
    LISTING_BASE_URL = "https://www.energy.gov/oha/listings/security-cases"
    ENERGY_GOV_BASE = "https://www.energy.gov"

    # Guideline patterns for extraction (same as DOHA - SEAD guidelines)
    GUIDELINE_PATTERNS = {
        'A': r'Guideline\s*A|Allegiance|AG\s*[^\w]\s*2',
        'B': r'Guideline\s*B|Foreign\s*Influence|AG\s*[^\w]\s*[67]',
        'C': r'Guideline\s*C|Foreign\s*Preference|AG\s*[^\w]\s*[910]',
        'D': r'Guideline\s*D|Sexual\s*Behavior|AG\s*[^\w]\s*1[23]',
        'E': r'Guideline\s*E|Personal\s*Conduct|AG\s*[^\w]\s*1[56]|E:\s*Personal\s*Conduct',
        'F': r'Guideline\s*F|Financial\s*Considerations|AG\s*[^\w]\s*1[89]|AG\s*[^\w]\s*20|F:\s*Financial',
        'G': r'Guideline\s*G|Alcohol\s*Consumption|AG\s*[^\w]\s*2[12]|G:\s*Alcohol',
        'H': r'Guideline\s*H|Drug\s*Involvement|AG\s*[^\w]\s*2[456]|H:\s*Drug',
        'I': r'Guideline\s*I|Psychological\s*Conditions|AG\s*[^\w]\s*2[78]|I:\s*Psychological',
        'J': r'Guideline\s*J|Criminal\s*Conduct|AG\s*[^\w]\s*3[012]|J:\s*Criminal',
        'K': r'Guideline\s*K|Handling\s*Protected\s*Information|AG\s*[^\w]\s*3[34]|K:\s*Handling',
        'L': r'Guideline\s*L|Outside\s*Activities|AG\s*[^\w]\s*3[67]|L:\s*Outside',
        'M': r'Guideline\s*M|Use\s*of\s*Information\s*Technology|AG\s*[^\w]\s*[34]0|M:\s*Use\s*of',
    }

    # Outcome patterns
    OUTCOME_PATTERNS = {
        'GRANTED': r'clearance\s+.*(?:is|should\s+be)\s+granted|eligibility\s+.*\s+(?:is|should\s+be)\s+granted|access\s+authorization\s+.*(?:is|should\s+be)\s+granted|favorable|should\s+be\s+restored',
        'DENIED': r'clearance\s+.*(?:is|should\s+be)\s+denied|eligibility\s+.*\s+(?:is|should\s+be)\s+denied|access\s+authorization\s+.*(?:is|should\s+be)\s+denied|unfavorable|should\s+not\s+be\s+granted|should\s+not\s+be\s+restored',
        'REVOKED': r'clearance\s+.*(?:is|should\s+be)\s+revoked|eligibility\s+.*\s+(?:is|should\s+be)\s+revoked|access\s+authorization\s+.*(?:is|should\s+be)\s+revoked',
    }

    def __init__(
        self,
        output_dir: Path = Path("./doe_cases"),
        rate_limit: float = 2.0,
        headless: bool = True
    ):
        if not HAS_PLAYWRIGHT:
            raise ImportError("playwright required. Install with: pip install playwright && playwright install chromium")
        if not HAS_BS4:
            raise ImportError("beautifulsoup4 required. Install with: pip install beautifulsoup4")

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.rate_limit = rate_limit
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.page = None
        self._last_request = 0

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

    def _rate_limit_wait(self):
        """Apply rate limiting"""
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request = time.time()

    def _browser_get(self, url: str) -> str:
        """Get page content using browser"""
        if not self.page:
            raise RuntimeError("Browser not started. Call start_browser() first or use context manager.")

        self._rate_limit_wait()

        logger.debug(f"Browser fetching: {url}")

        try:
            response = self.page.goto(url, wait_until="domcontentloaded", timeout=60000)

            if response is None:
                logger.error(f"Failed to load {url}: No response")
                return ""

            status = response.status
            if status == 403:
                logger.warning(f"Got 403 for {url}")
                time.sleep(5)
            elif status == 404:
                logger.warning(f"Got 404 for {url}")
                return ""

            # Wait for content to load
            time.sleep(1)

            return self.page.content()

        except Exception as e:
            logger.error(f"Browser error fetching {url}: {e}")
            return ""

    def get_total_pages(self) -> int:
        """
        Discover the total number of pages in the listing

        Returns:
            Total number of pages (0-indexed, so returns max page number + 1)
        """
        html = self._browser_get(self.LISTING_BASE_URL)

        if not html:
            logger.error("Failed to fetch listing page to determine total pages")
            return 0

        soup = BeautifulSoup(html, 'html.parser')

        # Look for the "Last" page link
        last_link = soup.find('a', {'aria-label': 'Last page'})
        if last_link and last_link.get('href'):
            # Extract page number from href like "/oha/listings/security-cases?page=139"
            match = re.search(r'page=(\d+)', last_link['href'])
            if match:
                last_page = int(match.group(1))
                logger.info(f"Found {last_page + 1} total pages (0-{last_page})")
                return last_page + 1

        # Fallback: look at pagination numbers
        pagination = soup.find('nav', {'aria-label': 'Pagination'})
        if pagination:
            page_links = pagination.find_all('a', class_='usa-pagination__button')
            max_page = 0
            for link in page_links:
                match = re.search(r'page=(\d+)', link.get('href', ''))
                if match:
                    page_num = int(match.group(1))
                    max_page = max(max_page, page_num)
            if max_page > 0:
                logger.info(f"Found approximately {max_page + 1} pages from pagination")
                return max_page + 1

        logger.warning("Could not determine total pages, defaulting to 1")
        return 1

    def get_case_links_from_page(self, page_num: int) -> List[DOECaseLink]:
        """
        Get case links from a single listing page

        Args:
            page_num: Page number (0-indexed)

        Returns:
            List of DOECaseLink objects
        """
        url = f"{self.LISTING_BASE_URL}?page={page_num}"
        logger.info(f"Fetching page {page_num}: {url}")

        html = self._browser_get(url)

        if not html:
            logger.error(f"Failed to fetch page {page_num}")
            return []

        soup = BeautifulSoup(html, 'html.parser')

        cases = []

        # Find all article elements with case links
        articles = soup.find_all('article', class_='listing-item')

        for article in articles:
            try:
                # Get the article URL
                about = article.get('about', '')
                if not about:
                    link = article.find('a', href=True)
                    if link:
                        about = link['href']

                if not about:
                    continue

                # Make absolute URL
                article_url = about if about.startswith('http') else self.ENERGY_GOV_BASE + about

                # Extract case number from title
                title_elem = article.find('span', class_='field--title')
                title = title_elem.get_text(strip=True) if title_elem else ""

                # Extract case number (e.g., "PSH-25-0181" from title)
                case_match = re.search(r'(PSH-\d{2}-\d{4})', title)
                case_number = case_match.group(1) if case_match else ""

                if not case_number:
                    # Try to extract from URL
                    url_match = re.search(r'(psh-\d{2}-\d{4})', about, re.IGNORECASE)
                    if url_match:
                        case_number = url_match.group(1).upper()

                # Extract date
                time_elem = article.find('time')
                date = time_elem.get('datetime', '') if time_elem else ""
                if not date and time_elem:
                    date = time_elem.get_text(strip=True)

                # Extract summary (contains guideline info)
                summary_elem = article.find('div', class_='listing-item__summary')
                summary = ""
                if summary_elem:
                    summary_field = summary_elem.find('div', class_='field--field-summary')
                    summary = summary_field.get_text(strip=True) if summary_field else summary_elem.get_text(strip=True)

                if case_number:
                    cases.append(DOECaseLink(
                        case_number=case_number,
                        date=date,
                        title=title,
                        summary=summary,
                        article_url=article_url
                    ))

            except Exception as e:
                logger.warning(f"Error parsing article on page {page_num}: {e}")
                continue

        logger.info(f"Found {len(cases)} cases on page {page_num}")
        return cases

    def get_pdf_url_from_article(self, article_url: str) -> Optional[str]:
        """
        Get the PDF URL from an article page

        Args:
            article_url: URL to the article page

        Returns:
            PDF URL or None if not found
        """
        html = self._browser_get(article_url)

        if not html:
            logger.error(f"Failed to fetch article page: {article_url}")
            return None

        soup = BeautifulSoup(html, 'html.parser')

        # Look for PDF link
        # The PDF is in a link like: <a href="/sites/default/files/2026-01/PSH-25-0181.pdf">
        pdf_link = soup.find('a', href=re.compile(r'\.pdf$', re.IGNORECASE))

        if pdf_link:
            href = pdf_link['href']
            # Make absolute URL
            if href.startswith('/'):
                return self.ENERGY_GOV_BASE + href
            elif href.startswith('http'):
                return href
            else:
                return self.ENERGY_GOV_BASE + '/' + href

        logger.warning(f"No PDF link found on article page: {article_url}")
        return None

    def get_all_case_links(
        self,
        start_page: int = 0,
        end_page: int = None,
        fetch_pdf_urls: bool = False
    ) -> List[DOECaseLink]:
        """
        Get all case links from the listing pages

        Args:
            start_page: Starting page number (0-indexed)
            end_page: Ending page number (exclusive), None for all pages
            fetch_pdf_urls: Whether to fetch PDF URLs from each article page

        Returns:
            List of DOECaseLink objects
        """
        if end_page is None:
            end_page = self.get_total_pages()

        all_cases = []

        for page_num in range(start_page, end_page):
            try:
                cases = self.get_case_links_from_page(page_num)

                if fetch_pdf_urls:
                    # Fetch PDF URL for each case
                    for case in cases:
                        pdf_url = self.get_pdf_url_from_article(case.article_url)
                        if pdf_url:
                            case.pdf_url = pdf_url

                all_cases.extend(cases)

                # Save checkpoint every 10 pages
                if (page_num + 1) % 10 == 0:
                    checkpoint_file = self.output_dir / f"links_checkpoint_page_{page_num}.json"
                    with open(checkpoint_file, 'w') as f:
                        json.dump([c.to_dict() for c in all_cases], f, indent=2)
                    logger.info(f"Checkpoint saved: {checkpoint_file}")

            except Exception as e:
                logger.error(f"Error processing page {page_num}: {e}")
                continue

        return all_cases

    def download_pdf_bytes(self, url: str) -> Optional[bytes]:
        """
        Download PDF bytes using browser

        Args:
            url: URL to PDF file

        Returns:
            PDF bytes or None on failure
        """
        try:
            logger.debug(f"Downloading PDF bytes from {url}")

            self._rate_limit_wait()

            # Use playwright's request context
            response = self.page.context.request.get(url, timeout=60000)

            if response.status != 200:
                logger.error(f"Failed to download PDF: HTTP {response.status}")
                return None

            return response.body()

        except Exception as e:
            logger.error(f"Failed to download PDF from {url}: {e}")
            return None

    def parse_case_text(self, case_number: str, text: str, source_url: str, pdf_url: str = "") -> DOECase:
        """
        Parse case text to extract structured information

        DOE PSH (Personnel Security Hearing) cases typically contain:
        - Case header with case number and date
        - Notification Letter (equivalent to Statement of Reasons/SOR)
        - Procedural Background / Statement of the Case
        - Findings of Fact
        - Analysis / Discussion
        - Conclusion / Opinion
        - Hearing Officer signature

        Args:
            case_number: DOE case number (e.g., PSH-25-0181)
            text: Full text of the decision
            source_url: URL where case was found
            pdf_url: URL to the PDF

        Returns:
            DOECase with extracted information
        """
        # Extract date
        date = self._extract_date(text)

        # Extract outcome
        outcome = self._extract_outcome(text)

        # Extract guidelines
        guidelines = self._extract_guidelines(text)

        # Extract notification letter / SOR allegations
        sor_allegations = self._extract_sor_allegations(text)

        # Extract mitigating factors
        mitigating_factors = self._extract_mitigating_factors(text)

        # Extract hearing officer name
        judge = self._extract_judge(text)

        # Create summary from Findings of Fact
        summary = self._create_summary(text)

        return DOECase(
            case_number=case_number,
            date=date,
            outcome=outcome,
            guidelines=guidelines,
            summary=summary,
            full_text=text,
            sor_allegations=sor_allegations,
            mitigating_factors=mitigating_factors,
            judge=judge,
            source_url=source_url,
            pdf_url=pdf_url
        )

    def _extract_date(self, text: str) -> str:
        """Extract decision date from case text"""
        # Month names for matching
        months = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'

        # Look for date patterns - DOE cases often have date at top or end
        patterns = [
            # "Issued: January 15, 2026" or "Date: January 15, 2026"
            rf'(?:Issued|Date|Dated)[:\s]+({months}\s+\d{{1,2}},?\s+\d{{4}})',
            # Full month name date pattern (most common in DOE cases)
            rf'({months}\s+\d{{1,2}},?\s+\d{{4}})',
            # MM/DD/YYYY format
            r'(\d{1,2}/\d{1,2}/\d{4})',
        ]

        # Check beginning of document
        for pattern in patterns:
            match = re.search(pattern, text[:3000], re.IGNORECASE)
            if match:
                return match.group(1)

        # Check end of document (signature area)
        for pattern in patterns:
            match = re.search(pattern, text[-2000:], re.IGNORECASE)
            if match:
                return match.group(1)

        return "Unknown"

    def _extract_outcome(self, text: str) -> str:
        """Extract case outcome from text"""
        # DOE PSH cases typically end with OPINION OF THE HEARING OFFICER or CONCLUSION
        # Look at the last portion of the document

        # Get the conclusion/opinion section - look for these sections in the last part
        last_section = text[-8000:]

        # DOE-specific outcome patterns - order matters (check DENIED before GRANTED
        # because "should not be granted" contains "granted")
        doe_outcome_patterns = {
            'DENIED': [
                r'should\s+not\s+be\s+(?:granted|restored)',
                r'access\s+authorization\s+should\s+not\s+be\s+(?:granted|restored)',
                r'access\s+authorization\s+(?:should\s+be\s+)?(?:is\s+)?(?:hereby\s+)?denied',
                r'security\s+clearance\s+(?:should\s+be\s+)?(?:is\s+)?(?:hereby\s+)?denied',
                r'eligibility\s+.*?(?:should\s+be\s+)?(?:is\s+)?(?:hereby\s+)?denied',
                r'unfavorable\s+(?:determination|decision)',
                r'deny(?:ing)?\s+(?:the\s+)?(?:individual[\'s]?\s+)?(?:access|clearance|eligibility)',
            ],
            'REVOKED': [
                r'access\s+authorization\s+(?:should\s+be\s+)?(?:is\s+)?(?:hereby\s+)?revoked',
                r'security\s+clearance\s+(?:should\s+be\s+)?(?:is\s+)?(?:hereby\s+)?revoked',
                r'eligibility\s+.*?(?:should\s+be\s+)?(?:is\s+)?(?:hereby\s+)?revoked',
                r'revok(?:e|ing)\s+(?:the\s+)?(?:individual[\'s]?\s+)?(?:access|clearance|eligibility)',
            ],
            'GRANTED': [
                r'access\s+authorization\s+should\s+be\s+restored',
                r'should\s+be\s+(?:restored|granted)',
                r'access\s+authorization\s+(?:should\s+be\s+)?(?:is\s+)?(?:hereby\s+)?granted',
                r'security\s+clearance\s+(?:should\s+be\s+)?(?:is\s+)?(?:hereby\s+)?granted',
                r'eligibility\s+.*?(?:should\s+be\s+)?(?:is\s+)?(?:hereby\s+)?granted',
                r'favorable\s+(?:determination|decision)',
                r'grant(?:ing)?\s+(?:the\s+)?(?:individual[\'s]?\s+)?(?:access|clearance|eligibility)',
            ],
        }

        last_section_lower = last_section.lower()

        # Check patterns in priority order
        for outcome, patterns in doe_outcome_patterns.items():
            for pattern in patterns:
                if re.search(pattern, last_section_lower):
                    return outcome

        return "UNKNOWN"

    def _extract_guidelines(self, text: str) -> List[str]:
        """Extract relevant guidelines (criteria) from case text"""
        guidelines = []

        # DOE uses "Criterion" terminology (A-M) similar to DOHA
        # Check for explicit criterion mentions
        criterion_matches = re.findall(r'Criterion\s+([A-M])', text, re.IGNORECASE)
        for match in criterion_matches:
            if match.upper() not in guidelines:
                guidelines.append(match.upper())

        # Also check guideline pattern mentions
        for code, pattern in self.GUIDELINE_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                if code not in guidelines:
                    guidelines.append(code)

        return sorted(guidelines)

    def _extract_sor_allegations(self, text: str) -> List[str]:
        """
        Extract allegations from the Notification Letter or Summary of Security Concerns

        DOE cases use "Notification Letter" which contains the security concerns,
        similar to DOHA's Statement of Reasons (SOR).
        """
        allegations = []

        # DOE-specific section headers
        notification_patterns = [
            # Notification Letter section
            r'(?:NOTIFICATION\s+LETTER|SUMMARY\s+OF\s+(?:SECURITY\s+)?CONCERNS?|STATEMENT\s+OF\s+(?:THE\s+)?CHARGES?|LETTER\s+OF\s+NOTIFICATION)\s*(.*?)(?:FINDINGS|PROCEDURAL|BACKGROUND|HEARING|II\.|ANALYSIS)',
            # Criterion-based format
            r'(?:Criterion\s+[A-M].*?)(?=Criterion\s+[A-M]|FINDINGS|PROCEDURAL|II\.|\Z)',
        ]

        notification_text = ""
        for pattern in notification_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                notification_text = match.group(1) if match.lastindex else match.group(0)
                break

        if notification_text:
            # Extract individual allegations/concerns
            # Look for numbered items or criterion-based items
            allegation_patterns = [
                # Numbered allegations: "1.", "1.a.", "(1)", etc.
                r'(?:^|\n)\s*(?:\d+\.(?:\s*[a-z]\.)?|\(\d+\))\s*(.+?)(?=\n\s*(?:\d+\.|\(\d+\)|Criterion|$))',
                # Criterion mentions with description
                r'Criterion\s+([A-M])\s*[:\-]?\s*(.+?)(?=\n\s*(?:Criterion|\d+\.|$))',
            ]

            for pattern in allegation_patterns:
                matches = re.findall(pattern, notification_text, re.MULTILINE | re.IGNORECASE | re.DOTALL)
                for match in matches:
                    if isinstance(match, tuple):
                        allegation = ' '.join(match).strip()
                    else:
                        allegation = match.strip()
                    # Clean up and limit length
                    allegation = re.sub(r'\s+', ' ', allegation)[:500]
                    if len(allegation) > 20 and allegation not in allegations:
                        allegations.append(allegation)

        return allegations[:10]

    def _extract_mitigating_factors(self, text: str) -> List[str]:
        """Extract mitigating factors mentioned in the decision"""
        mitigating = []

        # DOE-specific mitigating factor patterns
        mit_patterns = [
            # Explicit mitigating conditions
            r'mitigating\s+(?:condition|factor)[s]?\s*(?:\d+)?[:\s]*(.+?)(?:\n\n|\n(?=[A-Z]))',
            # "In mitigation" statements
            r'(?:in\s+mitigation|mitigating\s+circumstances?)[,:\s]*(.+?)(?:\n\n|\n(?=[A-Z]))',
            # DOE mitigating condition references like "MC 1" or "Mitigating Condition (1)"
            r'(?:MC\s*\d+|Mitigating\s+Condition\s*\(?\d+\)?)[:\s]*(.+?)(?:\n|$)',
            # "The individual has" (common mitigating factor phrasing)
            r'(?:the\s+individual\s+has)\s+(.+?)(?:which\s+mitigates?|therefore)',
        ]

        for pattern in mit_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                clean = re.sub(r'\s+', ' ', match).strip()[:300]
                if len(clean) > 20 and clean not in mitigating:
                    mitigating.append(clean)

        return mitigating[:10]

    def _extract_judge(self, text: str) -> str:
        """Extract hearing officer name from DOE case"""
        # DOE cases use "Hearing Officer" not "Administrative Judge"
        patterns = [
            # "Hearing Officer: John Smith" or signature block
            r'Hearing\s+Officer[:\s]+([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)',
            # Name followed by "Hearing Officer"
            r'([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)\s*\n\s*Hearing\s+Officer',
            # Signature line "/s/ John Smith"
            r'/s/\s*([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)',
            # "Signed by John Smith"
            r'(?:Signed\s+by|Electronically\s+signed)[:\s]+([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)',
            # Name at end of document before "Hearing Officer"
            r'([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)\s*,?\s*Hearing\s+Officer',
            # OHA Hearing Officer pattern
            r'OHA\s+(?:Case\s+)?(?:No\.?\s+)?.*?([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)\s*,?\s*Hearing\s+Officer',
        ]

        # Check end of document first (signature area)
        for pattern in patterns:
            match = re.search(pattern, text[-4000:], re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Filter out common false positives
                if name.lower() not in ['hearing officer', 'the individual', 'the hearing']:
                    return name

        # Check beginning of document
        for pattern in patterns:
            match = re.search(pattern, text[:5000], re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if name.lower() not in ['hearing officer', 'the individual', 'the hearing']:
                    return name

        return "Unknown"

    def _create_summary(self, text: str) -> str:
        """
        Create a summary from Findings of Fact section

        DOE PSH cases typically have structured sections:
        - Statement of the Case / Procedural Background
        - Findings of Fact
        - Analysis / Discussion
        - Conclusion / Opinion
        """
        # Priority order for sections to use as summary
        section_patterns = [
            # Findings of Fact (most important for summary)
            (r'(?:FINDINGS?\s+OF\s+FACT|II\.\s*FINDINGS?\s+OF\s+FACT)\s*(.*?)(?=(?:III\.|ANALYSIS|DISCUSSION|CONCLUSION|OPINION\s+OF))',
             'Findings of Fact'),
            # Analysis section
            (r'(?:ANALYSIS|DISCUSSION)\s*(.*?)(?=(?:CONCLUSION|OPINION\s+OF|\Z))',
             'Analysis'),
            # Statement of the Case / Background
            (r'(?:STATEMENT\s+OF\s+(?:THE\s+)?CASE|PROCEDURAL\s+(?:BACKGROUND|HISTORY)|I\.\s*(?:BACKGROUND|INTRODUCTION))\s*(.*?)(?=(?:II\.|FINDINGS|NOTIFICATION))',
             'Background'),
        ]

        for pattern, section_name in section_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                section_text = match.group(1).strip()
                if len(section_text) > 100:  # Ensure we got meaningful content
                    # Clean up whitespace
                    summary = re.sub(r'\s+', ' ', section_text).strip()
                    # Prefix with section name for context
                    return f"{section_name}: {summary[:1500]}"

        # Fallback: try to get any substantial text after headers
        # Skip the first ~500 chars (usually just headers)
        fallback_text = text[500:2500] if len(text) > 2500 else text[500:]
        summary = re.sub(r'\s+', ' ', fallback_text).strip()
        return summary[:1500] if summary else "No summary available"


class DOESimpleScraper:
    """
    Simple HTTP-based scraper for DOE cases (when Playwright not needed)
    """

    LISTING_BASE_URL = "https://www.energy.gov/oha/listings/security-cases"
    ENERGY_GOV_BASE = "https://www.energy.gov"

    def __init__(
        self,
        output_dir: Path = Path("./doe_cases"),
        rate_limit: float = 2.0
    ):
        if not HAS_REQUESTS:
            raise ImportError("requests required. Install with: pip install requests")
        if not HAS_BS4:
            raise ImportError("beautifulsoup4 required. Install with: pip install beautifulsoup4")

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.rate_limit = rate_limit
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })
        self._last_request = 0

    def _rate_limited_get(self, url: str) -> Optional[requests.Response]:
        """Make a rate-limited GET request"""
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)

        try:
            response = self.session.get(url, timeout=30)
            self._last_request = time.time()
            return response
        except Exception as e:
            logger.error(f"Request failed for {url}: {e}")
            return None

    def test_connection(self) -> bool:
        """Test if we can connect to energy.gov without bot protection"""
        response = self._rate_limited_get(self.LISTING_BASE_URL)
        if response and response.status_code == 200:
            logger.info("Simple HTTP connection works!")
            return True
        else:
            status = response.status_code if response else "No response"
            logger.warning(f"Simple HTTP connection failed: {status}")
            return False


if __name__ == "__main__":
    print("DOE OHA Case Scraper")
    print("=" * 50)

    if not HAS_PLAYWRIGHT:
        print("\nWarning: playwright not installed")
        print("Install with: pip install playwright && playwright install chromium")

    if not HAS_BS4:
        print("\nWarning: beautifulsoup4 not installed")
        print("Install with: pip install beautifulsoup4")

    print("\nTo scrape DOE cases:")
    print("  python run_doe_scrape.py")
    print("\nTo download PDFs:")
    print("  python download_doe_pdfs.py")
