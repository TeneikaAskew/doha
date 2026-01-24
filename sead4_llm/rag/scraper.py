"""
DOHA Case Scraper

Scrapes DOHA (Defense Office of Hearings and Appeals) case decisions
from public sources for building a precedent index.

DOHA publishes industrial security clearance decisions at:
https://ogc.osd.mil/doha/industrial/

This scraper downloads and parses these decisions to extract:
- Case numbers
- Outcomes (Granted/Denied/Revoked)
- Relevant guidelines
- Key facts and reasoning
"""
import json
import os
import re
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from loguru import logger

# Web scraping
try:
    import requests
    from bs4 import BeautifulSoup
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logger.warning("requests/beautifulsoup4 not installed. Install with: pip install requests beautifulsoup4")

# PDF parsing
try:
    import fitz  # PyMuPDF
    HAS_PDF = True
except ImportError:
    HAS_PDF = False


@dataclass
class ScrapedCase:
    """A scraped DOHA case"""
    case_number: str
    date: str
    outcome: str  # GRANTED, DENIED, REVOKED, REMANDED
    guidelines: List[str]
    summary: str
    full_text: str
    sor_allegations: List[str]
    mitigating_factors: List[str]
    judge: str
    source_url: str
    formal_findings: Dict[str, dict]  # Per-guideline formal findings with subparagraph details
    # Appeal-specific fields (empty for hearing decisions)
    case_type: str = "hearing"  # "hearing" or "appeal"
    appeal_board_members: List[str] = None  # List of Appeal Board judges for appeals
    judges_findings_of_fact: str = ""  # Summary of AJ's findings (for appeals)
    judges_analysis: str = ""  # Summary of AJ's analysis (for appeals)
    discussion: str = ""  # Appeal Board's discussion/analysis
    order: str = ""  # Appeal Board's order (e.g., "AFFIRMED", "REVERSED", "REMANDED")

    def __post_init__(self):
        if self.appeal_board_members is None:
            self.appeal_board_members = []

    def to_dict(self) -> dict:
        return asdict(self)


