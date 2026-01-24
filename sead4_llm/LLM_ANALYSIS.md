# SEAD-4 LLM Analyzer Package

LLM-powered analysis engine for evaluating security clearance reports against SEAD-4 adjudicative guidelines with explainable reasoning and precedent matching.

## Overview

This package provides the core analysis functionality for the DOHA project. It uses large language models (Google Gemini or Anthropic Claude) to analyze security clearance investigation reports and assess them against the 13 SEAD-4 adjudicative guidelines (A-M).

**Key Capabilities:**
- Guideline classification with confidence scores
- Specific disqualifier citations (e.g., "AG ¶ 19(a)")
- Mitigating condition analysis with applicability assessment
- Severity scoring (A-D scale)
- RAG-based precedent matching (optional)
- Batch processing support

## Quick Start

### Prerequisites

```bash
# Install package dependencies
pip install -r requirements.txt

# Set API key for your chosen provider
export GEMINI_API_KEY=your_key_here      # For Gemini (default)
# OR
export ANTHROPIC_API_KEY=your_key_here   # For Claude
```

### Basic Analysis (No Precedent Matching)

```bash
# Analyze a single report with Gemini
python analyze.py --input report.pdf --output result.json

# Use Claude instead
python analyze.py --input report.pdf --output result.json --provider claude

# Batch process multiple reports
python analyze.py --input-dir ./reports --output-dir ./results
```

### Analysis with Precedent Matching (RAG)

To use precedent matching, you need a DOHA case index. See the [root README](../README.md) for data collection instructions.

```bash
# With existing index
python analyze.py --input report.pdf --use-rag --index ../doha_index

# Batch processing with precedent matching
python analyze.py --input-dir ./reports --output-dir ./results --use-rag --index ../doha_index
```

## Package Structure

```
sead4_llm/
├── analyze.py                 # Main CLI entry point
├── build_index.py             # RAG index builder
├── requirements.txt           # Python dependencies
│
├── analyzers/                 # LLM provider implementations
│   ├── claude_analyzer.py     # Anthropic Claude integration
│   └── gemini_analyzer.py     # Google Gemini integration (default)
│
├── config/                    # Configuration and reference data
│   └── guidelines.py          # Complete SEAD-4 guidelines text
│
├── prompts/                   # LLM prompt engineering
│   └── templates.py           # Structured prompts for analysis
│
├── schemas/                   # Data models
│   └── models.py              # Pydantic schemas for structured output
│
└── rag/                       # Precedent matching (optional)
    ├── indexer.py             # Vector index builder
    ├── retriever.py           # Semantic search for similar cases
    ├── scraper.py             # Case text parser (URL patterns)
    └── browser_scraper.py     # Playwright-based scraper (see root)
```

## Command Reference

### analyze.py

Main analysis command:

```bash
python analyze.py \
  --input <file.pdf> \
  [--output <result.json>] \
  [--provider <gemini|claude>] \
  [--use-rag] \
  [--index <path>] \
  [--verbose]

# Batch mode
python analyze.py \
  --input-dir <directory> \
  --output-dir <directory> \
  [--provider <gemini|claude>] \
  [--use-rag] \
  [--index <path>]
```

**Options:**
- `--input` - Single PDF file to analyze
- `--input-dir` - Directory of PDFs for batch processing
- `--output` - Output JSON file path (default: `<input>_analysis.json`)
- `--output-dir` - Output directory for batch results
- `--provider` - LLM provider: `gemini` (default) or `claude`
- `--use-rag` - Enable precedent matching
- `--index` - Path to DOHA case index (required with `--use-rag`)
- `--verbose` - Detailed logging

### build_index.py

Build or update DOHA precedent index:

```bash
# Create new index from parsed cases (prefers Parquet format)
python build_index.py --from-cases <path> --output <index_dir>

# Update existing index with new cases only (incremental)
python build_index.py --from-cases <path> --output <index_dir> --update

# Build from local PDFs
python build_index.py --local-dir <pdf_dir> --output <index_dir>

# Test existing index
python build_index.py --test --index <index_dir>
```

