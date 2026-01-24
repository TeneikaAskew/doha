# SEAD-4 Analyzer Demo UI

Interactive web interface to compare all 4 analysis approaches side-by-side.

## Quick Start

### 1. Install Dependencies

```bash
# Base requirements
pip install -r requirements.txt

# Enhanced analyzer (ML/NLP)
pip install -r requirements-enhanced.txt

# UI framework
pip install -r requirements-ui.txt
```

### 2. (Optional) Set API Key for LLM Analysis

```bash
export GEMINI_API_KEY=your_api_key_here
```

**Note:** LLM analysis is optional. You can use the demo without an API key to see Native analyzers only.

### 3. Run the Demo

```bash
streamlit run demo_ui.py
```

The UI will open in your browser at `http://localhost:8501`

## Features

### 📁 Test Case Selection
- Choose from available DOHA case reports in `test_reports/`
- Ground truth displayed for validation cases (PSH-25-0137, PSH-25-0214, PSH-25-0181)

### 🔍 Analysis Approaches

The demo shows **4 different approaches** in separate tabs:

#### 1️⃣ Basic Native (Keyword-Only)
- Traditional keyword matching
- Pattern recognition
- **Speed:** ~100ms
- **Cost:** $0
- **Precision:** ~50%

#### 2️⃣ Enhanced Native (ML-Powered)
- N-gram phrase matching
- TF-IDF term weighting
- Semantic embeddings
- Contextual analysis
- **Speed:** ~3s
- **Cost:** $0
- **Precision:** ~83%

#### 3️⃣ LLM (No Guidance)
- Gemini 2.0 Flash
- Deep semantic understanding
- Independent analysis
- **Speed:** ~20s
- **Cost:** ~$0.02
- **Precision:** ~90%
- **Requires:** GEMINI_API_KEY

#### 4️⃣ Enhanced Native→LLM RAG
- Enhanced native identifies guidelines
- LLM performs focused deep analysis
- Best of both worlds
- **Speed:** ~23s
- **Cost:** ~$0.02
- **Precision:** ~95%
- **Requires:** GEMINI_API_KEY

### 📊 Comparison Tab

Shows side-by-side comparison including:
- Agreement indicator (all approaches agree?)
- Summary table with all results
- Ground truth validation (precision/recall)
- Guideline-by-guideline comparison
- False positive identification

## Usage

1. **Select a test case** from the sidebar dropdown
2. **Choose whether to include LLM** (requires API key, slower, costs money)
3. **Click "Run Comparison Analysis"**
4. **Explore results** in individual tabs
5. **Review comparison** in the Comparison tab

## Screenshots

### Welcome Screen
Shows overview of each approach with speed/cost/precision metrics.

### Analysis Tabs
Each approach gets its own tab showing:
- Overall assessment (recommendation + confidence)
- Guidelines flagged
- Detailed reasoning for each guideline
- Disqualifiers and mitigators

### Comparison Tab
Side-by-side comparison showing:
- Agreement status
- Summary table
- Ground truth validation
- Per-guideline comparison

## Tips

### Running Without LLM
If you don't have GEMINI_API_KEY or want faster analysis:
1. Uncheck "Include LLM Analysis" in sidebar
2. Only Basic Native and Enhanced Native will run
3. Still provides valuable comparison of rule-based vs ML approaches

### Ground Truth Cases
Three test cases have known ground truth:
- **PSH-25-0137**: Alcohol + PTSD → Should flag G, I
- **PSH-25-0214**: DUI + Lack of Candor → Should flag E, G
- **PSH-25-0181**: Alcohol only → Should flag G

These show precision/recall metrics in the Comparison tab.

### Performance
- First run loads ML models (~10s for enhanced native)
- Subsequent runs are faster (models cached)
- LLM calls add 20-30s each (2 calls for full comparison)

## Troubleshooting

### "GEMINI_API_KEY not set"
```bash
export GEMINI_API_KEY=your_key_here
```
Or uncheck "Include LLM Analysis" to run without LLM.

### "test_reports/ directory not found"
Make sure you're running from the `sead4_llm/` directory:
```bash
cd /workspaces/doha/sead4_llm
streamlit run demo_ui.py
```

### Slow First Run
The enhanced native analyzer downloads ML models on first use (~80MB).
Subsequent runs use cached models.

### Port Already in Use
```bash
streamlit run demo_ui.py --server.port 8502
```

## Deployment

### Local Network Access
```bash
streamlit run demo_ui.py --server.address 0.0.0.0
```
Access from other devices on your network at `http://your-ip:8501`

### Cloud Deployment
Streamlit Cloud (free):
1. Push to GitHub
2. Connect at https://streamlit.io/cloud
3. Set GEMINI_API_KEY in Streamlit Cloud secrets

## Development

### Adding New Test Cases
1. Add PDF to `test_reports/`
2. Optionally add ground truth to `GROUND_TRUTH` dict in `demo_ui.py`

### Customizing Display
Edit `demo_ui.py`:
- Modify tabs layout
- Add custom metrics
- Change styling with Streamlit themes

## License
Same as parent project.