class DOHAScraper:
    """
    Scrapes DOHA case decisions from public sources

    Primary sources:
    1. OSD OGC DOHA Industrial Security page
    2. DOHA case archives
    """

    # ========================================
    # HEARING DECISIONS URL PATTERNS
    # ========================================
    # Base URLs for DOHA Hearing cases
    DOHA_BASE_URL = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/ISCR-Hearing-Decisions/"
    # Pattern for recent years (current structure)
    # Note: 2024 uses different pattern (2024-ISCR-Hearing vs 2025-ISCR-Hearing-Decisions)
    DOHA_YEAR_PATTERN = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/ISCR-Hearing-Decisions/{year}-ISCR-Hearing-Decisions/"
    DOHA_2024_PATTERN = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/ISCR-Hearing-Decisions/2024-ISCR-Hearing/"
    # For archived years
    DOHA_ARCHIVE_BASE = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/ISCR-Hearing-Decisions/Archived-ISCR-Hearing-Decisions/"
    DOHA_ARCHIVE_YEAR_PATTERN = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/ISCR-Hearing-Decisions/Archived-ISCR-Hearing-Decisions/{year}-ISCR-Hearing-Decisions/"
    # For 2016 and prior (split across multiple pages)
    DOHA_2016_PRIOR_PATTERN = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/ISCR-Hearing-Decisions/Archived-ISCR-Hearing-Decisions/2016-and-Prior-ISCR-Hearing-Decisions-{page}/"
    DOHA_2016_PRIOR_PAGES = 17  # There are 17 pages for 2016 and prior cases

    # ========================================
    # APPEAL BOARD DECISIONS URL PATTERNS
    # ========================================
    # Base URL for DOHA Appeal Board decisions
    DOHA_APPEAL_BASE_URL = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/DOHA-Appeal-Board/"
    # Pattern for recent appeal years (2019-current)
    # Note: URL patterns vary by year (some use "DOHA-Appeal-Board" others use "DOHA-Appeal-Board-Decisions")
    DOHA_APPEAL_YEAR_PATTERN = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/DOHA-Appeal-Board/{year}-DOHA-Appeal-Board-Decisions/"
    # Special patterns for years with different URL structure
    DOHA_APPEAL_2022_PATTERN = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/DOHA-Appeal-Board/2022-DOHA-Appeal-Board/"
    DOHA_APPEAL_2021_PATTERN = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/DOHA-Appeal-Board/2021-DOHA-Appeal-Board/"
    DOHA_APPEAL_2020_PATTERN = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/DOHA-Appeal-Board/2020-DOHA-Appeal-Board/"
    DOHA_APPEAL_2019_PATTERN = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/DOHA-Appeal-Board/2019-DOHA-Appeal-Board/"
    # For archived appeal years
    DOHA_APPEAL_ARCHIVE_BASE = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/DOHA-Appeal-Board/Archived-DOHA-Appeal-Board/"
    # For 2016 and prior appeals (split across multiple pages)
    DOHA_APPEAL_2016_PRIOR_PATTERN = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/DOHA-Appeal-Board/Archived-DOHA-Appeal-Board/2016-and-Prior-DOHA-Appeal-Board-{page}/"
    DOHA_APPEAL_2016_PRIOR_PAGES = 3  # There are at least 3 pages for 2016 and prior appeal cases

    # Guideline patterns for extraction
    GUIDELINE_PATTERNS = {
        'A': r'Guideline\s*A|Allegiance|AG\s*¶\s*2',
        'B': r'Guideline\s*B|Foreign\s*Influence|AG\s*¶\s*6|AG\s*¶\s*7',
        'C': r'Guideline\s*C|Foreign\s*Preference|AG\s*¶\s*9|AG\s*¶\s*10',
        'D': r'Guideline\s*D|Sexual\s*Behavior|AG\s*¶\s*12|AG\s*¶\s*13',
        'E': r'Guideline\s*E|Personal\s*Conduct|AG\s*¶\s*15|AG\s*¶\s*16',
        'F': r'Guideline\s*F|Financial\s*Considerations|AG\s*¶\s*18|AG\s*¶\s*19|AG\s*¶\s*20',
        'G': r'Guideline\s*G|Alcohol\s*Consumption|AG\s*¶\s*21|AG\s*¶\s*22',
        'H': r'Guideline\s*H|Drug\s*Involvement|AG\s*¶\s*24|AG\s*¶\s*25|AG\s*¶\s*26',
        'I': r'Guideline\s*I|Psychological\s*Conditions|AG\s*¶\s*27|AG\s*¶\s*28',
        'J': r'Guideline\s*J|Criminal\s*Conduct|AG\s*¶\s*30|AG\s*¶\s*31|AG\s*¶\s*32',
        'K': r'Guideline\s*K|Handling\s*Protected\s*Information|AG\s*¶\s*33|AG\s*¶\s*34',
        'L': r'Guideline\s*L|Outside\s*Activities|AG\s*¶\s*36|AG\s*¶\s*37',
        'M': r'Guideline\s*M|Use\s*of\s*Information\s*Technology|AG\s*¶\s*39|AG\s*¶\s*40',
    }

    # Outcome patterns - list of patterns per outcome for comprehensive matching
    # These are searched in the last portion of the document
    # Patterns are checked in order; more specific patterns should come first
    OUTCOME_PATTERNS = {
        'GRANTED': [
            r'clearance\s+is\s+granted',
            r'eligibility\s+for\s+access\s+to\s+classified\s+information\s+is\s+granted',
            r'eligibility\s+[^.]{0,50}\s+is\s+granted',
            r'access\s+to\s+classified\s+information\s+is\s+granted',
            r'favorable\s+determination',
            r'security\s+clearance\s+is\s+granted',
            r'eligibility\s+is\s+granted',  # Direct "eligibility is granted"
            r'eligibility\s+granted',  # Without "is"
            r'clearance\s+granted',
            r'clearance\s+eligibility\s+is\s+granted',
            r'cac\s+eligibility\s+is\s+granted',  # Common Access Card cases
            # "Clearly consistent" language (means granted)
            r'it\s+is\s+clearly\s+consistent\s+with\s+the\s+national\s+interest\s+to\s+grant',
            r'clearly\s+consistent\s+with\s+the\s+interests\s+of\s+national\s+security',
            r'clearly\s+consistent\s+with\s+the\s+security\s+interests',
            r'national\s+security\s+eligibility\s+is\s+granted',
            # Appeal Board: favorable decision affirmed = grant upheld
            r'favorable\s+decision\s+(?:is\s+)?affirmed',
            # Appeal Board: adverse decision reversed = denial overturned = granted
            r'adverse\s+decision\s+(?:is\s+)?reversed',
            # Appeal Board: adverse findings not sustainable + reversed = denial overturned
            r'adverse\s+findings\s+are\s+not\s+sustainable',
        ],
        'DENIED': [
            r'clearance\s+is\s+denied',
            r'eligibility\s+for\s+access\s+to\s+classified\s+information\s+is\s+denied',
            r'eligibility\s+[^.]{0,50}\s+is\s+denied',
            r'access\s+to\s+classified\s+information\s+is\s+denied',
            r'unfavorable\s+determination',
            r'security\s+clearance\s+is\s+denied',
            r'eligibility\s+is\s+denied',  # Direct "eligibility is denied"
            r'eligibility\s+denied',  # Without "is"
            r'clearance\s+denied',
            r'clearance\s+eligibility\s+is\s+denied',
            r'cac\s+eligibility\s+is\s+denied',  # Common Access Card cases
            # "Not clearly consistent" language (means denied)
            r'it\s+is\s+not\s+clearly\s+consistent\s+with\s+the\s+national\s+interest\s+to\s+grant',
            r'not\s+clearly\s+consistent\s+with\s+the\s+national\s+interest',
            r'not\s+clearly\s+consistent\s+with\s+the\s+interests\s+of\s+national\s+security',
            r'not\s+clearly\s+consistent\s+with\s+the\s+security\s+interests',
            r'national\s+security\s+eligibility\s+is\s+denied',
            # Appeal Board: adverse decision affirmed = denial upheld
            r'adverse\s+decision\s+(?:is\s+)?affirmed',
            # Appeal Board: favorable decision reversed = grant overturned = denied
            r'favorable\s+decision\s+(?:is\s+)?reversed',
            # Appeal Board: favorable determination cannot be sustained + reversed = grant overturned
            r'favorable\s+(?:security\s+)?(?:clearance\s+)?determination\s+cannot\s+be\s+sustained',
            # Appeal Board: decision not sustainable + reversed (usually means grant overturned)
            r'decision\s+(?:is\s+)?not\s+sustainable[^.]*reversed',
            # Appeal Board: record not sufficient to mitigate + reversed (denial should stand)
            r'record\s+(?:evidence\s+)?(?:is\s+)?not\s+sufficient\s+to\s+mitigate',
            # Appeal Board: runs contrary to record evidence (usually overturning a favorable decision)
            r'runs\s+contrary\s+to\s+the\s+(?:weight\s+of\s+the\s+)?record\s+evidence[^.]*not\s+sustainable',
        ],
        'REVOKED': [
            r'clearance\s+is\s+revoked',
            r'eligibility\s+[^.]{0,50}\s+is\s+revoked',
            r'access\s+to\s+classified\s+information\s+is\s+revoked',
            r'security\s+clearance\s+is\s+revoked',
            r'eligibility\s+revoked',
            r'clearance\s+revoked',
        ],
        'REMANDED': [
            # Appeal Board: case sent back to administrative judge
            r'case\s+(?:is\s+)?remanded',
            r'decision\s+(?:is\s+)?remanded',
            r'remanded\s+to\s+the\s+administrative\s+judge',
            r'remanded\s+for\s+(?:further|additional)\s+proceedings',
        ],
    }

    def __init__(
        self,
        output_dir: Path = Path("./doha_cases"),
        rate_limit: float = 2.0,  # seconds between requests (increased for politeness)
        user_agent: str = None
    ):
        if not HAS_REQUESTS:
            raise ImportError("requests and beautifulsoup4 required. Install with: pip install requests beautifulsoup4")

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.rate_limit = rate_limit
        self.session = requests.Session()

        # Use realistic browser headers to avoid bot detection
        if user_agent is None:
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        self._last_request = 0
        self.max_retries = 3

    def _rate_limited_get(self, url: str, **kwargs) -> requests.Response:
        """Make a rate-limited GET request with retry logic"""
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)

        logger.debug(f"Fetching: {url}")

        # Retry logic for handling temporary failures
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=30, **kwargs)
                self._last_request = time.time()

                # If we get a 403, wait longer and retry
                if response.status_code == 403:
                    if attempt < self.max_retries - 1:
                        wait_time = (attempt + 1) * 5  # Progressive backoff
                        logger.warning(f"Got 403 for {url}, waiting {wait_time}s before retry {attempt + 1}/{self.max_retries}")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"Failed with 403 after {self.max_retries} attempts: {url}")

                return response

            except requests.RequestException as e:
                if attempt < self.max_retries - 1:
                    wait_time = (attempt + 1) * 3
                    logger.warning(f"Request failed: {e}, retrying in {wait_time}s")
                    time.sleep(wait_time)
                else:
                    raise

        return response

    def discover_available_years(self) -> List[int]:
        """
        Discover all available years from the DOHA website

        Returns:
            List of years with available cases
        """
        available_years = []

        # Try recent years (2015-2026)
        current_year = datetime.now().year
        for year in range(2015, current_year + 2):
            url = self.DOHA_YEAR_PATTERN.format(year=year)
            try:
                response = self._rate_limited_get(url)
                if response.status_code == 200:
                    available_years.append(year)
                    logger.info(f"Year {year} is available")
                elif response.status_code == 404:
                    logger.debug(f"Year {year} not found (404)")
                elif response.status_code == 403:
                    logger.warning(f"Access denied for year {year} (403) - may need different access method")
                    # Still add it, might work later or from different network
                    available_years.append(year)
            except requests.RequestException as e:
                logger.debug(f"Could not check year {year}: {e}")

        # Also check archived years section
        try:
            response = self._rate_limited_get(self.DOHA_ARCHIVE_BASE)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                for a in soup.find_all('a', href=True):
                    # Look for year patterns in archive links
                    year_match = re.search(r'(\d{4})-ISCR', a['href'])
                    if year_match:
                        year = int(year_match.group(1))
                        if year not in available_years:
                            available_years.append(year)
                            logger.info(f"Found archived year {year}")
        except requests.RequestException as e:
            logger.warning(f"Could not check archived years: {e}")

        available_years.sort()
        logger.info(f"Discovered {len(available_years)} available years: {available_years}")
        return available_years

    def get_case_links(self, year: int, is_archived: bool = None) -> List[Tuple[str, str]]:
        """
        Get links to case decisions for a given year

        Args:
            year: The year to scrape
            is_archived: Whether to use archived URL pattern (auto-detect if None)

        Returns:
            List of (case_number, url) tuples
        """
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

        try:
            response = self._rate_limited_get(url)
            response.raise_for_status()

            if response.status_code == 403:
                logger.error(f"Access denied (403) for {year}. DOHA website may be blocking automated access.")
                logger.info("Consider: 1) Running from different network, 2) Manual download, 3) Contact DOHA for bulk access")
                return []

        except requests.RequestException as e:
            logger.error(f"Failed to fetch case list for {year}: {e}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')

        links = []
        # Look for FileId links which point to individual cases
        for a in soup.find_all('a', href=True):
            href = a['href']

            # New structure uses /FileId/{number}/ pattern
            if '/FileId/' in href:
                # Extract FileId number
                file_id_match = re.search(r'/FileId/(\d+)', href)
                if file_id_match:
                    file_id = file_id_match.group(1)
                    # Use FileId as case identifier
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
                    # Make absolute URL
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

    def scrape_case_html(self, url: str) -> Optional[str]:
        """Scrape case text from HTML page"""
        try:
            response = self._rate_limited_get(url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Remove script and style elements
            for element in soup(['script', 'style', 'nav', 'header', 'footer']):
                element.decompose()

            # Get main content
            main = soup.find('main') or soup.find('article') or soup.find('body')
            if main:
                return main.get_text(separator='\n', strip=True)
            return soup.get_text(separator='\n', strip=True)

        except Exception as e:
            logger.error(f"Failed to scrape HTML from {url}: {e}")
            return None

    def scrape_case_pdf(self, url: str) -> Optional[str]:
        """Scrape case text from PDF"""
        if not HAS_PDF:
            logger.warning("PyMuPDF not installed, cannot parse PDF")
            return None

        try:
            response = self._rate_limited_get(url)
            response.raise_for_status()

            # Parse PDF from bytes
            doc = fitz.open(stream=response.content, filetype="pdf")
            text_parts = []

            for page in doc:
                text_parts.append(page.get_text())

            doc.close()
            return "\n".join(text_parts)

        except Exception as e:
            logger.error(f"Failed to scrape PDF from {url}: {e}")
            return None

    def scrape_case(self, case_number: str, url: str) -> Optional[ScrapedCase]:
        """
        Scrape a single case

        Args:
            case_number: DOHA case number
            url: URL to the case decision

        Returns:
            ScrapedCase if successful, None otherwise
        """
        # Determine content type and scrape accordingly
        if url.lower().endswith('.pdf'):
            text = self.scrape_case_pdf(url)
        else:
            text = self.scrape_case_html(url)

        if not text:
            return None

        # Parse the case text
        return self.parse_case_text(case_number, text, url)

    def parse_case_text(self, case_number: str, text: str, source_url: str) -> ScrapedCase:
        """
        Parse case text to extract structured information

        Args:
            case_number: DOHA case number
            text: Full text of the decision
            source_url: URL where case was found

        Returns:
            ScrapedCase with extracted information
        """
        # Detect if this is an appeal or hearing decision
        is_appeal = self._is_appeal_document(text)

        # Extract date
        date = self._extract_date(text)

        # Extract outcome
        outcome = self._extract_outcome(text)

        # Extract guidelines (relevant for both types)
        guidelines = self._extract_guidelines(text)

        # Extract judge name (single judge for hearings, Appeal Board chair for appeals)
        judge = self._extract_judge(text)

        # Create summary
        summary = self._create_summary(text)

        if is_appeal:
            # Appeal Board decision - use appeal-specific extraction
            return ScrapedCase(
                case_number=case_number,
                date=date,
                outcome=outcome,
                guidelines=guidelines,
                summary=summary,
                full_text=text,
                sor_allegations=[],  # Not applicable for appeals
                mitigating_factors=[],  # Not applicable for appeals
                judge=judge,
                source_url=source_url,
                formal_findings={},  # Not applicable for appeals
                case_type="appeal",
                appeal_board_members=self._extract_appeal_board_members(text),
                judges_findings_of_fact=self._extract_judges_findings_of_fact(text),
                judges_analysis=self._extract_judges_analysis(text),
                discussion=self._extract_discussion(text),
                order=self._extract_order(text),
            )
        else:
            # Hearing decision - use hearing-specific extraction
            sor_allegations = self._extract_sor_allegations(text)
            mitigating_factors = self._extract_mitigating_factors(text)
            formal_findings = self._extract_formal_findings(text)

            return ScrapedCase(
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
                formal_findings=formal_findings,
                case_type="hearing",
            )

    def _extract_date(self, text: str) -> str:
        """Extract decision date from case text"""
        # Common date patterns
        patterns = [
            r'(?:Date|Dated)[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
            r'(\d{1,2}/\d{1,2}/\d{4})',
            r'([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
        ]

        for pattern in patterns:
            match = re.search(pattern, text[:2000], re.IGNORECASE)
            if match:
                return match.group(1)

        return "Unknown"

    def _extract_outcome(self, text: str) -> str:
        """Extract case outcome from text.

        For hearing decisions: searches the last portion of the document.
        For appeal board decisions: checks the Order section and contextual patterns.
        Returns the outcome with the LAST (rightmost) match position.
        """
        text_lower = text.lower()

        # Check if this is an Appeal Board decision
        is_appeal = self._is_appeal_document(text)

        if is_appeal:
            # Appeal Board-specific outcome extraction
            return self._extract_appeal_outcome(text)

        # For hearing decisions: search in the last 3000 characters
        search_text = text_lower[-3000:]

        # Track the last (rightmost) match position for each outcome
        last_match_positions = {}

        for outcome, patterns in self.OUTCOME_PATTERNS.items():
            for pattern in patterns:
                # Find ALL matches and track the last one
                for match in re.finditer(pattern, search_text, re.IGNORECASE):
                    pos = match.end()
                    if outcome not in last_match_positions or pos > last_match_positions[outcome]:
                        last_match_positions[outcome] = pos

        if not last_match_positions:
            return "UNKNOWN"

        # Return the outcome with the latest (rightmost) match
        # This handles cases where earlier text might mention outcomes in context
        # but the actual decision is at the end
        return max(last_match_positions, key=last_match_positions.get)

    def _is_appeal_document(self, text: str) -> bool:
        """Detect if this is an Appeal Board decision vs a Hearing decision."""
        # Check for Appeal Board-specific markers in first 2500 chars (increased range)
        header_text = text[:2500].lower()
        appeal_markers = [
            'appeal board',
            'appeal board decision',
            'applicant appealed',
            'government appealed',
            'department counsel appealed',  # Common in appeals
            'cross-appeal',
            'the board gives deference',  # Unique to appeal documents
            'favorable decision reversed',  # In digest section
            'adverse decision reversed',    # In digest section
            'decision is affirmed',         # In digest section
            'decision is reversed',         # In digest section
        ]
        return any(marker in header_text for marker in appeal_markers)

    def _extract_appeal_outcome(self, text: str) -> str:
        """Extract outcome specifically for Appeal Board decisions.

        Appeal Board outcomes are determined by:
        1. The underlying decision (granted/denied by Administrative Judge)
        2. The Appeal Board's action (affirmed/reversed/remanded)

        Common patterns:
        - "The adverse decision is AFFIRMED" → DENIED (denial upheld)
        - "The favorable decision is AFFIRMED" → GRANTED (grant upheld)
        - "The decision is AFFIRMED" → check context for underlying outcome
        - "adverse decision is sustainable" → DENIED
        - Case remanded → REMANDED
        """
        text_lower = text.lower()

        # Check the Order section (last 1500 chars) for explicit outcome
        order_text = text_lower[-1500:]

        # Pattern 1: Explicit "adverse decision" or "favorable decision" in Order
        if re.search(r'the\s+adverse\s+decision\s+is\s+affirmed', order_text):
            return "DENIED"
        if re.search(r'the\s+favorable\s+decision\s+is\s+affirmed', order_text):
            return "GRANTED"
        if re.search(r'the\s+adverse\s+decision\s+is\s+reversed', order_text):
            return "GRANTED"
        if re.search(r'the\s+favorable\s+decision\s+is\s+reversed', order_text):
            return "DENIED"

        # Pattern 2: Check for remand
        if re.search(r'(?:case|decision)\s+is\s+remanded', order_text):
            return "REMANDED"
        if re.search(r'remanded\s+(?:to|for)', order_text):
            return "REMANDED"

        # Pattern 3: "The decision is AFFIRMED" - need to determine underlying decision
        if re.search(r'the\s+decision\s+is\s+affirmed', order_text):
            # Look for context about what was the underlying decision
            # Check the body text for "denied" or "granted" near "eligibility"
            body_text = text_lower[:len(text_lower) - 1500]

            # Look for phrases indicating the AJ denied eligibility
            # Use .{0,10} to handle possessives, quotes, newlines between words
            # Be specific to avoid false positives from discussion of the decision
            denial_indicators = [
                r'(?:administrative\s+)?judge.{0,100}denied\s+applicant.{0,10}(?:request\s+for\s+)?(?:a\s+)?(?:security\s+)?clearance',
                r'denied\s+applicant.{0,10}(?:request\s+for\s+)?(?:a\s+)?(?:security\s+)?clearance',
                r'denied\s+applicant.{0,10}eligibility',
                r'denied\s+(?:the\s+)?eligibility',
                r'decision\s+(?:of\s+the\s+)?(?:administrative\s+)?judge\s+denying',
                r'judge\s+(?:issued\s+)?(?:an?\s+)?adverse\s+decision',  # More specific
                r'judge\s+denied',  # More specific
                r'unfavorable\s+(?:security\s+)?(?:clearance\s+)?decision',
                # Applicant appealed (usually against denial)
                r'applicant\s+(?:has\s+)?appealed',
                # Common language when applicant's appeal is rejected
                r'applicant\s+failed\s+to\s+(?:establish|demonstrate)',
                r'applicant.{0,10}arguments\s+(?:are|do)\s+not',
                # Decision is sustainable (usually used when affirming denial)
                r'decision\s+is\s+sustainable',
            ]

            # Look for phrases indicating the AJ granted eligibility
            # Use .{0,10} to handle possessives, quotes, newlines between words
            grant_indicators = [
                r'(?:administrative\s+)?judge.{0,100}granted\s+applicant.{0,10}(?:request\s+for\s+)?(?:a\s+)?(?:security\s+)?clearance',
                r'granted\s+applicant.{0,10}(?:request\s+for\s+)?(?:a\s+)?(?:security\s+)?clearance',
                r'granted\s+applicant.{0,10}eligibility',
                r'granted\s+(?:the\s+)?eligibility',
                r'decision\s+(?:of\s+the\s+)?(?:administrative\s+)?judge\s+granting',
                r'judge.{0,10}(?:favorable\s+)?decision\s+(?:granting|was\s+to\s+grant)',
                r'favorable\s+(?:security\s+)?(?:clearance\s+)?decision',
                # Government appealed (usually against grant)
                r'(?:department\s+counsel|government)\s+(?:has\s+)?appealed',
            ]

            for pattern in denial_indicators:
                if re.search(pattern, body_text, re.DOTALL):
                    return "DENIED"  # Denial affirmed = still denied

            for pattern in grant_indicators:
                if re.search(pattern, body_text, re.DOTALL):
                    return "GRANTED"  # Grant affirmed = still granted

        # Pattern 4: "The decision is REVERSED" - opposite of underlying
        if re.search(r'the\s+decision\s+is\s+reversed', order_text):
            body_text = text_lower[:len(text_lower) - 1500]

            # If underlying was denial, reversed means granted
            # Use .{0,10} to handle possessives, quotes, newlines between words
            # Be specific to avoid false positives from discussion of the decision
            denial_indicators = [
                r'(?:administrative\s+)?judge.{0,100}denied\s+applicant.{0,10}(?:request\s+for\s+)?(?:a\s+)?(?:security\s+)?clearance',
                r'denied\s+applicant.{0,10}(?:request\s+for\s+)?(?:a\s+)?(?:security\s+)?clearance',
                r'denied\s+applicant.{0,10}eligibility',
                r'judge\s+(?:issued\s+)?(?:an?\s+)?adverse\s+decision',  # More specific: "judge issued an adverse decision"
                r'judge\s+denied',  # More specific: "judge denied"
                r'adverse\s+findings\s+are\s+not\s+sustainable',
            ]

            for pattern in denial_indicators:
                if re.search(pattern, body_text, re.DOTALL):
                    return "GRANTED"  # Denial reversed = now granted

            # If underlying was grant, reversed means denied
            # Use .{0,10} to handle possessives, quotes, newlines between words
            grant_indicators = [
                r'(?:administrative\s+)?judge.{0,100}granted\s+applicant.{0,10}(?:request\s+for\s+)?(?:a\s+)?(?:security\s+)?clearance',
                r'granted\s+applicant.{0,10}(?:request\s+for\s+)?(?:a\s+)?(?:security\s+)?clearance',
                r'granted\s+applicant.{0,10}eligibility',
                r'decision\s+(?:of\s+the\s+)?(?:administrative\s+)?judge\s+granting',
                r'judge.{0,10}favorable\s+(?:findings|decision)',
                r'favorable\s+(?:security\s+)?(?:clearance\s+)?decision',
                # Appeal Board language indicating they disagree with a favorable decision
                r'record\s+(?:evidence\s+)?(?:is\s+)?not\s+sufficient\s+to\s+mitigate',
                r'not\s+sufficient\s+to\s+mitigate\s+the\s+government',
                r'decision\s+runs\s+contrary\s+to\s+the\s+(?:weight\s+of\s+the\s+)?record',
                r'favorable\s+(?:security\s+)?(?:clearance\s+)?determination\s+cannot\s+be\s+sustained',
                r'cannot\s+be\s+sustained',
            ]

            for pattern in grant_indicators:
                if re.search(pattern, body_text, re.DOTALL):
                    return "DENIED"  # Grant reversed = now denied

        # Pattern 5: Check for "is sustainable" language (means affirmed)
        if re.search(r'(?:adverse\s+)?decision[^.]*is\s+sustainable', order_text):
            # Check if it's an adverse decision
            if re.search(r'adverse\s+decision[^.]*is\s+sustainable', order_text):
                return "DENIED"
            if re.search(r'(?:denying|denial)[^.]*is\s+sustainable', text_lower):
                return "DENIED"
            if re.search(r'(?:granting|grant)[^.]*is\s+sustainable', text_lower):
                return "GRANTED"

        # Pattern 6: Check earlier in document (DIGEST section) for appeal patterns
        digest_text = text_lower[:2000]

        if re.search(r'adverse\s+decision\s+(?:is\s+)?affirmed', digest_text):
            return "DENIED"
        if re.search(r'favorable\s+decision\s+(?:is\s+)?affirmed', digest_text):
            return "GRANTED"
        if re.search(r'adverse\s+decision\s+(?:is\s+)?reversed', digest_text):
            return "GRANTED"
        if re.search(r'favorable\s+decision\s+(?:is\s+)?reversed', digest_text):
            return "DENIED"
        if re.search(r'case\s+(?:is\s+)?remanded', digest_text):
            return "REMANDED"

        return "UNKNOWN"

    def _extract_guidelines(self, text: str) -> List[str]:
        """Extract relevant guidelines from case text"""
        guidelines = []

        for code, pattern in self.GUIDELINE_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                guidelines.append(code)

        return guidelines

    def _extract_sor_allegations(self, text: str) -> List[str]:
        """Extract SOR (Statement of Reasons) allegations"""
        allegations = []

        # Look for SOR section
        sor_match = re.search(
            r'Statement\s+of\s+Reasons.*?(?:FINDINGS|ANALYSIS|\n\n\n)',
            text,
            re.IGNORECASE | re.DOTALL
        )

        if sor_match:
            sor_text = sor_match.group(0)

            # Extract numbered allegations
            allegation_matches = re.findall(
                r'(?:^\s*\d+\.\s*[a-z]?\.|SOR\s*¶\s*\d+\.[a-z]?)\s*(.+?)(?=\n\s*\d+\.|$)',
                sor_text,
                re.MULTILINE | re.IGNORECASE
            )

            allegations = [a.strip()[:500] for a in allegation_matches if len(a.strip()) > 10]

        return allegations[:10]  # Limit to 10

    def _extract_mitigating_factors(self, text: str) -> List[str]:
        """Extract mitigating factors mentioned in the decision"""
        mitigating = []

        # Look for mitigating conditions
        mit_patterns = [
            r'(?:mitigating\s+condition|MC|AG\s*¶\s*\d+\([a-z]\)).*?(?:\n|$)',
            r'(?:in\s+mitigation|mitigating\s+factor).*?(?:\n\n|$)',
        ]

        for pattern in mit_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                clean = match.strip()[:300]
                if len(clean) > 20 and clean not in mitigating:
                    mitigating.append(clean)

        return mitigating[:5]  # Limit to 5

    def _extract_formal_findings(self, text: str) -> Dict[str, dict]:
        """Extract formal findings section with per-guideline and per-subparagraph outcomes.

        Returns a dict mapping guideline codes to their findings:
        {
            "F": {
                "guideline_name": "Financial Considerations",
                "overall": "AGAINST",  # or "FOR"
                "subparagraphs": [
                    {"para": "1.a-b", "finding": "Against"},
                    {"para": "1.c-f", "finding": "For"},
                ]
            },
            ...
        }
        """
        findings = {}

        # Find the Formal Findings section (handles both "Formal Finding" singular and "Formal Findings" plural)
        # Use negative lookbehind to avoid matching "conclusions" in middle of sentence
        # Match "Conclusion" only when it appears as a section header (preceded by newline)
        formal_match = re.search(
            r'Formal\s+Findings?.*?(?=\n\s*Conclusions?\s*\n|$)',
            text,
            re.IGNORECASE | re.DOTALL
        )

        if not formal_match:
            return findings

        formal_text = formal_match.group(0)

        # Guideline name mapping
        guideline_names = {
            'A': 'Allegiance to the United States',
            'B': 'Foreign Influence',
            'C': 'Foreign Preference',
            'D': 'Sexual Behavior',
            'E': 'Personal Conduct',
            'F': 'Financial Considerations',
            'G': 'Alcohol Consumption',
            'H': 'Drug Involvement',
            'I': 'Psychological Conditions',
            'J': 'Criminal Conduct',
            'K': 'Handling Protected Information',
            'L': 'Outside Activities',
            'M': 'Use of Information Technology',
        }

        # Reverse mapping: guideline name keywords to code
        name_to_code = {
            'allegiance': 'A',
            'foreign influence': 'B',
            'foreign preference': 'C',
            'sexual': 'D',
            'personal conduct': 'E',
            'financial': 'F',
            'alcohol': 'G',
            'drug': 'H',
            'psychological': 'I',
            'criminal': 'J',
            'handling protected': 'K',
            'outside activities': 'L',
            'information technology': 'M',
        }

        # Pattern 1: "Paragraph 1, Guideline F:" or "Paragraph 1. Guideline F:" or "Paragraph 1 (Guideline B):"
        para_pattern = r'Paragraph\s+(\d+)[.,]?\s*(?:\()?Guideline\s+([A-M])(?:\s*\([^)]+\))?\)?[:\s]*(FOR|AGAINST)\s*APPLICANT'

        # Pattern 2: "GUIDELINE F (FINANCIAL CONSIDERATIONS): AGAINST APPLICANT"
        alt_pattern = r'GUIDELINE\s+([A-M])\s*\([^)]+\)\s*:\s*(FOR|AGAINST)\s*APPLICANT'

        # Try Pattern 1 first (more common)
        for match in re.finditer(para_pattern, formal_text, re.IGNORECASE):
            para_num = match.group(1)
            guideline = match.group(2).upper()
            overall = match.group(3).upper()

            # Get section text until next Paragraph/Guideline or end
            start_pos = match.end()
            next_section = re.search(r'(?:Paragraph\s+\d+|GUIDELINE\s+[A-M])', formal_text[start_pos:], re.IGNORECASE)
            if next_section:
                section_text = formal_text[start_pos:start_pos + next_section.start()]
            else:
                section_text = formal_text[start_pos:]

            subparagraphs = self._extract_subparagraphs(section_text, para_num)

            findings[guideline] = {
                "guideline_name": guideline_names.get(guideline, "Unknown"),
                "overall": overall,
                "subparagraphs": subparagraphs
            }

        # Try Pattern 2 for any guidelines not yet found
        for match in re.finditer(alt_pattern, formal_text, re.IGNORECASE):
            guideline = match.group(1).upper()
            if guideline in findings:
                continue  # Already found with Pattern 1

            overall = match.group(2).upper()

            # Get section text until next GUIDELINE or end
            start_pos = match.end()
            next_section = re.search(r'(?:GUIDELINE\s+[A-M]|Paragraph\s+\d+)', formal_text[start_pos:], re.IGNORECASE)
            if next_section:
                section_text = formal_text[start_pos:start_pos + next_section.start()]
            else:
                section_text = formal_text[start_pos:]

            # For alt pattern, paragraph number is usually 1, 2, 3 based on guideline order
            para_num = str(len(findings) + 1)
            subparagraphs = self._extract_subparagraphs(section_text, para_num)

            findings[guideline] = {
                "guideline_name": guideline_names.get(guideline, "Unknown"),
                "overall": overall,
                "subparagraphs": subparagraphs
            }

        # Pattern 3: "Paragraph 1, Personal Conduct:" or "Paragraph 1, Financial Considerations:"
        # Uses guideline name instead of "Guideline X"
        name_pattern = r'Paragraph\s+(\d+)[.,]?\s*([A-Za-z][A-Za-z\s]+?)\s*[:\s]*(FOR|AGAINST)\s*APPLICANT'

        for match in re.finditer(name_pattern, formal_text, re.IGNORECASE):
            para_num = match.group(1)
            name_text = match.group(2).strip().lower()
            overall = match.group(3).upper()

            # Map the name to a guideline code
            guideline = None
            for keyword, code in name_to_code.items():
                if keyword in name_text:
                    guideline = code
                    break

            if not guideline or guideline in findings:
                continue  # Couldn't identify or already found

            # Get section text until next Paragraph or end
            start_pos = match.end()
            next_section = re.search(r'Paragraph\s+\d+', formal_text[start_pos:], re.IGNORECASE)
            if next_section:
                section_text = formal_text[start_pos:start_pos + next_section.start()]
            else:
                section_text = formal_text[start_pos:]

            subparagraphs = self._extract_subparagraphs(section_text, para_num)

            findings[guideline] = {
                "guideline_name": guideline_names.get(guideline, "Unknown"),
                "overall": overall,
                "subparagraphs": subparagraphs
            }

        # Pattern 4: "[Guideline Name] Security Concern:" format
        # e.g., "Financial Considerations Security Concern: AGAINST APPLICANT"
        # e.g., "Foreign Influence Security Concern: FOR APPLICANT"
        concern_pattern = r'([A-Za-z][A-Za-z\s]+?)\s*(?:Security\s+)?Concern\s*[:\s]*(FOR|AGAINST)\s*APPLICANT'

        for match in re.finditer(concern_pattern, formal_text, re.IGNORECASE):
            name_text = match.group(1).strip().lower()
            overall = match.group(2).upper()

            # Map the name to a guideline code
            guideline = None
            for keyword, code in name_to_code.items():
                if keyword in name_text:
                    guideline = code
                    break

            if not guideline or guideline in findings:
                continue  # Couldn't identify or already found

            # Get section text until next Concern section or Conclusion
            start_pos = match.end()
            next_section = re.search(r'(?:[A-Za-z\s]+Security\s+)?Concern\s*:|Conclusion', formal_text[start_pos:], re.IGNORECASE)
            if next_section:
                section_text = formal_text[start_pos:start_pos + next_section.start()]
            else:
                section_text = formal_text[start_pos:]

            # Determine paragraph number based on order found
            para_num = str(len(findings) + 1)
            subparagraphs = self._extract_subparagraphs(section_text, para_num)

            findings[guideline] = {
                "guideline_name": guideline_names.get(guideline, "Unknown"),
                "overall": overall,
                "subparagraphs": subparagraphs
            }

        return findings

    def _extract_subparagraphs(self, section_text: str, para_num: str) -> List[dict]:
        """Extract subparagraph findings from a section of text.

        Handles various formats:
        - "Subparagraph 1.a: For Applicant"
        - "Subparagraphs 1.a-1.b: Against Applicant"
        - "Subparagraphs 1.a - 1.f: For Applicant"
        - "Subparagraphs a-b, d: Against Applicant" (letters only)
        """
        subparagraphs = []

        # Multiple patterns to catch different formats
        sub_patterns = [
            # "Subparagraphs 1.a-1.b:" or "Subparagraph 1.a:"
            r'Subparagraphs?\s+([\d]+\.[\w]+(?:\s*[-–—]\s*[\d]*\.?[\w]+)?)\s*[:\s]+\s*(For|Against)\s*Applicant',
            # "Subparagraphs 1.a - 1.b:" with spaces around dash
            r'Subparagraphs?\s+([\d]+\.[\w]+\s*[-–—]\s*[\d]+\.[\w]+)\s*[:\s]+\s*(For|Against)\s*Applicant',
            # Simpler: just look for the pattern with finding on next line
            r'Subparagraphs?\s+([\d]+\.[\w]+(?:[-–—\s]+[\d]*\.?[\w]+)?)[:\s]*\n\s*(For|Against)\s*Applicant',
            # Letters only: "Subparagraphs a-b, d:" or "Subparagraph a:"
            r'Subparagraphs?\s+([a-z](?:\s*[-–—,]\s*[a-z])*)\s*[:\s]+\s*(For|Against)\s*Applicant',
            # Letters only with newline
            r'Subparagraphs?\s+([a-z](?:[-–—,\s]+[a-z])*)[:\s]*\n\s*(For|Against)\s*Applicant',
        ]

        seen = set()
        for pattern in sub_patterns:
            for sub_match in re.finditer(pattern, section_text, re.IGNORECASE):
                para_ref = sub_match.group(1).strip()
                finding = sub_match.group(2).capitalize()

                # Normalize the para reference
                para_ref = re.sub(r'\s+', '', para_ref)  # Remove internal spaces

                # If it's just letters (no number), prefix with para_num
                if re.match(r'^[a-z]', para_ref, re.IGNORECASE) and '.' not in para_ref:
                    para_ref = f"{para_num}.{para_ref}"

                # Create unique key to avoid duplicates
                key = (para_ref, finding)
                if key in seen:
                    continue
                seen.add(key)

                subparagraphs.append({
                    "para": para_ref,
                    "finding": finding
                })

        return subparagraphs

    def _extract_judge(self, text: str) -> str:
        """Extract administrative judge name from the end of the document"""
        # Search in the last 1500 characters where the judge signature typically appears
        search_text = text[-1500:]

        # Name character class: letters, apostrophes, accented chars, hyphens
        name_char = r"[A-Za-z'\u2019\u00C0-\u00FF-]"
        # A name part: capital letter followed by name chars
        name_part = rf"[A-Z]{name_char}*"
        # Optional middle: initial (A.) or full name (Le'i)
        middle_opt = rf"(?:\s+{name_part}\.?)?"
        # Optional suffix: II, III, IV, Jr., Sr. (with optional comma before)
        suffix_opt = r"(?:[,\s]+(?:II|III|IV|Jr\.?|Sr\.?))?"

        patterns = [
            # Full name on line before "Administrative Judge" (allowing page numbers/whitespace in between)
            # Matches: "Roger C. Wesley", "Candace Le'i Garcia", "Claude R. Heiny II"
            rf'({name_part}{middle_opt}\s+{name_part}{suffix_opt})\s*\n[\s\d]*\.?Administrative\s+Judge',
            # All caps name: "ROGER C. WESLEY" or "JOHN GRATTAN METZ, JR"
            r'([A-Z]+(?:\s+[A-Z]\.?)?\s+[A-Z]+(?:[,\s]+(?:II|III|IV|JR\.?|SR\.?)?)?)\s*\n[\s\d]*\.?Administrative\s+Judge',
            # Name with "Administrative Judge" on same line
            rf'({name_part}{middle_opt}\s+{name_part})[\s,]+Administrative\s+Judge',
            # After underscore line (signature line)
            rf'_{5,}\s*\n\s*({name_part}{middle_opt}\s+{name_part}{suffix_opt})\s*\n',
            # Reversed format: "Administrative Judge" followed by name on next line
            rf'Administrative\s+Judge\s*\n\s*({name_part}{middle_opt}\s+{name_part}{suffix_opt})',
        ]

        for pattern in patterns:
            match = re.search(pattern, search_text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Title case the name if it's all caps
                if name.isupper():
                    parts = name.split()
                    titled_parts = []
                    for part in parts:
                        if part in ('II', 'III', 'IV', 'JR', 'JR.', 'SR', 'SR.'):
                            titled_parts.append(part if part in ('II', 'III', 'IV') else part.title())
                        elif len(part) == 2 and part[1] == '.':
                            titled_parts.append(part)  # Keep middle initial as-is
                        else:
                            titled_parts.append(part.title())
                    name = ' '.join(titled_parts)
                return name

        return "Unknown"

    def _extract_appeal_board_members(self, text: str) -> List[str]:
        """Extract Appeal Board member names from an appeal decision.

        Appeal Board decisions are signed by 3 judges (Chair and 2 Members).
        """
        members = []

        # Search in the last 1500 characters where signatures appear
        search_text = text[-1500:]

        # Pattern for signed Appeal Board members
        # Formats:
        # "Signed: Moira Modzelewski\nMoira Modzelewski\nAdministrative Judge\nChair, Appeal Board"
        # "Signed: Gregg A. Cervi\nGregg A. Cervi\nAdministrative Judge\nMember, Appeal Board"

        # Name character class
        name_char = r"[A-Za-z'\u2019\u00C0-\u00FF-]"
        name_part = rf"[A-Z]{name_char}*"
        middle_opt = rf"(?:\s+{name_part}\.?)?"
        suffix_opt = r"(?:[,\s]+(?:II|III|IV|Jr\.?|Sr\.?))?"

        # Pattern to find names followed by "Administrative Judge" and "Appeal Board"
        pattern = rf'Signed:\s*({name_part}{middle_opt}\s+{name_part}{suffix_opt})\s*\n'

        matches = re.findall(pattern, search_text, re.IGNORECASE)
        for match in matches:
            name = match.strip()
            if name and name not in members:
                members.append(name)

        # Alternative: look for names above "Administrative Judge" + "Appeal Board"
        if not members:
            pattern2 = rf'({name_part}{middle_opt}\s+{name_part}{suffix_opt})\s*\n\s*Administrative\s+Judge\s*\n\s*(?:Chair|Member),?\s*Appeal\s+Board'
            matches = re.findall(pattern2, search_text, re.IGNORECASE)
            for match in matches:
                name = match.strip()
                if name and name not in members:
                    members.append(name)

        return members

    def _extract_judges_findings_of_fact(self, text: str) -> str:
        """Extract the 'Judge's Findings of Fact' section from an appeal decision.

        This section summarizes what the Administrative Judge found in the original hearing.
        """
        # Look for the section header
        patterns = [
            r"Judge['\u2019]?s\s+Findings?\s+of\s+Fact\s*(.*?)(?=Judge['\u2019]?s\s+Analysis|Discussion|Conclusion|Order|\Z)",
            r"Findings?\s+of\s+Fact\s*(.*?)(?=Analysis|Discussion|Conclusion|Order|\Z)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                content = match.group(1).strip()
                # Clean up and limit length
                content = re.sub(r'\s+', ' ', content)
                return content[:3000] if len(content) > 3000 else content

        return ""

    def _extract_judges_analysis(self, text: str) -> str:
        """Extract the 'Judge's Analysis' section from an appeal decision.

        This section summarizes how the Administrative Judge analyzed the case.
        """
        patterns = [
            r"Judge['\u2019]?s\s+Analysis\s*(.*?)(?=Discussion|Conclusion|Order|\Z)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                content = match.group(1).strip()
                content = re.sub(r'\s+', ' ', content)
                return content[:2000] if len(content) > 2000 else content

        return ""

    def _extract_discussion(self, text: str) -> str:
        """Extract the 'Discussion' section from an appeal decision.

        This is the Appeal Board's analysis of the appeal arguments.
        """
        patterns = [
            r"\bDiscussion\b\s*(.*?)(?=Conclusion|Order|\Z)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                content = match.group(1).strip()
                content = re.sub(r'\s+', ' ', content)
                return content[:5000] if len(content) > 5000 else content

        return ""

    def _extract_order(self, text: str) -> str:
        """Extract the 'Order' section from an appeal decision.

        This contains the Appeal Board's final decision (AFFIRMED, REVERSED, REMANDED).
        """
        # Look for Order section at the end
        patterns = [
            r"\bOrder\b\s*(.*?)(?=Signed:|Administrative\s+Judge|\Z)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text[-2000:], re.IGNORECASE | re.DOTALL)
            if match:
                content = match.group(1).strip()
                # Extract just the key decision text
                content = re.sub(r'\s+', ' ', content)
                # Typically short like "The decision is AFFIRMED."
                return content[:500] if len(content) > 500 else content

        # Fallback: look for specific order language in last portion
        order_patterns = [
            r'The\s+(?:adverse\s+)?(?:favorable\s+)?decision\s+is\s+(AFFIRMED|REVERSED|REMANDED)',
            r'(?:Case|Decision)\s+is\s+(REMANDED)',
        ]

        for pattern in order_patterns:
            match = re.search(pattern, text[-1500:], re.IGNORECASE)
            if match:
                return match.group(0)

        return ""

    def _create_summary(self, text: str) -> str:
        """Create a summary of the case"""
        # Try to find the findings or analysis section
        sections = [
            r'FINDINGS\s+OF\s+FACT.*?(?=POLICIES|ANALYSIS|\Z)',
            r'ANALYSIS.*?(?=CONCLUSION|\Z)',
            r'STATEMENT\s+OF\s+THE\s+CASE.*?(?=FINDINGS|\Z)',
        ]

        for pattern in sections:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                section_text = match.group(0)
                # Clean up and truncate
                summary = re.sub(r'\s+', ' ', section_text).strip()
                return summary[:1500]

        # Fallback: use first 1500 chars
        return re.sub(r'\s+', ' ', text[:1500]).strip()

    def get_2016_and_prior_links(self) -> List[Tuple[str, str]]:
        """
        Get links from all "2016 and Prior" pages

        Returns:
            List of (case_number, url) tuples
        """
        all_links = []

        for page in range(1, self.DOHA_2016_PRIOR_PAGES + 1):
            url = self.DOHA_2016_PRIOR_PATTERN.format(page=page)
            logger.info(f"Fetching 2016 and Prior page {page}/{self.DOHA_2016_PRIOR_PAGES}...")

            try:
                response = self._rate_limited_get(url)
                if response.status_code != 200:
                    logger.warning(f"Failed to fetch page {page}: HTTP {response.status_code}")
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')

                page_links = []
                for a in soup.find_all('a', href=True):
                    href = a['href']

                    # Look for FileId links
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

                    # Also look for old-style case numbers
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

                # Remove duplicates within this page
                seen = set()
                for case_num, case_url in page_links:
                    if case_num not in seen:
                        seen.add(case_num)
                        all_links.append((case_num, case_url))

                logger.info(f"Found {len(page_links)} cases on page {page}")

            except Exception as e:
                logger.error(f"Error fetching 2016 and Prior page {page}: {e}")

        logger.info(f"Found total of {len(all_links)} cases in 2016 and Prior pages")
        return all_links

    def scrape_years(
        self,
        start_year: int,
        end_year: int,
        max_cases_per_year: Optional[int] = None,
        include_2016_and_prior: bool = False
    ) -> List[ScrapedCase]:
        """
        Scrape cases for a range of years

        Args:
            start_year: Starting year (4-digit)
            end_year: Ending year (4-digit)
            max_cases_per_year: Optional limit per year
            include_2016_and_prior: If True, also scrape "2016 and Prior" archives

        Returns:
            List of scraped cases
        """
        all_cases = []

        # Scrape requested years
        for year in range(start_year, end_year + 1):
            logger.info(f"Scraping cases for year {year}...")

            links = self.get_case_links(year)

            if max_cases_per_year:
                links = links[:max_cases_per_year]

            for case_number, url in links:
                try:
                    case = self.scrape_case(case_number, url)
                    if case:
                        all_cases.append(case)
                        logger.info(f"Scraped case {case_number}: {case.outcome}")
                except Exception as e:
                    logger.error(f"Error scraping case {case_number}: {e}")

            # Save intermediate results after each year
            self._save_cases(all_cases, f"cases_{start_year}_{year}.json")

        # Optionally scrape 2016 and Prior
        if include_2016_and_prior:
            logger.info("Scraping 2016 and Prior cases...")
            prior_links = self.get_2016_and_prior_links()

            if max_cases_per_year:
                prior_links = prior_links[:max_cases_per_year]

            for case_number, url in prior_links:
                try:
                    case = self.scrape_case(case_number, url)
                    if case:
                        all_cases.append(case)
                        logger.info(f"Scraped case {case_number}: {case.outcome}")
                except Exception as e:
                    logger.error(f"Error scraping case {case_number}: {e}")

            # Save final results including prior cases
            self._save_cases(all_cases, f"cases_{start_year}_{end_year}_all.json")

        return all_cases

    def scrape_all_available(self, max_cases_per_year: Optional[int] = None) -> List[ScrapedCase]:
        """
        Scrape all available DOHA cases including current years and archives

        Args:
            max_cases_per_year: Optional limit per year

        Returns:
            List of all scraped cases
        """
        logger.info("Starting comprehensive scrape of all DOHA cases...")

        # Get current year
        current_year = datetime.now().year

        # Scrape recent years (2017-current)
        # Years 2017-2022 are in archives, 2023+ are in current section
        cases = self.scrape_years(
            start_year=2017,
            end_year=current_year + 1,
            max_cases_per_year=max_cases_per_year,
            include_2016_and_prior=True  # Also get all pre-2017 cases
        )

        logger.info(f"Comprehensive scrape complete! Total cases: {len(cases)}")
        return cases

    def _save_cases(self, cases: List[ScrapedCase], filename: str):
        """Save cases to JSON file"""
        output_path = self.output_dir / filename

        with open(output_path, 'w') as f:
            json.dump([c.to_dict() for c in cases], f, indent=2)

        logger.info(f"Saved {len(cases)} cases to {output_path}")

    def load_cases(self, filename: str) -> List[ScrapedCase]:
        """Load cases from JSON file"""
        input_path = self.output_dir / filename

        with open(input_path) as f:
            data = json.load(f)

        return [
            ScrapedCase(**c) for c in data
        ]


class DOHALocalParser:
    """
    Parser for locally downloaded DOHA case files

    Use this when you have already downloaded case PDFs or HTML files.
    """

    def __init__(self, scraper: Optional[DOHAScraper] = None):
        self.scraper = scraper or DOHAScraper()

    def parse_directory(self, directory: Path) -> List[ScrapedCase]:
        """
        Parse all case files in a directory

        Args:
            directory: Path to directory containing case files

        Returns:
            List of parsed cases
        """
        directory = Path(directory)
        cases = []

        # Find all relevant files
        files = list(directory.glob("*.pdf")) + list(directory.glob("*.html")) + list(directory.glob("*.txt"))

        logger.info(f"Found {len(files)} case files in {directory}")

        for file_path in files:
            try:
                case = self.parse_file(file_path)
                if case:
                    cases.append(case)
            except Exception as e:
                logger.error(f"Failed to parse {file_path}: {e}")

        return cases

    def parse_file(self, file_path: Path) -> Optional[ScrapedCase]:
        """Parse a single case file"""
        file_path = Path(file_path)

        # Extract case number from filename
        case_match = re.search(r'(\d{2}-\d+)', file_path.name)
        case_number = case_match.group(1) if case_match else file_path.stem

        # Read file content
        if file_path.suffix.lower() == '.pdf':
            if not HAS_PDF:
                logger.warning(f"Cannot parse PDF {file_path}: PyMuPDF not installed")
                return None
            doc = fitz.open(file_path)
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
        else:
            text = file_path.read_text(encoding='utf-8', errors='ignore')

        # Parse using scraper's parse method
        return self.scraper.parse_case_text(
            case_number=case_number,
            text=text,
            source_url=f"file://{file_path.absolute()}"
        )


def scrape_and_index(
    output_dir: Path,
    start_year: int = 2020,
    end_year: int = 2024,
    max_cases: Optional[int] = None
) -> Path:
    """
    Convenience function to scrape DOHA cases and create an index

    Args:
        output_dir: Directory to store scraped cases and index
        start_year: Starting year
        end_year: Ending year
        max_cases: Optional maximum number of cases to scrape

    Returns:
        Path to the created index
    """
    from rag.indexer import DOHAIndexer, IndexedCase

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Scrape cases
    scraper = DOHAScraper(output_dir=output_dir / "raw_cases")

    max_per_year = None
    if max_cases:
        years = end_year - start_year + 1
        max_per_year = max_cases // years

    cases = scraper.scrape_years(start_year, end_year, max_per_year)

    # Convert to indexed cases
    indexed_cases = []
    for case in cases:
        # Parse year from case number
        try:
            year = int(case.case_number[:2])
            year = year + 2000 if year < 50 else year + 1900
        except:
            year = 2020

        indexed_cases.append(IndexedCase(
            case_number=case.case_number,
            year=year,
            outcome=case.outcome,
            guidelines=case.guidelines,
            summary=case.summary,
            key_facts=case.sor_allegations,
            judge=case.judge
        ))

    # Create index
    index_path = output_dir / "doha_index"
    indexer = DOHAIndexer(index_path=index_path)
    indexer.add_cases_batch(indexed_cases)
    indexer.save()

    logger.info(f"Created index with {len(indexed_cases)} cases at {index_path}")
    return index_path


if __name__ == "__main__":
    print("DOHA Case Scraper")
    print("=" * 50)

    if not HAS_REQUESTS:
        print("\nError: requests and beautifulsoup4 required")
        print("Install with: pip install requests beautifulsoup4")
    else:
        print("\nTo scrape and build an index, use:")
        print("  python build_index.py --start-year 2020 --end-year 2024")
        print("\nOr from Python:")
        print("  from rag.scraper import scrape_and_index")
        print("  scrape_and_index('./my_index', start_year=2020, end_year=2024)")
