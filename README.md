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

## Complete Workflow

The typical workflow consists of three main phases:

### Phase 1: Data Collection (Optional - for precedent matching)
Run from **project root** directory:
1. Scrape case links: `python run_full_scrape.py`
2. Download PDFs: `python download_pdfs.py`

### Phase 2: Index Building (Optional - for precedent matching)
Run from **sead4_llm/** directory:
3. Build RAG index: `python build_index.py --from-cases ../doha_parsed_cases/all_cases.parquet --output ../doha_index`

### Phase 3: Analysis
Run from **sead4_llm/** directory:
4. Analyze reports: `python analyze.py --input report.pdf [--use-rag --index ../doha_index]`

**Note**: Phases 1-2 are only needed if you want precedent matching. You can perform basic SEAD-4 analysis without them.

## Requirements

- Python 3.8+
- Google Gemini API key (default) or Anthropic Claude API key
- PyMuPDF for PDF processing
- Optional: sentence-transformers for RAG precedent matching
- Optional: Playwright + Chromium for DOHA case scraping (browser automation)

## Quick Start

```bash
# Install dependencies (from project root)
pip install -r requirements.txt

# Set your API key (Gemini by default)
export GOOGLE_API_KEY=your_key_here

# Or use Claude
export ANTHROPIC_API_KEY=your_key_here

# Navigate to the analysis directory
cd sead4_llm

# Analyze a single report (uses Gemini by default)
python analyze.py --input report.pdf --output result.json

# Analyze using Claude instead
python analyze.py --input report.pdf --output result.json --provider claude

# Analyze with precedent matching (requires DOHA index built first)
python analyze.py --input report.pdf --use-rag --index ../doha_index

# Batch process multiple reports
python analyze.py --input-dir ./reports --output-dir ./results
```

## Project Structure

```
doha/                       # Project root
├── run_full_scrape.py     # Step 1: Collect case links (hearings + appeals)
├── download_pdfs.py       # Step 2: Download and parse PDFs
├── requirements.txt       # Python dependencies
├── sead4_llm/            # Analysis package
│   ├── analyze.py             # Main entry point for SEAD-4 analysis
│   ├── build_index.py         # Step 3: Build RAG index from parsed cases
│   ├── analyzers/
│   │   ├── claude_analyzer.py # Claude API implementation
│   │   └── gemini_analyzer.py # Google Gemini API implementation (default)
│   ├── config/
│   │   └── guidelines.py      # Full SEAD-4 guidelines text
│   ├── prompts/
│   │   └── templates.py       # Structured prompts
│   ├── schemas/
│   │   └── models.py          # Pydantic output schemas
│   └── rag/
│       ├── indexer.py         # DOHA case indexer
│       ├── retriever.py       # Precedent retriever
│       ├── scraper.py         # Case text parser
│       └── browser_scraper.py # Playwright browser automation
├── doha_full_scrape/      # Created by run_full_scrape.py
│   └── all_case_links.json    # All collected case links
└── doha_parsed_cases/     # Created by download_pdfs.py
    ├── all_cases.json         # Parsed case data (local use, gitignored if >100MB)
    ├── all_cases.parquet      # Compressed format for Git (<90MB, auto-created)
    ├── hearing_pdfs/          # Downloaded hearing PDFs
    └── appeal_pdfs/           # Downloaded appeal PDFs
```

## Building the DOHA Precedent Index

### Browser-Based Scraping (Recommended)

✅ **SCRAPING WORKS!** The project includes a **Playwright-based browser scraper** that successfully bypasses bot protection:
- **30,850+ Hearing decisions** (2016-2026) - Initial adjudications by DOHA administrative judges (GRANTED/DENIED)
- **1,010+ Appeal decisions** (2017-2026) - DOHA Appeal Board reviews of hearing decisions (AFFIRM/REVERSE/REMAND)
- **2016 and Prior Appeals** - Additional appeal cases in archived pages (exact count TBD after scraping)

See [**DOHA_SCRAPING_GUIDE.md**](DOHA_SCRAPING_GUIDE.md) for complete details on:
- How browser automation bypasses Akamai bot protection
- Complete scraping workflow (link collection → PDF download → index building)
- Website structure for all years (2016-2026)
- Legal/ethical considerations for public records access
- Troubleshooting and best practices

**Quick start for scraping (run from project root):**

```bash
# Step 1: Collect all case links using browser automation
# Hearings: Initial adjudication decisions (2016-2026, ~30,850 cases)
# Appeals: Appeal Board reviews (2016-2026, ~1,010+ cases)
# Both hearings and appeals include "2016 and Prior" archived pages
python run_full_scrape.py                         # Both hearings and appeals (default)
python run_full_scrape.py --case-type hearings   # Only hearings
python run_full_scrape.py --case-type appeals    # Only appeals

# Output: ./doha_full_scrape/all_case_links.json

# Step 2: Download and parse PDFs using browser automation
# Note: Use --max-cases for testing to avoid long download times
python download_pdfs.py --max-cases 10           # Test with 10 cases first
python download_pdfs.py                           # Download all cases (both types)
python download_pdfs.py --case-type hearings     # Download only hearings
python download_pdfs.py --case-type appeals      # Download only appeals

# Output: ./doha_parsed_cases/all_cases.json (for local use)
#         ./doha_parsed_cases/all_cases.parquet (for Git - stays under 100MB limit)
# PDFs organized in: ./doha_parsed_cases/hearing_pdfs/ and ./doha_parsed_cases/appeal_pdfs/

# Step 3: Build RAG index from parsed cases
cd sead4_llm
# Automatically detects and prefers parquet format (most consistent)
python build_index.py --from-cases ../doha_parsed_cases/all_cases.parquet --output ../doha_index

# Step 4: Test the index
python build_index.py --test --index ../doha_index
```

**Troubleshooting:**

If you encounter issues with the download process (interrupted downloads, UNKNOWN outcomes, or missing cases), use these helper scripts:

```bash
# If download was interrupted and all_cases.json is missing/incomplete:
# This merges all checkpoint files back into all_cases.json
python merge_checkpoints.py

# If you have cases with UNKNOWN outcomes:
# This re-extracts metadata from the full_text of existing cases
python reprocess_cases.py

# Then continue with download_pdfs.py - it will resume from where it left off
python download_pdfs.py
```

**Performance:**
- **GitHub Codespaces**: ~5-6 cases per second
- **Local desktop**: ~1-2 cases per second
- Estimated time for full dataset (31,860 cases):
  - Codespaces: ~1.5-1.8 hours
  - Local: ~4.5-9 hours

**Important Notes:**
- Individual PDF URLs are protected by bot detection and require browser automation to download
- Downloads can be resumed - the script automatically skips already processed cases
- Checkpoints are saved every 50 cases to prevent data loss
- **Parquet format is automatically created** - stays under GitHub's 100MB limit (JSON will exceed this)
- Both JSON and Parquet are created: use JSON locally, commit Parquet to Git
- Default rate limit is 2 seconds between requests to be respectful to the DOHA servers

### Alternative: Build from Local Files

If you prefer manual downloads or have existing PDFs:

```bash
cd sead4_llm

# Build from local PDF files
python build_index.py --local-dir ../downloaded_cases --output ../doha_index

# Or from parsed case data (accepts both Parquet and JSON, prefers Parquet)
python build_index.py --from-cases ../doha_parsed_cases/all_cases.parquet --output ../doha_index
```

### Using the Index

Once built, enable precedent matching in your analysis (from sead4_llm/ directory):

```bash
cd sead4_llm

# Analyze with precedent matching (uses Gemini by default)
python analyze.py --input report.pdf --use-rag --index ../doha_index

# Use with Claude
python analyze.py --input report.pdf --use-rag --index ../doha_index --provider claude
```

**Note**: The built-in `--scrape` option in `build_index.py` uses HTTP requests which are blocked by bot protection. Use the root-level `run_full_scrape.py` script (with Playwright browser automation) instead for successful scraping.

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

**Analysis commands (from `sead4_llm/` directory):**
```bash
# Single document analysis
python analyze.py --input <file> [--output <path>] [--provider <gemini|claude>] [--use-rag] [--index <path>] [--verbose]

# Batch processing
python analyze.py --input-dir <directory> --output-dir <directory> [--provider <gemini|claude>] [--batch]

# Build DOHA index from cases (Parquet or JSON)
python build_index.py --from-cases <path> --output <path>

# Test existing index
python build_index.py --test --index <path>
```

**Scraping commands (from project root):**
```bash
# Collect case links
python run_full_scrape.py [--case-type <hearings|appeals|both>]

# Download and parse PDFs
python download_pdfs.py [--case-type <hearings|appeals|both>] [--max-cases <N>] [--force]
```

## References

### Official Resources

- **[CDSE Training Toolkits](https://www.cdse.edu/Training/Toolkits/)** - Center for Development of Security Excellence training resources
- **[Personnel Vetting Toolkit](https://www.cdse.edu/Training/Toolkits/Personnel-Vetting-Toolkit/#personnel-vetting-policy)** - Personnel vetting policy and procedures
- **[Adjudicator Toolkit](https://www.cdse.edu/Training/Toolkits/Adjudicator-Toolkit/)** - Resources for security clearance adjudicators

### Policy Documents

- **[SEAD-4 Adjudicative Guidelines](https://www.dni.gov/files/NCSC/documents/Regulations/SEAD-4-Adjudicative-Guidelines-U.pdf)** - Security Executive Agent Directive 4 (official guidelines used by this tool)
- **[SEAD-8 Temporary Eligibility](https://www.odni.gov/files/NCSC/documents/Regulations/SEAD-8_Temporary_Eligibility_U.pdf)** - Temporary eligibility standards
- **[Federal Personnel Vetting Guidelines](https://www.dni.gov/files/NCSC/documents/Regulations/Federal_Personnel_Vetting_Guidelines_10FEB2022-15Jul22.pdf)** - Federal personnel vetting standards and procedures
- **[Trusted Workforce Policy Index](https://assets.performance.gov/files/Trusted_Workforce_Policy_Index.pdf)** - Trusted Workforce 2.0 policy framework
- **[Suitability Guide for Employees](https://www.dcpas.osd.mil/sites/default/files/2021-04/Suitability_Guide_for_Employees.pdf)** - DOD suitability adjudication guide
- **[DoDI 5200.02](https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodi/520002p.pdf)** - DOD Personnel Security Program

## License

This project is intended for educational use only. It is provided as-is for learning purposes and should not be used for production security clearance adjudication or other official government purposes.