**Options:**
- `--from-cases <path>` - Build from Parquet/JSON case data (prefers Parquet)
- `--local-dir <path>` - Build from directory of PDF files
- `--output <path>` - Output directory for index
- `--update` - Add only new cases to existing index (much faster)
- `--test` - Test index with sample query
- `--index <path>` - Existing index path (for `--test`)

**Note**: For data collection (scraping), see the [root README](../README.md) and [DOHA_SCRAPING_GUIDE](../DOHA_SCRAPING_GUIDE.md).

## Output Format

The analyzer produces structured JSON with this schema:

```json
{
  "case_id": "report_001",
  "overall_assessment": {
    "recommendation": "UNFAVORABLE|FAVORABLE",
    "confidence": 0.85,
    "summary": "Brief summary of security concerns or clearances"
  },
  "guidelines": [
    {
      "code": "F",
      "name": "Financial Considerations",
      "relevant": true,
      "severity": "A|B|C|D",
      "disqualifiers": [
        {
          "code": "AG ¶ 19(a)",
          "description": "inability to satisfy debts",
          "evidence": "Specific evidence from report..."
        }
      ],
      "mitigators": [
        {
          "code": "AG ¶ 20(b)",
          "description": "conditions beyond control",
          "applicability": "FULL|PARTIAL|NONE",
          "reasoning": "Why this mitigator applies or doesn't..."
        }
      ],
      "reasoning": "Detailed analysis of this guideline..."
    }
  ],
  "follow_up_recommendations": [
    "Suggested investigative actions..."
  ],
  "similar_precedents": [
    {
      "case_number": "22-01234",
      "outcome": "DENIED",
      "guidelines": ["F", "E"],
      "relevance_score": 0.87,
      "summary": "Brief case summary..."
    }
  ]
}
```

## LLM Providers

### Google Gemini (Default)

```bash
export GEMINI_API_KEY=your_key_here
python analyze.py --input report.pdf --provider gemini
```

- Model: `gemini-2.0-flash-exp`
- Fast and cost-effective
- Excellent structured output support

### Anthropic Claude

```bash
export ANTHROPIC_API_KEY=your_key_here
python analyze.py --input report.pdf --provider claude
```

- Model: `claude-sonnet-4-20250514`
- Superior reasoning on complex cases
- Better handling of nuanced mitigating factors

## Configuration

### Environment Variables

**Required (choose one):**
- `GEMINI_API_KEY` - Google Gemini API key
- `ANTHROPIC_API_KEY` - Anthropic Claude API key

**Optional:**
- `DOHA_INDEX_PATH` - Default path to DOHA case index

### Customizing Prompts

Prompts are defined in [`prompts/templates.py`](prompts/templates.py). You can modify these to:
- Adjust analysis depth
- Change output format
- Add domain-specific guidance
- Fine-tune reasoning style

### Guidelines Reference

The complete SEAD-4 guidelines are in [`config/guidelines.py`](config/guidelines.py). The analyzer references these when citing specific disqualifiers and mitigators.

## Understanding Severity Levels

The analyzer uses a 4-level severity scale:

| Level | Description | Example |
|-------|-------------|---------|
| **A** | Minor concerns, easily mitigated | Single late payment, now resolved |
| **B** | Moderate concerns, some mitigation | Multiple debts with payment plans |
| **C** | Serious concerns, limited mitigation | Ongoing financial problems, partial efforts |
| **D** | Severe concerns, little/no mitigation | Large unresolved debts, no mitigation |

## Precedent Matching (RAG)

The optional RAG system finds similar DOHA cases to inform analysis:

### How It Works

1. **Semantic Search**: Converts report text to embeddings
2. **Similarity Matching**: Finds cases with similar facts/guidelines
3. **Filtering**: Matches by relevant guidelines
4. **Ranking**: Returns top N most similar cases with scores

### Building the Index

