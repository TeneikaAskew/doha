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
    outcome: str  # GRANTED, DENIED, REVOKED
    guidelines: List[str]
    summary: str
    full_text: str
    sor_allegations: List[str]
    mitigating_factors: List[str]
    judge: str
    source_url: str

    def to_dict(self) -> dict:
        return asdict(self)


class DOHAScraper:
    """
    Scrapes DOHA case decisions from public sources

    Primary sources:
    1. OSD OGC DOHA Industrial Security page
    2. DOHA case archives
    """

    # Base URLs for DOHA cases
    DOHA_BASE_URL = "https://ogc.osd.mil/doha/industrial/"
    DOHA_ARCHIVE_PATTERN = "https://ogc.osd.mil/doha/industrial/{year}/"

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

    # Outcome patterns
    OUTCOME_PATTERNS = {
        'GRANTED': r'clearance\s+is\s+granted|eligibility\s+.*\s+is\s+granted|favorable\s+determination',
        'DENIED': r'clearance\s+is\s+denied|eligibility\s+.*\s+is\s+denied|unfavorable\s+determination',
        'REVOKED': r'clearance\s+is\s+revoked|eligibility\s+.*\s+is\s+revoked',
    }

    def __init__(
        self,
        output_dir: Path = Path("./doha_cases"),
        rate_limit: float = 1.0,  # seconds between requests
        user_agent: str = "SEAD4-Analyzer/1.0 (Research Tool)"
    ):
        if not HAS_REQUESTS:
            raise ImportError("requests and beautifulsoup4 required. Install with: pip install requests beautifulsoup4")

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.rate_limit = rate_limit
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': user_agent
        })
        self._last_request = 0

    def _rate_limited_get(self, url: str, **kwargs) -> requests.Response:
        """Make a rate-limited GET request"""
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)

        logger.debug(f"Fetching: {url}")
        response = self.session.get(url, timeout=30, **kwargs)
        self._last_request = time.time()

        return response

    def get_case_links(self, year: int) -> List[Tuple[str, str]]:
        """
        Get links to case decisions for a given year

        Returns:
            List of (case_number, url) tuples
        """
        url = self.DOHA_ARCHIVE_PATTERN.format(year=year)

        try:
            response = self._rate_limited_get(url)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch case list for {year}: {e}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')

        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            # Look for case links (typically .html or .pdf)
            if re.search(r'\d{2}-\d+', href):
                case_match = re.search(r'(\d{2}-\d+)', href)
                if case_match:
                    case_number = case_match.group(1)
                    # Make absolute URL
                    if not href.startswith('http'):
                        href = url + href
                    links.append((case_number, href))

        # Remove duplicates
        seen = set()
        unique_links = []
        for case_num, url in links:
            if case_num not in seen:
                seen.add(case_num)
                unique_links.append((case_num, url))

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
        # Extract date
        date = self._extract_date(text)

        # Extract outcome
        outcome = self._extract_outcome(text)

        # Extract guidelines
        guidelines = self._extract_guidelines(text)

        # Extract SOR allegations
        sor_allegations = self._extract_sor_allegations(text)

        # Extract mitigating factors
        mitigating_factors = self._extract_mitigating_factors(text)

        # Extract judge name
        judge = self._extract_judge(text)

        # Create summary (first 1000 chars of findings section or beginning)
        summary = self._create_summary(text)

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
            source_url=source_url
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
        """Extract case outcome from text"""
        text_lower = text.lower()

        # Check conclusion section first
        conclusion_match = re.search(
            r'(?:conclusion|decision|order)[:\s]*(.*?)(?:\n\n|\Z)',
            text_lower[-3000:],
            re.DOTALL
        )
        conclusion_text = conclusion_match.group(1) if conclusion_match else text_lower[-3000:]

        for outcome, pattern in self.OUTCOME_PATTERNS.items():
            if re.search(pattern, conclusion_text, re.IGNORECASE):
                return outcome

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

    def _extract_judge(self, text: str) -> str:
        """Extract administrative judge name"""
        patterns = [
            r'(?:Administrative\s+Judge|AJ)[:\s]+([A-Z][a-z]+\s+[A-Z]\.?\s*[A-Z][a-z]+)',
            r'([A-Z][a-z]+\s+[A-Z]\.?\s*[A-Z][a-z]+)[\s,]+Administrative\s+Judge',
        ]

        for pattern in patterns:
            match = re.search(pattern, text[:3000])
            if match:
                return match.group(1)

        return "Unknown"

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

    def scrape_years(
        self,
        start_year: int,
        end_year: int,
        max_cases_per_year: Optional[int] = None
    ) -> List[ScrapedCase]:
        """
        Scrape cases for a range of years

        Args:
            start_year: Starting year (2-digit or 4-digit)
            end_year: Ending year
            max_cases_per_year: Optional limit per year

        Returns:
            List of scraped cases
        """
        all_cases = []

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

            # Save intermediate results
            self._save_cases(all_cases, f"cases_{start_year}_{year}.json")

        return all_cases

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
