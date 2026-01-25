# Comprehensive Course Plan: Building a Legal Case Analysis System
## From Web Scraping to AI-Powered Analysis with Streamlit UI

---

# Course Overview

This course teaches students to build an end-to-end legal document analysis system that:
- Scrapes **~36,700 DOHA security clearance cases** from government websites
- Bypasses bot protection using browser automation
- Extracts structured data from PDF documents
- Applies progressively sophisticated NLP techniques
- Integrates LLMs for intelligent analysis
- Presents results through an interactive Streamlit dashboard

**Target Audience:** Developers with Python experience seeking to build production-grade data pipelines and ML applications.

**Prerequisites:** Python fundamentals, basic understanding of HTTP/web concepts, familiarity with command line.

**Total Duration:** ~15 weeks (adjustable based on pace)

---

# Phase 1: Understanding the Domain & Data Discovery (1 Week)

## 1.1 Domain Knowledge: DOHA Security Clearance Cases

**Learning Objectives:**
- Understand what DOHA (Defense Office of Hearings and Appeals) does
- Learn the SEAD-4 (Security Executive Agent Directive 4) guidelines
- Understand case types: Hearing vs Appeal decisions

**Key Concepts - SEAD-4 Guidelines (13 total, A-M):**

| Letter | Guideline |
|--------|-----------|
| A | Allegiance to the United States |
| B | Foreign Influence |
| C | Foreign Preference |
| D | Sexual Behavior |
| E | Personal Conduct |
| F | Financial Considerations |
| G | Alcohol Consumption |
| H | Drug Involvement |
| I | Psychological Conditions |
| J | Criminal Conduct |
| K | Handling Protected Information |
| L | Outside Activities |
| M | Use of IT Systems |

**Key File:** [guidelines.py](sead4_llm/config/guidelines.py) - Complete guideline definitions with disqualifiers and mitigators

**Developer Considerations:**
- Domain expertise is critical - spend time reading actual DOHA decisions
- Each guideline has specific "disqualifying conditions" and "mitigating conditions"
- Outcomes are: GRANTED, DENIED, REVOKED, REMANDED
- Cases follow predictable structure: Findings of Fact → Analysis → Conclusion

## 1.2 Source Identification & URL Pattern Analysis

**Target Sources:**
```
Base URL: https://doha.ogc.osd.mil/
├── Industrial Security Program (ISP)
│   ├── Hearing Decisions: /ISCR/Hearing-Decisions/
│   └── Appeal Decisions: /ISCR/Appeal-Decisions/
└── ADP/CAC Program
    └── ADP Decisions: /ADP-CAC/ADP-Decisions/
```

**URL Pattern Discovery:**
```python
# Hearing decisions URL pattern (from scraper.py)
DOHA_YEAR_PATTERN = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/ISCR-Hearing-Decisions/{year}-ISCR-Hearing-Decisions/"

# Appeal decisions URL pattern
DOHA_APPEAL_YEAR_PATTERN = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/DOHA-Appeal-Board/{year}-DOHA-Appeal-Board-Decisions/"
```