The index requires:
- Parsed DOHA case data (JSON or Parquet format)
- sentence-transformers library
- ~5-10 minutes to build for ~31,000 cases

See [`../README.md`](../README.md) for data collection workflow.

### Updating the Index

For periodic updates (new DOHA cases):

```bash
# Collect new cases (from root directory)
cd ..
python download_pdfs.py

# Update index with new cases only (much faster)
cd sead4_llm
python build_index.py --from-cases ../doha_parsed_cases/all_cases.parquet --output ../doha_index --update
```

## Batch Processing

Process multiple reports efficiently:

```bash
# Basic batch
python analyze.py --input-dir ./pending_reports --output-dir ./results

# With precedent matching
python analyze.py \
  --input-dir ./pending_reports \
  --output-dir ./results \
  --use-rag \
  --index ../doha_index

# With Claude
python analyze.py \
  --input-dir ./pending_reports \
  --output-dir ./results \
  --provider claude
```

Output files are named: `<input_name>_analysis.json`

## Error Handling

The analyzer includes robust error handling:

- **PDF parsing failures**: Logged and skipped in batch mode
- **LLM API errors**: Retries with exponential backoff
- **Malformed PDFs**: Attempts text extraction fallbacks
- **Missing index**: Clear error message with setup instructions

Check logs for detailed error information with `--verbose`.

## Performance

Typical analysis times (single report):

| Configuration | Time |
|---------------|------|
| Gemini (no RAG) | 3-5 seconds |
| Gemini (with RAG) | 5-8 seconds |
| Claude (no RAG) | 5-7 seconds |
| Claude (with RAG) | 7-10 seconds |

Batch processing is parallelized where possible.

## Integration

### Python API

```python
from analyzers.gemini_analyzer import GeminiAnalyzer

# Initialize analyzer
analyzer = GeminiAnalyzer()

# Analyze text
report_text = "..."
result = analyzer.analyze(report_text)

# With precedent matching
from rag.retriever import PrecedentRetriever

retriever = PrecedentRetriever(index_path="./doha_index")
retriever.load()

result = analyzer.analyze(report_text, retriever=retriever)
```

### Custom Workflows

The package is modular - use components independently:

```python
# Just guideline classification
from analyzers.gemini_analyzer import GeminiAnalyzer
analyzer = GeminiAnalyzer()
guidelines = analyzer.classify_guidelines(text)

# Just precedent search
from rag.retriever import PrecedentRetriever
retriever = PrecedentRetriever(index_path="./doha_index")
retriever.load()
precedents = retriever.retrieve(query, guidelines=['F'], num_precedents=5)

# Just parse DOHA case
from rag.scraper import DOHALocalParser
parser = DOHALocalParser()
cases = parser.parse_directory("./pdfs")
```

## Troubleshooting

**"No module named 'sentence_transformers'"**
- Install with: `pip install sentence-transformers`
- Only needed for RAG/precedent matching

**"API key not found"**
- Set `GEMINI_API_KEY` or `ANTHROPIC_API_KEY`
- Verify environment variable: `echo $GEMINI_API_KEY`

**"Index not found at path"**
- Build index first: `python build_index.py --from-cases <data> --output <path>`
- Or omit `--use-rag` for analysis without precedent matching

**Poor analysis quality**
- Try Claude instead of Gemini: `--provider claude`
- Enable RAG for precedent matching: `--use-rag --index <path>`
- Check that PDF text extraction worked (use `--verbose`)

## Further Reading

- [Root README](../README.md) - Complete project overview and data collection
- [DOHA Scraping Guide](../DOHA_SCRAPING_GUIDE.md) - Detailed scraping instructions
- [SEAD-4 Guidelines](https://www.dni.gov/files/NCSC/documents/Regulations/SEAD-4-Adjudicative-Guidelines-U.pdf) - Official adjudicative guidelines

## License

This project is intended for educational use only. It is provided as-is for learning purposes and should not be used for production security clearance adjudication or other official government purposes.
