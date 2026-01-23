# SEAD-4 Adjudicative Guidelines Analyzer (LLM-Based)

An LLM-powered system for analyzing security clearance reports against SEAD-4 adjudicative guidelines with explainable reasoning and optional precedent matching.

## Why LLM-Based?

| Benefit | Description |
|---------|-------------|
| **Explainable** | Provides reasoning with specific SEAD-4 citations |
| **Fast deployment** | Hours, not months |
| **Handles nuance** | Edge cases, context, mitigating factors |
| **No training data** | Works out of the box |
| **Easy updates** | Change prompts when guidelines update |

## Features

- **Guideline Classification**: Identifies relevant guidelines A-M with confidence scores
- **Disqualifier Detection**: Cites specific AG paragraphs (e.g., "AG ¶ 19(a)")
- **Mitigator Analysis**: Identifies potential mitigating conditions
- **Severity Assessment**: A-D scale with detailed reasoning
- **Precedent Matching** (Optional): RAG-based retrieval of similar DOHA cases
- **Batch Processing**: Analyze multiple reports efficiently

## Requirements

- Python 3.8+
- Google Gemini API key (default) or Anthropic Claude API key
- PyMuPDF for PDF processing
- Optional: sentence-transformers for RAG precedent matching
- Optional: Playwright + Chromium for DOHA case scraping (browser automation)

## Quick Start

```bash
# Navigate to the project directory
cd sead4_llm

# Install dependencies
pip install -r requirements.txt

# Set your API key (Gemini by default)
export GOOGLE_API_KEY=your_key_here

# Or use Claude
export ANTHROPIC_API_KEY=your_key_here

# Analyze a single report (uses Gemini by default)
python analyze.py --input report.pdf --output result.json

# Analyze using Claude instead
python analyze.py --input report.pdf --output result.json --provider claude

# Analyze with precedent matching (requires DOHA index)
python analyze.py --input report.pdf --use-rag --index ./doha_index

# Batch process (uses Gemini by default)
python analyze.py --input-dir ./reports --output-dir ./results
```

## Project Structure

```
sead4_llm/
├── analyze.py             # Main entry point with PDF/text parsing
├── build_index.py         # DOHA index builder CLI
├── requirements.txt       # Python dependencies
├── analyzers/
│   ├── claude_analyzer.py # Claude API implementation
│   └── gemini_analyzer.py # Google Gemini API implementation (default)
├── config/
│   └── guidelines.py      # Full SEAD-4 guidelines text
├── prompts/
│   └── templates.py       # Structured prompts
├── schemas/
│   └── models.py          # Pydantic output schemas
└── rag/
    ├── indexer.py         # DOHA case indexer
    ├── retriever.py       # Precedent retriever
    ├── scraper.py         # HTTP-based scraper (blocked by bot protection)
    └── browser_scraper.py # Playwright browser scraper (recommended)

# Root-level scraping scripts
├── run_full_scrape.py         # Automated link collection (30K+ cases)
├── download_pdfs_browser.py   # Browser-based PDF downloader (WORKS - use this!)
└── download_pdfs.py           # Parallel downloader (doesn't work - bot protection)
```

## Building the DOHA Precedent Index

### Browser-Based Scraping (Recommended)

✅ **SCRAPING WORKS!** The project includes a **Playwright-based browser scraper** that successfully bypasses bot protection and has scraped **30,850+ DOHA cases**.

See [**DOHA_SCRAPING_GUIDE.md**](DOHA_SCRAPING_GUIDE.md) for complete details on:
- How browser automation bypasses Akamai bot protection
- Complete scraping workflow (link collection → PDF download → index building)
- Website structure for all years (2016-2026)
- Legal/ethical considerations for public records access
- Troubleshooting and best practices

**Quick start for scraping:**

```bash
# 1. Collect all case links using browser automation (~11 minutes)
python run_full_scrape.py

# 2. Download and parse PDFs using browser automation (~8-9 hours)
python download_pdfs_browser.py --max-cases 10  # Test with 10 cases first
python download_pdfs_browser.py                 # Download all 30K+ cases

# 3. Build RAG index from parsed cases
cd sead4_llm
python build_index.py --from-json ../doha_parsed_cases/all_cases.json --output ./doha_index

# Test the index
python build_index.py --test --index ./doha_index
```

**Note**: Use `download_pdfs_browser.py` (not `download_pdfs.py`). Individual PDF URLs are also protected by bot protection and require browser-based downloads.

### Alternative: Build from Local Files

If you prefer manual downloads or have existing PDFs:

```bash
cd sead4_llm

# Build from local PDF files
python build_index.py --local-dir ./downloaded_cases --output ./doha_index

# Or from JSON data
python build_index.py --from-json ./cases.json --output ./doha_index
```

### Using the Index

Once built, enable precedent matching in your analysis:

```bash
# Analyze with precedent matching (uses Gemini by default)
python analyze.py --input report.pdf --use-rag --index ./doha_index

# Use with Claude
python analyze.py --input report.pdf --use-rag --index ./doha_index --provider claude
```

**Note**: The built-in `--scrape` option in `build_index.py` uses HTTP requests which are blocked. Use `run_full_scrape.py` (Playwright) instead for successful scraping.

## Output Format

```json
{
  "case_id": "report_001",
  "overall_assessment": {
    "recommendation": "UNFAVORABLE",
    "confidence": 0.85,
    "summary": "Multiple unresolved financial concerns under Guideline F..."
  },
  "guidelines": [
    {
      "code": "F",
      "name": "Financial Considerations",
      "relevant": true,
      "severity": "C",
      "disqualifiers": [
        {
          "code": "AG ¶ 19(a)",
          "description": "inability to satisfy debts",
          "evidence": "Applicant has $47,000 in delinquent debt..."
        }
      ],
      "mitigators": [
        {
          "code": "AG ¶ 20(b)",
          "description": "conditions beyond control",
          "applicability": "PARTIAL",
          "reasoning": "Job loss in 2022, but no evidence of responsible action since..."
        }
      ],
      "reasoning": "The applicant's financial situation raises significant concerns..."
    }
  ],
  "follow_up_recommendations": [
    "Request current credit report",
    "Verify employment history 2021-2023"
  ],
  "similar_precedents": [
    {
      "case_number": "ISCR 22-01234",
      "outcome": "DENIED",
      "relevance": "Similar debt amount, no mitigation efforts"
    }
  ]
}
```

## Configuration

### Environment Variables

**Required (choose one):**
- `GOOGLE_API_KEY` - Your Google Gemini API key (default provider)
- `ANTHROPIC_API_KEY` - Your Claude API key from Anthropic (alternative provider)

**Optional:**
- `DOHA_INDEX_PATH` - Path to DOHA vector index directory (for RAG precedent matching)

### LLM Provider Selection

The system supports two LLM providers:
- **Google Gemini** (default) - Use `--provider gemini` or omit flag
- **Anthropic Claude** - Use `--provider claude`

### Command Line Options

```bash
# Single document analysis
python analyze.py --input <file> [--output <path>] [--provider <gemini|claude>] [--use-rag] [--index <path>] [--verbose]

# Batch processing
python analyze.py --input-dir <directory> --output-dir <directory> [--provider <gemini|claude>] [--batch]

# Build DOHA index
python build_index.py --scrape --start-year <year> --end-year <year> --output <path>
```

## License

This project is intended for educational use only. It is provided as-is for learning purposes and should not be used for production security clearance adjudication or other official government purposes.
