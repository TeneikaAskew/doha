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

## Quick Start

```bash
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
├── config/
│   └── guidelines.py      # Full SEAD-4 guidelines text
├── schemas/
│   └── models.py          # Pydantic output schemas
├── prompts/
│   └── templates.py       # Structured prompts
├── analyzers/
│   ├── claude_analyzer.py # Claude API implementation
│   └── gemini_analyzer.py # Google Gemini API implementation (default)
├── rag/
│   ├── indexer.py         # DOHA case indexer
│   ├── retriever.py       # Precedent retriever
│   ├── scraper.py         # HTTP-based scraper (blocked)
│   └── browser_scraper.py # Playwright browser scraper (works)
├── analyze.py             # Main entry point with PDF parsing
├── build_index.py         # DOHA index builder CLI
└── requirements.txt
```

## Building the DOHA Precedent Index

For improved analysis with precedent matching (RAG), you can build an index of DOHA case decisions. This helps the model make better-informed decisions by referencing similar historical cases.

### Option 1: Browser-Based Scraping (Recommended)

⚠️ **Note**: The `--scrape` option below uses HTTP requests which are blocked by bot protection. For successful scraping, use the **Playwright-based browser scraper** in the root directory:

```bash
# Return to root directory
cd ..

# Collect all case links with browser automation (recommended)
python run_full_scrape.py

# Download and parse PDFs
python download_pdfs.py --max-cases 100  # Test with 100 cases
python download_pdfs.py                   # Download all 30K+ cases

# Build index from parsed cases
cd sead4_llm
python build_index.py --from-json ../doha_parsed_cases/all_cases.json --output ./doha_index
```

See [DOHA_SCRAPING_GUIDE.md](../DOHA_SCRAPING_GUIDE.md) for complete details on browser-based scraping.

### Option 1b: HTTP Scraping (Currently Blocked)

The built-in HTTP scraper is blocked by Akamai bot protection but included for reference:

```bash
# ⚠️ This will likely fail with 403 errors
python build_index.py --scrape --start-year 2020 --end-year 2024 --output ./doha_index
```

### Option 2: Build from Local Files

If you've already downloaded DOHA case PDFs or HTML files:

```bash
# Build from a directory of case files
python build_index.py --local-dir ./downloaded_cases --output ./doha_index
```

Supported file formats: `.pdf`, `.html`, `.txt`

### Option 3: Build from Pre-extracted JSON

If you have case data in JSON format:

```bash
python build_index.py --from-json ./cases.json --output ./doha_index
```

Expected JSON format:
```json
[
  {
    "case_number": "22-01234",
    "overall_decision": "DENIED",
    "guidelines": {"F": {"relevant": true}, "E": {"relevant": true}},
    "text": "Full case text...",
    "sor_allegations": ["Allegation 1", "Allegation 2"]
  }
]
```

### Testing the Index

```bash
# Test with a sample financial query
python build_index.py --test --index ./doha_index
```

### Using the Index for Analysis

Once built, use the index with the analyzer:

```bash
# Analyze with precedent matching (uses Gemini by default)
python analyze.py --input report.pdf --use-rag --index ./doha_index

# Use with Claude
python analyze.py --input report.pdf --use-rag --index ./doha_index --provider claude
```

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

## Supported LLM Providers

| Provider | Model | Environment Variable | Default |
|----------|-------|---------------------|---------|
| Google Gemini | gemini-2.0-flash | `GOOGLE_API_KEY` | ✓ |
| Anthropic Claude | claude-sonnet-4 | `ANTHROPIC_API_KEY` | |

Use the `--provider` flag to select your LLM:
- `--provider gemini` (default)
- `--provider claude`

## Configuration

Environment variables:
- `GOOGLE_API_KEY` - Google Gemini API key (required for default provider)
- `ANTHROPIC_API_KEY` - Claude API key (required for Claude provider)
- `DOHA_INDEX_PATH` - Path to DOHA vector index (for RAG)

## License

This project is intended for educational use only. It is provided as-is for learning purposes and should not be used for production security clearance adjudication or other official government purposes.
