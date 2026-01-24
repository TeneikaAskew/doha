# Quick Start - Demo UI

Get the SEAD-4 Analyzer Demo running in 3 minutes.

## 1. Install Dependencies

```bash
cd sead4_llm

# Base requirements
pip install -r requirements.txt

# Enhanced analyzer (ML/NLP)
pip install -r requirements-enhanced.txt

# Streamlit UI
pip install -r requirements-ui.txt
```

## 2. (Optional) Add Logos

```bash
# Add DCSA and DOHA logos for branding
# Place PNG files in assets/ directory:
assets/dcsa_logo.png  # DCSA logo (400x400px recommended)
assets/doha_logo.png  # DOHA logo (400x400px recommended)
```

If you don't add logos, the UI will show placeholder badges.

## 3. (Optional) Set API Key for LLM Analysis

```bash
export GEMINI_API_KEY=your_api_key_here
```

**Without API key:** Demo works fine, shows only Native analyzers (free, offline, fast)

**With API key:** Demo shows all 4 approaches including LLM and RAG (~$0.04 per analysis)

## 4. Run the Demo

```bash
streamlit run demo_ui.py
```

The UI will open automatically at `http://localhost:8501`

## Using the Demo

### Step 1: Select a Test Case
- In the sidebar, choose from available DOHA case reports
- Ground truth shown if available (PSH-25-0137, PSH-25-0214, PSH-25-0181)

### Step 2: Choose Analysis Options
- **Include LLM Analysis:** Check this if you have GEMINI_API_KEY and want to see LLM approaches
- **Uncheck** to run faster with just Native analyzers (no API calls)

### Step 3: Run Analysis
- Click **"Run Comparison Analysis"** button
- Wait for analysis (3-5s for native only, 45-60s with LLM)
- **Cached results** are loaded instantly if available (checks `llm_response_*.txt` files)

### Step 4: Explore Results
- **Tabs 1-2 (or 1-4):** Individual approach results
  - Overall assessment
  - Guidelines flagged
  - Detailed reasoning
  - Disqualifiers and mitigators

- **Comparison Tab:** Side-by-side comparison
  - Agreement status
  - Summary table
  - Ground truth validation (precision/recall)
  - Per-guideline comparison

## Features

### Caching
The demo automatically caches LLM results in `llm_response_*.txt` files:
- **PSH-25-0214_llm.txt** → LLM (no guidance) result
- **PSH-25-0214_enhanced_native_rag.txt** → Enhanced→LLM RAG result

If cached files exist, they're loaded instantly (no API calls, no cost).

### White Background Theme
The UI uses a clean white background with professional DCSA colors:
- Main area: White (#FFFFFF)
- Sidebar: Light gray (#f8f9fa)
- Accents: DCSA blue (#003d7a)

### Responsive Layout
- Wide layout for side-by-side comparisons
- Expandable guideline details
- Collapsible sections

## Test Cases

### PSH-25-0137 (Alcohol + PTSD)
- **Ground Truth:** G, I
- **Expected:** Basic Native over-flags (G, I, K), Enhanced correctly identifies (G, I)
- **Precision Test:** Shows enhanced native improvement

### PSH-25-0214 (DUI + Lack of Candor)
- **Ground Truth:** E, G
- **Expected:** Basic Native over-flags (E, G, I, J, K), Enhanced nearly correct (E, G, I)
- **Precision Test:** Demonstrates false positive reduction

### PSH-25-0181 (Alcohol Only)
- **Ground Truth:** G
- **Expected:** All approaches should agree on G only
- **Consistency Test:** Verifies agreement across methods

## Troubleshooting

### "test_reports/ directory not found"
```bash
# Ensure you're in the correct directory
cd sead4_llm
streamlit run demo_ui.py
```

### LLM Analysis Fails
```bash
# Check API key is set
echo $GEMINI_API_KEY

# Or uncheck "Include LLM Analysis" to run without LLM
```

### Port Already in Use
```bash
# Use different port
streamlit run demo_ui.py --server.port 8502
```

### Slow First Run
- Enhanced native downloads ML models (~80MB) on first use
- Subsequent runs use cached models
- Expected: ~10s first run, ~3s after

## Deployment

### Local Network
```bash
# Allow access from other devices on your network
streamlit run demo_ui.py --server.address 0.0.0.0
# Access at http://your-ip:8501
```

### Cloud (Streamlit Cloud)
1. Push repo to GitHub
2. Go to https://streamlit.io/cloud
3. Connect repository
4. Set `GEMINI_API_KEY` in Streamlit secrets
5. Deploy

## Next Steps

- Review [DEMO_UI.md](DEMO_UI.md) for full documentation
- Check [COMPARISON_MODES.md](COMPARISON_MODES.md) for CLI usage
- See [CONFIDENCE_CALCULATIONS.md](CONFIDENCE_CALCULATIONS.md) for how scores are calculated

## Support

For issues or questions:
- Check the main [README.md](README.md)
- Review [TROUBLESHOOTING.md](TROUBLESHOOTING.md) if it exists
- Open an issue on GitHub
