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

# Set your API key (Claude - default)
export ANTHROPIC_API_KEY=your_key_here

# Or use Google Gemini
export GOOGLE_API_KEY=your_key_here

# Analyze a single report (using Claude - default)
python analyze.py --input report.pdf --output result.json

# Analyze using Google Gemini
python analyze.py --input report.pdf --output result.json --provider gemini

# Analyze with precedent matching (requires DOHA index)
python analyze.py --input report.pdf --use-rag

# Batch process
python analyze.py --input-dir ./reports --output-dir ./results

# Batch process with Gemini
python analyze.py --input-dir ./reports --output-dir ./results --provider gemini
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
│   ├── base.py            # Base analyzer class
│   ├── claude_analyzer.py # Claude API implementation
│   └── gemini_analyzer.py # Google Gemini API implementation
├── rag/
│   ├── indexer.py         # DOHA case indexer
│   └── retriever.py       # Precedent retriever
├── parsers/
│   └── document.py        # PDF/text extraction
├── analyze.py             # Main entry point
└── requirements.txt
```

## Supported LLM Providers

| Provider | Model | Environment Variable |
|----------|-------|---------------------|
| Claude (default) | claude-sonnet-4-20250514 | `ANTHROPIC_API_KEY` |
| Google Gemini | gemini-2.0-flash | `GOOGLE_API_KEY` |

Use the `--provider` flag to select your LLM:
- `--provider claude` (default)
- `--provider gemini`

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

Environment variables:
- `ANTHROPIC_API_KEY` - Claude API key (required for Claude provider)
- `GOOGLE_API_KEY` - Google Gemini API key (required for Gemini provider)
- `DOHA_INDEX_PATH` - Path to DOHA vector index (for RAG)

## License

For government/educational use.