**Key File:** [scraper.py:83-120](sead4_llm/rag/scraper.py#L83-L120) - URL configuration

---

# Phase 2: Web Scraping & Browser Automation (2 Weeks)

## 2.1 Why Browser Automation is Required

**The Problem - Bot Protection:**
- DOHA website uses Akamai Bot Manager
- Simple HTTP requests get blocked (403 Forbidden)
- JavaScript challenges require execution
- Cookie-based session validation

## 2.2 Playwright Browser Automation

**Installation:**
```bash
pip install playwright
playwright install chromium
```

**Core Pattern - BrowserSession Class:**
```python
from playwright.sync_api import sync_playwright

class BrowserSession:
    def __init__(self, headless: bool = True):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)..."
        )
        self.page = self.context.new_page()

    def fetch(self, url: str) -> str:
        self.page.goto(url)
        self.page.wait_for_load_state("networkidle")
        return self.page.content()
```

**Key File:** [browser_scraper.py:26-129](sead4_llm/rag/browser_scraper.py#L26-L129) - DOHABrowserScraper class (~940 lines total)

## 2.3 Parallel Browser Downloads

**Thread-Local Browser Pattern:**
```python
import threading
from concurrent.futures import ThreadPoolExecutor

class ParallelBrowserDownloader:
    def __init__(self, max_workers: int = 3):
        self._thread_local = threading.local()

    def _get_browser(self):
        """Thread-local browser instance"""
        if not hasattr(self._thread_local, 'browser'):
            self._thread_local.playwright = sync_playwright().start()
            self._thread_local.browser = self._thread_local.playwright.chromium.launch()
        return self._thread_local.browser
```

**Key File:** [browser_scraper.py:644-938](sead4_llm/rag/browser_scraper.py#L644-L938) - ParallelBrowserDownloader

**Developer Considerations:**
- Browser instances are heavy - reuse them across downloads
- Limit concurrency (3-5 workers) to avoid overwhelming the server
- Add delays between requests for respectful scraping
- Restart browsers periodically (every ~100 cases) to prevent memory buildup

## 2.4 Link Discovery Pipeline

**Key File:** [run_full_scrape.py:17-339](run_full_scrape.py#L17-L339) - Full scrape orchestration (run_full_scrape function)

---

# Phase 3: PDF Processing & Text Extraction (1.5 Weeks)

## 3.1 Download Pipeline with Checkpointing

**Checkpoint System Design:**
```python
import json
from pathlib import Path

class PDFDownloader:
    def __init__(self, output_dir: str, checkpoint_file: str):
        self.output_dir = Path(output_dir)
        self.checkpoint_file = Path(checkpoint_file)
        self.downloaded = self._load_checkpoint()

    def _load_checkpoint(self) -> set:
        if self.checkpoint_file.exists():
            with open(self.checkpoint_file) as f:
                return set(json.load(f))
        return set()

    def _save_checkpoint(self):
        """Save progress every batch"""
        with open(self.checkpoint_file, 'w') as f:
            json.dump(list(self.downloaded), f)
```

**Key File:** [download_pdfs.py](download_pdfs.py) - Complete download pipeline (~950 lines)

## 3.2 Text Extraction with PyMuPDF

```python
import fitz  # PyMuPDF

def extract_from_bytes(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes (no file on disk)"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text_parts = [page.get_text("text") for page in doc]
    doc.close()
    return "\n\n".join(text_parts)
```

**Key File:** [scraper.py:482-500](sead4_llm/rag/scraper.py#L482-L500) - PDF text extraction (scrape_case_pdf method)

## 3.3 Checkpoint Recovery & Merging

**Key File:** [merge_checkpoints.py](merge_checkpoints.py) - Checkpoint merging, deduplication, parquet validation (~260 lines)

**Features:**
- Merges multiple checkpoint files into single dataset
- Deduplicates by case number
- Validates parquet files with PAR1 magic bytes
- Auto-splits files to stay under GitHub's 100MB limit

---

# Phase 4: Data Structuring & Pattern Extraction (2 Weeks)

## 4.1 Data Model Design

**ScrapedCase Dataclass:**
```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ScrapedCase:
    case_number: str
    case_type: str  # "hearing" or "appeal"
    outcome: Optional[str] = None  # GRANTED, DENIED, REVOKED, REMANDED
    guidelines: list[str] = field(default_factory=list)  # Letters A-M
    formal_findings: list[dict] = field(default_factory=list)
    full_text: str = ""
    source_url: str = ""
    date: Optional[str] = None
```

**Key File:** [scraper.py:43-72](sead4_llm/rag/scraper.py#L43-L72) - ScrapedCase dataclass

## 4.2 Outcome Extraction with 100+ Regex Patterns

**Pattern Hierarchy Strategy:**
```python
import re
from typing import Optional

# Ordered by specificity - more specific patterns first
OUTCOME_PATTERNS = [
    # Explicit conclusions
    (r"Applicant's eligibility.*?is\s+(GRANTED|DENIED)", "conclusion"),
    (r"clearance\s+is\s+(GRANTED|DENIED)", "conclusion"),
    (r"DECISION[:\s]+(?:Eligibility\s+is\s+)?(GRANTED|DENIED)", "decision"),

    # Remand/Revocation patterns
    (r"case\s+is\s+REMANDED", "remand"),
    (r"clearance\s+is\s+(REVOKED)", "revocation"),

    # Appeal-specific patterns
    (r"affirmed|reversed|sustained", "appeal_outcome"),
    # ... 100+ more patterns
]

def extract_outcome(text: str) -> Optional[str]:
    """Extract case outcome using pattern hierarchy"""
    for pattern, pattern_type in OUTCOME_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            outcome = match.group(1) if match.lastindex else match.group()
            return normalize_outcome(outcome.upper())
    return None
```

**Key File:** [scraper.py:139-255](sead4_llm/rag/scraper.py#L139-L255) - OUTCOME_PATTERNS dictionary

**Developer Considerations:**
- Order patterns from most specific to least specific
- Test patterns against real documents constantly
- Handle case insensitivity properly
- Log which pattern matched for debugging
- Build a pattern test suite with edge cases

## 4.3 Guideline & Formal Findings Extraction

**Key File:** [scraper.py:122-137](sead4_llm/rag/scraper.py#L122-L137) - GUIDELINE_PATTERNS dictionary

---

# Phase 5: Basic NLP - Keyword Analysis (1.5 Weeks)

## 5.1 Keyword-Based Analysis

**NativeSEAD4Analyzer Architecture:**
```python
from dataclasses import dataclass

@dataclass
class KeywordMatch:
    keyword: str
    category: str  # "disqualifying" or "mitigating"
    context: str   # Surrounding text
    position: int

class NativeSEAD4Analyzer:
    def __init__(self):
        self.disqualifying_keywords = self._load_keywords()
        self.mitigating_keywords = self._load_mitigating_keywords()

    def assess_guideline(self, text: str, guideline: str) -> GuidelineAssessment:
        # Find disqualifying matches with context
        # Find mitigating matches with context
        # Calculate severity score
        return assessment
```

**Key File:** [native_analyzer.py](sead4_llm/analyzers/native_analyzer.py) - Complete keyword analyzer (~400 lines)

## 5.2 Severity Assessment

**Weighted Scoring:**
```python
SEVERITY_WEIGHTS = {"high": 3.0, "medium": 2.0, "low": 1.0}

def calculate_severity(disq_matches, mit_matches):
    disq_score = sum(SEVERITY_WEIGHTS[m.severity] for m in disq_matches)
    mit_score = sum(SEVERITY_WEIGHTS[m.severity] for m in mit_matches)

    # Net score = disqualifying - (mitigating * 0.5)
    net_score = disq_score - (mit_score * 0.5)

    if net_score <= 0: return "none"
    elif net_score < 3: return "low"
    elif net_score < 7: return "medium"
    else: return "high"
```

**Key File:** [native_analyzer.py:150-280](sead4_llm/analyzers/native_analyzer.py#L150-L280) - Severity assessment

---

# Phase 6: Enhanced NLP - Statistical & Embedding Methods (2 Weeks)

## 6.1 N-gram Phrase Matching

```python
def tokenize(text: str) -> list[str]:
    import re
    return re.findall(r'\b\w+\b', text.lower())

def generate_ngrams(tokens: list[str], n: int) -> list[tuple]:
    return [tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]

class NgramMatcher:
    def __init__(self, phrases: list[str]):
        self.phrase_ngrams = {}
        for phrase in phrases:
            tokens = tokenize(phrase)
            self.phrase_ngrams[tuple(tokens)] = phrase

    def find_phrases(self, text: str) -> list[dict]:
        tokens = tokenize(text)
        matches = []
        for n in range(1, 5):  # Up to 4-grams
            for i, ngram in enumerate(generate_ngrams(tokens, n)):
                if ngram in self.phrase_ngrams:
                    matches.append({"phrase": self.phrase_ngrams[ngram], "position": i})
        return matches
```

**Key File:** [enhanced_native_analyzer.py:80-150](sead4_llm/analyzers/enhanced_native_analyzer.py#L80-L150) - N-gram matching

## 6.2 TF-IDF Weighting

```python
from sklearn.feature_extraction.text import TfidfVectorizer

class TfidfAnalyzer:
    def __init__(self, corpus: list[str]):
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 3),
            stop_words='english'
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)
        self.feature_names = self.vectorizer.get_feature_names_out()

    def get_important_terms(self, text: str, top_n: int = 20) -> list[tuple]:
        vec = self.vectorizer.transform([text])
        scores = vec.toarray()[0]
        top_indices = scores.argsort()[-top_n:][::-1]
        return [(self.feature_names[i], scores[i]) for i in top_indices if scores[i] > 0]
```

## 6.3 Semantic Embeddings

```python
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class SemanticMatcher:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.concept_embeddings = {}
        self._build_concept_index()

    def _build_concept_index(self):
        concepts = {
            "financial_irresponsibility": ["failed to pay debts", "delinquent on taxes"],
            "drug_use": ["used marijuana", "illegal drug use"],
            # ... more concepts
        }
        for concept, phrases in concepts.items():
            embeddings = self.model.encode(phrases)
            self.concept_embeddings[concept] = np.mean(embeddings, axis=0)

    def find_concept_matches(self, text: str, threshold: float = 0.5) -> dict:
        sentences = text.split('.')
        sentence_embeddings = self.model.encode(sentences)

        matches = {}
        for concept, concept_emb in self.concept_embeddings.items():
            similarities = cosine_similarity([concept_emb], sentence_embeddings)[0]
            max_sim = float(np.max(similarities))
            if max_sim >= threshold:
                matches[concept] = max_sim
        return matches
```

**Key File:** [enhanced_native_analyzer.py:200-350](sead4_llm/analyzers/enhanced_native_analyzer.py#L200-L350) - Embedding analysis

## 6.4 Ensemble Scoring

**Combined Analysis:**
```python
WEIGHTS = {"keyword": 0.25, "ngram": 0.20, "tfidf": 0.25, "embedding": 0.30}

def ensemble_score(keyword_score, ngram_score, tfidf_score, embedding_score):
    combined = (
        WEIGHTS["keyword"] * keyword_score +
        WEIGHTS["ngram"] * ngram_score +
        WEIGHTS["tfidf"] * tfidf_score +
        WEIGHTS["embedding"] * embedding_score
    )

    # Confidence based on agreement between methods
    scores = [keyword_score, ngram_score, tfidf_score, embedding_score]
    agreement = 1.0 - np.std(scores)  # High std = low agreement

    return combined, agreement
```

**Key File:** [enhanced_native_analyzer.py:400-550](sead4_llm/analyzers/enhanced_native_analyzer.py#L400-L550) - Ensemble scoring (~600 lines total)

---

# Phase 7: LLM Integration (2 Weeks)

## 7.1 Gemini 2.0 Flash Setup

```python
import google.generativeai as genai
import os

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash-exp",
    generation_config={"temperature": 0.1, "max_output_tokens": 4096}
)
```

**Key File:** [gemini_analyzer.py:38-67](sead4_llm/analyzers/gemini_analyzer.py#L38-L67) - Gemini setup (pricing + GeminiSEAD4Analyzer class)

## 7.2 Prompt Engineering

**Structured JSON Output:**
```python
SYSTEM_PROMPT = """You are a legal analyst specializing in DOHA decisions.
Analyze this security clearance case and respond ONLY with valid JSON:
{
  "predicted_outcome": "GRANTED|DENIED|REVOKED|REMANDED",
  "confidence": 0.0-1.0,
  "guidelines_triggered": ["F", "H"],
  "assessments": {
    "F": {
      "severity": "high|medium|low|none",
      "disqualifying_conditions": ["DC 19(a): inability to satisfy debts"],
      "mitigating_conditions": ["MC 20(b): conditions beyond control"],
      "reasoning": "Explanation..."
    }
  }
}
"""
```

**Key File:** [templates.py:15-150](sead4_llm/config/templates.py#L15-L150) - Prompt templates

## 7.3 Response Parsing with Pydantic

```python
from pydantic import BaseModel
from typing import Optional
import json
import re

class GuidelineAssessmentLLM(BaseModel):
    severity: str
    disqualifying_conditions: list[str]
    mitigating_conditions: list[str]
    reasoning: str

class AnalysisResultLLM(BaseModel):
    predicted_outcome: str
    confidence: float
    guidelines_triggered: list[str]
    assessments: dict[str, GuidelineAssessmentLLM]

def parse_llm_response(response_text: str) -> Optional[AnalysisResultLLM]:
    # Extract JSON from response
    json_match = re.search(r'\{[\s\S]*\}', response_text)
    if not json_match:
        return None

    try:
        data = json.loads(json_match.group())
        return AnalysisResultLLM(**data)
    except (json.JSONDecodeError, ValidationError):
        return None
```

**Key File:** [gemini_analyzer.py:150-250](sead4_llm/analyzers/gemini_analyzer.py#L150-L250) - Response parsing

## 7.4 Token Usage Tracking

```python
from dataclasses import dataclass

# Gemini 2.0 Flash pricing (per 1M tokens)
GEMINI_FLASH_INPUT_PRICE = 0.10
GEMINI_FLASH_OUTPUT_PRICE = 0.40

@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        input_cost = (self.input_tokens / 1_000_000) * GEMINI_FLASH_INPUT_PRICE
        output_cost = (self.output_tokens / 1_000_000) * GEMINI_FLASH_OUTPUT_PRICE
        return input_cost + output_cost
```

**Key File:** [gemini_analyzer.py:280-350](sead4_llm/analyzers/gemini_analyzer.py#L280-L350) - Token tracking

---

# Phase 8: RAG (Retrieval Augmented Generation) (2 Weeks)

## 8.1 RAG Architecture

```
Input Document → Native Analysis → Build Query → Retrieve Similar Cases → LLM with Context
       ↓                ↓                 ↓                ↓                    ↓
   Full Text    Guidelines Found    Semantic Search   Top-K Cases        Final Analysis
```

## 8.2 Vector Index with FAISS

```python
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

class CaseIndex:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.index = None
        self.case_ids = []
        self.case_metadata = {}

    def build_index(self, cases: list[dict]):
        texts = [self._create_summary(case) for case in cases]
        embeddings = self.model.encode(texts).astype('float32')
        faiss.normalize_L2(embeddings)

        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dimension)
        self.index.add(embeddings)

        for case in cases:
            self.case_ids.append(case['case_number'])
            self.case_metadata[case['case_number']] = case

    def search(self, query: str, k: int = 5) -> list[dict]:
        query_embedding = self.model.encode([query]).astype('float32')
        faiss.normalize_L2(query_embedding)
        scores, indices = self.index.search(query_embedding, k)

        return [
            {'case_number': self.case_ids[i], 'score': float(s),
             'metadata': self.case_metadata[self.case_ids[i]]}
            for s, i in zip(scores[0], indices[0]) if i >= 0
        ]
```

**Key File:** [build_index.py:150-280](sead4_llm/build_index.py#L150-L280) - FAISS index building

## 8.3 Native Analysis Guides Retrieval

```python
def build_rag_query(native_result):
    """Build retrieval query from native analysis results"""
    parts = [f"Guideline {g}" for g in native_result.guidelines_triggered]

    # Add top evidence from native analysis
    for evidence in native_result.evidence[:5]:
        parts.append(evidence['context'])

    return " ".join(parts)
```

**Key File:** [build_index.py](sead4_llm/build_index.py) - Index building (631 lines, 4 modes: scrape, local, parquet, test)

---

# Phase 9: Frontend Development with Streamlit (2 Weeks)

## 9.1 Streamlit Fundamentals

**Key Patterns:**
- `st.set_page_config()` must be first Streamlit call
- Use `st.tabs()` for organization
- `st.columns()` for horizontal layout
- `st.sidebar` for filters and navigation

## 9.2 Session State Management

```python
import streamlit as st

def init_session_state():
    defaults = {
        'current_document': None,
        'analysis_results': {},
        'selected_case': None,
        'analyzer': None,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

# Call at start of app
init_session_state()
```

**Key File:** [demo_ui.py:95-180](sead4_llm/demo_ui.py#L95-L180) - Session state initialization

## 9.3 Caching Strategies

```python
@st.cache_resource  # For ML models, heavy objects - persists across sessions
def load_analyzer():
    return EnhancedNativeSEAD4Analyzer()

@st.cache_data  # For DataFrames, computation results - cached by input
def load_case_data():
    parquet_path = Path("doha_parsed_cases")
    split_files = list(parquet_path.glob("all_cases_*.parquet"))
    if split_files:
        dfs = [pd.read_parquet(f) for f in sorted(split_files)]
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame()
```

**Key File:** [demo_ui.py:45-95](sead4_llm/demo_ui.py#L45-L95) - Caching functions

## 9.4 UI Components

**Tab Structure:**
1. **Document View** - PDF display with PDF.js
2. **Basic Native** - Keyword analysis results
3. **Enhanced Native** - ML-enhanced analysis
4. **Comparison** - Side-by-side comparison
5. **Dashboard** - Case statistics and charts

**Key File:** [demo_ui.py:400-450](sead4_llm/demo_ui.py#L400-L450) - Tab layout

## 9.5 Precision Calculation & Validation

```python
def calculate_precision(predictions: list[dict], ground_truth: pd.DataFrame) -> dict:
    results = {'total': 0, 'correct_outcome': 0, 'cases': []}

    for pred in predictions:
        case_num = pred['case_number']
        gt_row = ground_truth[ground_truth['case_number'] == case_num]
        if gt_row.empty:
            continue

        results['total'] += 1
        actual = gt_row.iloc[0]['outcome']
        predicted = pred['predicted_outcome']

        if predicted == actual:
            results['correct_outcome'] += 1

        results['cases'].append({
            'case_number': case_num,
            'predicted': predicted,
            'actual': actual,
            'correct': predicted == actual
        })

    if results['total'] > 0:
        results['precision'] = results['correct_outcome'] / results['total']

    return results
```

**Key File:** [demo_ui.py:700-800](sead4_llm/demo_ui.py#L700-L800) - Precision calculation

---

# Key Files Reference Table

| File | Purpose | Lines |
|------|---------|-------|
| [run_full_scrape.py](run_full_scrape.py) | Link discovery orchestration | ~375 |
| [download_pdfs.py](download_pdfs.py) | PDF download with checkpoints | ~950 |
| [browser_scraper.py](sead4_llm/rag/browser_scraper.py) | Playwright browser automation | ~940 |
| [scraper.py](sead4_llm/rag/scraper.py) | ScrapedCase, URL patterns, outcome extraction | ~1,970 |
| [merge_checkpoints.py](merge_checkpoints.py) | Checkpoint merging & parquet | ~260 |
| [native_analyzer.py](sead4_llm/analyzers/native_analyzer.py) | Keyword-based analysis | ~400 |
| [enhanced_native_analyzer.py](sead4_llm/analyzers/enhanced_native_analyzer.py) | N-gram + TF-IDF + embeddings | ~600 |
| [gemini_analyzer.py](sead4_llm/analyzers/gemini_analyzer.py) | LLM integration & token tracking | ~485 |
| [build_index.py](sead4_llm/build_index.py) | Vector index building | ~630 |
| [demo_ui.py](sead4_llm/demo_ui.py) | Streamlit frontend | ~1,385 |
| [guidelines.py](sead4_llm/config/guidelines.py) | SEAD-4 definitions | ~500 |
| [templates.py](sead4_llm/config/templates.py) | Prompt templates | ~200 |
| [models.py](sead4_llm/config/models.py) | Pydantic schemas | ~150 |

---

# Developer Considerations by Phase

| Phase | Key Considerations |
|-------|-------------------|
| 1. Domain | Read real DOHA decisions; understand guideline structure |
| 2. Scraping | Use browser automation for bot protection; implement rate limiting; restart browsers periodically |
| 3. PDFs | Always checkpoint; handle corrupted/scanned PDFs; validate parquet files |
| 4. Extraction | Build 100+ regex patterns; validate against ground truth; handle edge cases |
| 5. Keywords | Fast baseline; easy to debug and improve; domain-specific dictionaries |
| 6. Enhanced NLP | Train TF-IDF on full corpus; tune embedding thresholds; ensemble weighting |
| 7. LLM | Low temperature for consistency; track token costs; cache responses |
| 8. RAG | Native analysis guides retrieval; balance context window size |
| 9. Streamlit | Use caching; manage session state properly; responsive design |

---

# Assessment & Projects

**Mini-Projects (Per Phase):**
1. Build scraper for different legal document source
2. Extract data from 100 sample documents with validation
3. Implement keyword analyzer for new domain
4. Compare ensemble method accuracy with different weights
5. Build LLM analyzer with different model (Claude, GPT-4)
6. Implement RAG for document Q&A
7. Build custom Streamlit dashboard with charts

**Final Capstone:**
Build a complete document analysis system for a new legal/regulatory domain:
- Identify and scrape data source
- Extract structured data with validation
- Build NLP analysis pipeline (keyword → ML → LLM)
- Create interactive Streamlit interface
- Validate accuracy against ground truth
- Document with precision/recall metrics

---

# Verification

To run the complete system:
```bash
# 1. Collect case links (~11 minutes for ~36,700 cases)
python run_full_scrape.py

# 2. Download and parse PDFs (~3 hours with 4 workers)
python download_pdfs.py --workers 4

# 3. Merge checkpoints into parquet files
python merge_checkpoints.py

# 4. Build vector index (from sead4_llm/ directory)
cd sead4_llm
python build_index.py --from-cases ../doha_parsed_cases/all_cases.parquet --output ../doha_index

# 5. Launch Streamlit UI
streamlit run demo_ui.py
```

---

# Live Demo

Explore the scraped data: **https://doha-analysis.streamlit.app/**

Browse and search ~36,700 DOHA cases with filtering by outcome, guidelines, year, and case type.

---

# Related Documentation

- [README.md](README.md) - Main project documentation
- [DOHA_SCRAPING_GUIDE.md](DOHA_SCRAPING_GUIDE.md) - Detailed scraping guide
- [INVESTIGATION_SUMMARY.md](INVESTIGATION_SUMMARY.md) - How the project was developed
