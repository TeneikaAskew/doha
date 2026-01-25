"""
SEAD-4 Analyzer Demo UI

Interactive Streamlit interface to compare all 4 analysis approaches:
- Basic Native (keyword-only)
- Enhanced Native (N-grams + TF-IDF + Embeddings)
- LLM (Independent)
- Enhanced LLM (RAG)
"""
import warnings
warnings.filterwarnings('ignore', message='.*google.generativeai.*', category=FutureWarning)

import logging
import time

# Configure logging - output to both console and file
# Put log file next to the script for easy access
from pathlib import Path as _Path
LOG_FILE = _Path(__file__).parent / "demo_ui_debug.log"

# Clear log file on module load (fresh start)
with open(LOG_FILE, 'w') as f:
    f.write("")

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d | %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler(LOG_FILE, mode='a')  # File output (append within session)
    ]
)
logger = logging.getLogger(__name__)

# Track script start time
_script_start = time.time()

def log_timing(message: str):
    """Log message with elapsed time since script start"""
    elapsed = time.time() - _script_start
    logger.info(f"[{elapsed:6.2f}s] {message}")

log_timing("")
log_timing("=" * 60)
log_timing("=== SCRIPT RERUN START ===")
log_timing(f"Logs writing to: {LOG_FILE}")

import streamlit as st
log_timing("Imported streamlit")
from pathlib import Path
import fitz  # PyMuPDF
import json
from datetime import datetime
import base64
import os
import pandas as pd

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from analyzers.native_analyzer import NativeSEAD4Analyzer
from analyzers.gemini_analyzer import GeminiSEAD4Analyzer
from schemas.models import SEAD4AnalysisResult

# Lazy import for heavy ML dependencies with background loading
# This makes the app start instantly, then loads models in background
@st.cache_resource
def get_enhanced_analyzer_instance():
    """
    Lazy import and cache of EnhancedNativeSEAD4Analyzer INSTANCE.
    First call downloads ML models (~80MB) and creates instance, subsequent calls reuse.
    """
    log_timing("get_enhanced_analyzer_instance: Importing and creating instance...")
    from analyzers.enhanced_native_analyzer import EnhancedNativeSEAD4Analyzer
    instance = EnhancedNativeSEAD4Analyzer(use_embeddings=True)
    log_timing("get_enhanced_analyzer_instance: Instance ready with loaded model")
    return instance


@st.cache_resource
def get_gemini_parser():
    """
    Lazy import and cache of GeminiSEAD4Analyzer for parsing cached results.
    First call imports google.generativeai (~15-20s), subsequent calls use cache.
    """
    log_timing("get_gemini_parser: Starting (this may take 15-20s on first call)")
    # Create analyzer with dummy key just for parsing
    import os
    original_key = os.getenv("GEMINI_API_KEY")
    os.environ["GEMINI_API_KEY"] = "dummy_key_for_cache_parsing"

    try:
        analyzer = GeminiSEAD4Analyzer()
        log_timing("get_gemini_parser: Created analyzer")
        return analyzer
    finally:
        # Restore original key
        if original_key:
            os.environ["GEMINI_API_KEY"] = original_key
        else:
            os.environ.pop("GEMINI_API_KEY", None)


def get_api_key() -> str | None:
    """Get GEMINI_API_KEY from Streamlit secrets or environment"""
    # Try Streamlit secrets first (for cloud deployment)
    try:
        if hasattr(st, 'secrets') and 'GEMINI_API_KEY' in st.secrets:
            return st.secrets['GEMINI_API_KEY']
    except Exception:
        pass

    # Fall back to environment variable
    return os.getenv('GEMINI_API_KEY')


def display_pdf(file_path: Path, document_text: str = None):
    """Display PDF using PDF.js for cross-platform compatibility"""
    with open(file_path, "rb") as f:
        pdf_bytes = f.read()
        base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')

    # PDF.js viewer with inline rendering
    pdf_js_html = f'''
    <div id="pdf-container" style="width:100%; height:700px; overflow:auto; border:1px solid #ddd; background:#f5f5f5;">
        <canvas id="pdf-canvas"></canvas>
    </div>
    <div style="margin-top:10px;">
        <button onclick="prevPage()" style="padding:5px 15px; margin-right:5px;">◀ Prev</button>
        <span id="page-info">Page 1 of 1</span>
        <button onclick="nextPage()" style="padding:5px 15px; margin-left:5px;">Next ▶</button>
    </div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
    <script>
        var pdfData = atob("{base64_pdf}");
        var pdfjsLib = window['pdfjs-dist/build/pdf'];
        pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

        var pdfDoc = null;
        var pageNum = 1;
        var canvas = document.getElementById('pdf-canvas');
        var ctx = canvas.getContext('2d');

        function renderPage(num) {{
            pdfDoc.getPage(num).then(function(page) {{
                var container = document.getElementById('pdf-container');
                var baseViewport = page.getViewport({{scale: 1}});
                var scale = (container.clientWidth - 20) / baseViewport.width;
                var viewport = page.getViewport({{scale: scale}});
                canvas.height = viewport.height;
                canvas.width = viewport.width;
                page.render({{canvasContext: ctx, viewport: viewport}});
                document.getElementById('page-info').textContent = 'Page ' + num + ' of ' + pdfDoc.numPages;
            }});
        }}

        function prevPage() {{ if (pageNum > 1) {{ pageNum--; renderPage(pageNum); }} }}
        function nextPage() {{ if (pageNum < pdfDoc.numPages) {{ pageNum++; renderPage(pageNum); }} }}

        var loadingTask = pdfjsLib.getDocument({{data: pdfData}});
        loadingTask.promise.then(function(pdf) {{
            pdfDoc = pdf;
            renderPage(1);
        }});
    </script>
    '''

    st.components.v1.html(pdf_js_html, height=800)

    # Download button as backup
    st.download_button(
        label="Download PDF",
        data=pdf_bytes,
        file_name=file_path.name,
        mime="application/pdf"
    )


@st.cache_data
def load_case_statistics():
    """Load and cache case statistics from parquet file(s)

    Handles both single file (all_cases.parquet) and split files
    (all_cases_1.parquet, all_cases_2.parquet, etc.)
    Prefers split files to avoid duplicates if both exist.
    """
    parquet_dir = Path(__file__).parent.parent / "doha_parsed_cases"

    # Check for split files FIRST (all_cases_1.parquet, all_cases_2.parquet, etc.)
    # to avoid loading both single and split files which causes duplicates
    split_files = sorted(parquet_dir.glob("all_cases_*.parquet"))
    if split_files:
        dfs = []
        for f in split_files:
            dfs.append(pd.read_parquet(f, columns=['case_number', 'outcome', 'guidelines', 'date']))
        df = pd.concat(dfs, ignore_index=True)
        return df

    # Fallback to single file
    single_file = parquet_dir / "all_cases.parquet"
    if single_file.exists():
        df = pd.read_parquet(single_file, columns=['case_number', 'outcome', 'guidelines', 'date'])
        return df

    return None


@st.fragment
def analyst_assessment_form(case_id: str, sead4_guidelines: dict):
    """Fragment for analyst assessment - reruns independently from main page"""
    log_timing(f">>> FRAGMENT START (case_id={case_id})")
    st.markdown("**Analyst Assessment**")
    st.caption("Record your independent analysis of this case")

    # Initialize session state for analyst input if not exists
    if 'analyst_guidelines' not in st.session_state:
        st.session_state.analyst_guidelines = []
    if 'analyst_assessments' not in st.session_state:
        st.session_state.analyst_assessments = {}

    # Guideline multi-select with change detection
    previous_guidelines = st.session_state.analyst_guidelines.copy() if st.session_state.analyst_guidelines else []

    selected_guidelines = st.multiselect(
        "Select applicable SEAD-4 Guidelines:",
        options=list(sead4_guidelines.keys()),
        format_func=lambda x: f"{x}: {sead4_guidelines[x]}",
        default=st.session_state.analyst_guidelines,
        help="Select all guidelines that apply to this case"
    )

    # Log changes
    if selected_guidelines != previous_guidelines:
        added = set(selected_guidelines) - set(previous_guidelines)
        removed = set(previous_guidelines) - set(selected_guidelines)
        if added:
            log_timing(f"MULTISELECT: Added {added}")
        if removed:
            log_timing(f"MULTISELECT: Removed {removed}")

    st.session_state.analyst_guidelines = selected_guidelines

    st.divider()

    # For each selected guideline, get severity and justification
    if selected_guidelines:
        st.markdown("**Guideline Details**")

        for guideline in selected_guidelines:
            with st.expander(f"**{guideline}: {sead4_guidelines[guideline]}**", expanded=True):
                # Severity selection
                severity_key = f"severity_{guideline}"
                severity = st.selectbox(
                    "Severity Level:",
                    options=['A', 'B', 'C', 'D'],
                    key=severity_key,
                    help="A=Minimal, B=Low, C=Moderate, D=High"
                )

                # Justification text
                justification_key = f"justification_{guideline}"
                justification = st.text_area(
                    "Justification:",
                    key=justification_key,
                    height=100,
                    placeholder="Explain why this guideline applies and the severity level chosen..."
                )

                # Store in session state
                st.session_state.analyst_assessments[guideline] = {
                    'severity': severity,
                    'justification': justification
                }

        st.divider()

        # Overall recommendation
        overall_recommendation = st.radio(
            "Overall Recommendation:",
            options=['FAVORABLE', 'UNFAVORABLE'],
            help="Your final recommendation for this case"
        )
        st.session_state.analyst_overall = overall_recommendation

        # Save button
        if st.button("Save Analyst Assessment", type="primary"):
            # Save to JSON file
            analyst_data = {
                'case_id': case_id,
                'guidelines': selected_guidelines,
                'assessments': st.session_state.analyst_assessments,
                'overall_recommendation': overall_recommendation,
                'timestamp': datetime.now().isoformat()
            }

            analyst_file = Path("analysis_results") / f"{case_id}_analyst.json"
            analyst_file.parent.mkdir(exist_ok=True)

            with open(analyst_file, 'w') as f:
                json.dump(analyst_data, f, indent=2)

            st.success(f"Analyst assessment saved to {analyst_file.name}")

    else:
        st.info("Select one or more guidelines above to begin your assessment")

    log_timing(f"<<< FRAGMENT END (case_id={case_id})")


def load_cached_llm_result(case_id: str, suffix: str) -> tuple[SEAD4AnalysisResult | None, dict | None]:
    """
    Load cached LLM result from llm_cache/llm_response_*.txt file if it exists

    Args:
        case_id: Case ID (e.g., "PSH-25-0214")
        suffix: Suffix like "llm", "native_rag", "enhanced_native_rag"

    Returns:
        Tuple of (SEAD4AnalysisResult, usage_dict) if cached file exists and can be parsed,
        (None, None) otherwise. usage_dict may be None if no metadata file exists.
    """
    cache_file = Path("llm_cache") / f"llm_response_{case_id}_{suffix}.txt"
    meta_file = Path("llm_cache") / f"llm_response_{case_id}_{suffix}_meta.json"
    log_timing(f"load_cached_llm_result: Checking {cache_file}")

    if not cache_file.exists():
        log_timing(f"load_cached_llm_result: File not found")
        return None, None

    try:
        log_timing(f"load_cached_llm_result: Reading file...")
        # Read cached response (use UTF-8 for Windows compatibility)
        response_text = cache_file.read_text(encoding='utf-8')

        # Use cached parser instance (fast after first load)
        log_timing(f"load_cached_llm_result: Getting parser...")
        parser = get_gemini_parser()
        log_timing(f"load_cached_llm_result: Parsing response...")
        result = parser._parse_response(response_text, f"{case_id}_{suffix}", "")
        log_timing(f"load_cached_llm_result: Done")

        # Load usage metadata if it exists
        usage = None
        if meta_file.exists():
            try:
                import json
                usage = json.loads(meta_file.read_text(encoding='utf-8'))
                log_timing(f"load_cached_llm_result: Loaded usage metadata")
            except Exception:
                pass

        st.caption(f"Loaded from cache: {cache_file.name}")
        return result, usage
    except Exception as e:
        log_timing(f"load_cached_llm_result: FAILED - {e}")
        st.warning(f"Failed to load cache {cache_file.name}: {e}")
        return None, None


def save_llm_cache_metadata(case_id: str, suffix: str, usage: dict):
    """Save usage metadata alongside the cached LLM response."""
    import json
    cache_dir = Path("llm_cache")
    cache_dir.mkdir(exist_ok=True)
    meta_file = cache_dir / f"llm_response_{case_id}_{suffix}_meta.json"
    meta_file.write_text(json.dumps(usage, indent=2), encoding='utf-8')
    log_timing(f"Saved usage metadata to {meta_file.name}")


# Page config
st.set_page_config(
    page_title="SEAD-4 Analyzer Comparison Demo",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for professional design
st.markdown("""
<style>
    /* Main area */
    .main {
        background-color: #ffffff;
        padding: 2rem;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #f8f9fa;
        border-right: 1px solid #e1e4e8;
    }

    /* DCSA brand colors */
    .dcsa-blue {
        color: #003d7a;
        font-weight: 600;
    }

    .text-muted {
        color: #6c757d;
        font-size: 0.9rem;
    }

    /* Typography */
    h1 {
        font-weight: 700;
        letter-spacing: -0.5px;
        margin-bottom: 0.5rem;
    }

    h2 {
        font-weight: 600;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }

    h3 {
        font-weight: 600;
        font-size: 1.1rem;
        margin-top: 1.5rem;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        background-color: #ffffff;
        border-bottom: 1px solid #e1e4e8;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border: none;
        padding: 0.75rem 1.5rem;
        font-weight: 500;
        color: #6c757d;
    }

    .stTabs [aria-selected="true"] {
        background-color: transparent;
        border-bottom: 2px solid #003d7a;
        color: #003d7a;
    }

    /* Metrics */
    [data-testid="stMetricValue"] {
        font-size: 1.5rem;
        font-weight: 600;
    }

    /* Cards and containers */
    .element-container {
        margin-bottom: 1rem;
    }

    /* Buttons */
    .stButton > button {
        font-weight: 500;
        border-radius: 6px;
        padding: 0.5rem 1.5rem;
    }

    /* Expanders */
    .streamlit-expanderHeader {
        font-weight: 500;
        background-color: #f8f9fa;
        border-radius: 4px;
    }

    /* Status messages */
    .stSuccess, .stWarning, .stError, .stInfo {
        border-radius: 6px;
        padding: 1rem;
    }

    /* PDF viewer improvements */
    iframe {
        border: 1px solid #e1e4e8;
        border-radius: 6px;
    }
</style>

<script>
    // Auto-collapse sidebar when on Document View tab
    const observer = new MutationObserver(() => {
        const tabs = document.querySelectorAll('[data-baseweb="tab"]');
        if (tabs.length > 0) {
            const firstTab = tabs[0];
            if (firstTab.getAttribute('aria-selected') === 'true') {
                // Document View tab is active - collapse sidebar
                const sidebar = document.querySelector('[data-testid="stSidebar"]');
                const collapseButton = document.querySelector('[data-testid="collapsedControl"]');
                if (sidebar && sidebar.getAttribute('aria-expanded') === 'true' && collapseButton) {
                    collapseButton.click();
                }
            }
        }
    });

    observer.observe(document.body, { childList: true, subtree: true });
</script>
""", unsafe_allow_html=True)

# Get script directory for asset paths (works on Streamlit Cloud and locally)
script_dir = Path(__file__).parent

# Header with logos
col_dcsa_logo, col_doha_logo, col_title = st.columns([1, 1, 4])

with col_dcsa_logo:
    # Check if DCSA logo exists, otherwise show placeholder
    # Use path relative to script file (works on Streamlit Cloud and locally)
    dcsa_logo_path = script_dir / "assets" / "dcsa_logo.png"
    if dcsa_logo_path.exists():
        st.image(str(dcsa_logo_path), width=100)
    else:
        # Placeholder - user should add their logo to assets/dcsa_logo.png
        st.markdown("""
        <div style="width:100px; height:100px; background-color:#003d7a;
                    display:flex; align-items:center; justify-content:center;
                    border-radius:10px; color:white; font-weight:bold; font-size:14px;">
            DCSA
        </div>
        """, unsafe_allow_html=True)

with col_doha_logo:
    # Check if DOHA logo exists, otherwise show placeholder
    # Use path relative to script file (works on Streamlit Cloud and locally)
    doha_logo_path = script_dir / "assets" / "doha_logo.png"
    if doha_logo_path.exists():
        st.image(str(doha_logo_path), width=100)
    else:
        # Placeholder - user should add their logo to assets/doha_logo.png
        st.markdown("""
        <div style="width:100px; height:100px; background-color:#1a472a;
                    display:flex; align-items:center; justify-content:center;
                    border-radius:10px; color:white; font-weight:bold; font-size:14px;">
            DOHA
        </div>
        """, unsafe_allow_html=True)

with col_title:
    st.markdown('<h1 class="dcsa-blue">SEAD-4 Security Clearance Analyzer</h1>', unsafe_allow_html=True)
    st.markdown('<p class="text-muted">DOHA Case Analysis - Assessing Case Outcomes Based on DOHA Precedent<br>Using a multi-model approach to evaluation</p>', unsafe_allow_html=True)

st.divider()

# Set up API key (try secrets first, then environment)
api_key = get_api_key()
if api_key:
    os.environ['GEMINI_API_KEY'] = api_key

# SEAD-4 Guidelines for analyst input
SEAD4_GUIDELINES = {
    'A': 'Allegiance to the United States',
    'B': 'Foreign Influence',
    'C': 'Foreign Preference',
    'D': 'Sexual Behavior',
    'E': 'Personal Conduct',
    'F': 'Financial Considerations',
    'G': 'Alcohol Consumption',
    'H': 'Drug Involvement and Substance Misuse',
    'I': 'Psychological Conditions',
    'J': 'Criminal Conduct',
    'K': 'Handling Protected Information',
    'L': 'Outside Activities',
    'M': 'Use of Information Technology'
}

# Sidebar - File selection
st.sidebar.header("Select Test Case")

test_reports_dir = script_dir / "test_reports"
if test_reports_dir.exists():
    pdf_files = sorted(test_reports_dir.glob("*.pdf"))
    pdf_names = [f.name for f in pdf_files]

    selected_file = st.sidebar.selectbox(
        "Choose a DOE HA case report:",
        pdf_names,
        help="Select from available test cases"
    )

    selected_path = test_reports_dir / selected_file

    log_timing(f"File selected: {selected_file}")

    # Reset state when file selection changes
    if 'last_selected_file' not in st.session_state:
        st.session_state.last_selected_file = selected_file
        log_timing("First file selection (initialized last_selected_file)")
    elif st.session_state.last_selected_file != selected_file:
        log_timing(f"FILE CHANGED: {st.session_state.last_selected_file} -> {selected_file}")
        st.session_state.last_selected_file = selected_file
        st.session_state.analyses_run = False  # Reset so analyses don't auto-run
        # Reset analyst assessment for new case
        st.session_state.analyst_guidelines = []
        st.session_state.analyst_assessments = {}
        st.session_state.pop('analyst_overall', None)
        # Clear dynamic widget keys (severity_X, justification_X)
        keys_to_remove = [k for k in st.session_state.keys()
                         if k.startswith('severity_') or k.startswith('justification_')]
        for k in keys_to_remove:
            del st.session_state[k]
else:
    st.sidebar.error("test_reports/ directory not found")
    st.stop()

# Ground truth mapping (if known)
GROUND_TRUTH = {
    "PSH-25-0137.pdf": {"guidelines": ["G", "I"], "outcome": "UNFAVORABLE"},
    "PSH-25-0145.pdf": {"guidelines": ["F"], "outcome": "UNFAVORABLE"},
    "PSH-25-0148.pdf": {"guidelines": ["I"], "outcome": "UNFAVORABLE"},
    "PSH-25-0151.pdf": {"guidelines": ["G"], "outcome": "UNFAVORABLE"},
    "PSH-25-0155.pdf": {"guidelines": ["I", "J"], "outcome": "UNFAVORABLE"},
    "PSH-25-0167.pdf": {"guidelines": ["F", "I"], "outcome": "UNFAVORABLE"},
    "PSH-25-0170.pdf": {"guidelines": ["G"], "outcome": "UNFAVORABLE"},
    "PSH-25-0181.pdf": {"guidelines": ["G"], "outcome": "UNFAVORABLE"},
    "PSH-25-0206.pdf": {"guidelines": ["E", "F"], "outcome": "UNFAVORABLE"},
    "PSH-25-0214.pdf": {"guidelines": ["E", "G"], "outcome": "UNFAVORABLE"}
}

# Show ground truth if available
case_id = selected_file.replace(".pdf", "")
if selected_file in GROUND_TRUTH:
    st.sidebar.success("Ground Truth Available")
    gt = GROUND_TRUTH[selected_file]
    st.sidebar.markdown(f"**Expected Guidelines:** {', '.join(gt['guidelines'])}")
    st.sidebar.markdown(f"**Expected Outcome:** {gt['outcome']}")
else:
    st.sidebar.info("Ground truth not available for this case")

# Analysis options
st.sidebar.header("Analysis Options")
include_llm = st.sidebar.checkbox(
    "Include LLM Analysis",
    value=True,
    help="Requires GEMINI_API_KEY (slower, costs ~$0.04)"
)

if not include_llm:
    st.sidebar.warning("LLM disabled — showing Native analyzers only")

# Initialize state
if 'case_results' not in st.session_state:
    st.session_state.case_results = {}  # {case_id: {'native': result, 'enhanced': result, ...}}

log_timing(f"include_llm={include_llm}")

# Main area - loads immediately when file is selected
log_timing(">>> MAIN BLOCK START")

# Load PDF text
doc = fitz.open(selected_path)
document_text = ""
for page in doc:
    document_text += page.get_text()
doc.close()

# Get or initialize results for this case
if case_id not in st.session_state.case_results:
    st.session_state.case_results[case_id] = {}
results = st.session_state.case_results[case_id]

# Create tabs - analysis tabs only functional if analyses have run
if include_llm:
    tab_pdf, tab1, tab2, tab3, tab4, tab_compare, tab_dashboard = st.tabs([
        "Document View",
        "Basic Native",
        "Enhanced Native",
        "LLM (Independent)",
        "Enhanced LLM (RAG)",
        "Comparison",
        "Dashboard"
    ])
else:
    tab_pdf, tab1, tab2, tab_compare, tab_dashboard = st.tabs([
        "Document View",
        "Basic Native",
        "Enhanced Native",
        "Comparison",
        "Dashboard"
    ])

# Document View Tab - Always available instantly
with tab_pdf:
    log_timing("Rendering Document View tab")
    st.subheader("Case Document & Analyst Assessment")
    st.markdown(f"**Viewing: {selected_file} — Loaded {len(document_text):,} characters from PDF. Review the case document below.**")

    col_pdf, col_analyst = st.columns([2, 1])

    with col_pdf:
        display_pdf(selected_path)

    with col_analyst:
        analyst_assessment_form(case_id, SEAD4_GUIDELINES)

# 1. Basic Native - auto-runs when tab is viewed
with tab1:
    log_timing("Rendering Basic Native tab")
    st.subheader("Basic Native")
    st.caption("Keyword matching and pattern recognition")

    # Auto-run if not already done
    if 'native' not in results:
        with st.status("Running Basic Native analysis...", expanded=True) as status:
            st.write("Analyzing document with keyword matching...")
            log_timing("Basic Native: RUNNING...")
            native_analyzer = NativeSEAD4Analyzer()
            results['native'] = native_analyzer.analyze(document_text, case_id=f"{case_id}_native")
            log_timing("Basic Native: COMPLETE")
            status.update(label="Analysis complete!", state="complete", expanded=False)
    else:
        # Calculate precision against ground truth if available
        native_relevant = [g.code for g in results['native'].get_relevant_guidelines()]
        native_set = set(native_relevant)
        gt_guidelines = set(GROUND_TRUTH[selected_file]['guidelines']) if selected_file in GROUND_TRUTH else None
        if gt_guidelines and native_set:
            native_precision = len(gt_guidelines & native_set) / len(native_set)
            native_precision_display = f"{native_precision:.2%}"
        else:
            native_precision_display = "N/A"

        col_metric1, col_metric2, col_metric3 = st.columns(3)
        with col_metric1:
            st.metric("Speed", "~100ms")
        with col_metric2:
            st.metric("Cost", "$0")
        with col_metric3:
            st.metric("Precision", native_precision_display)

        st.divider()
        st.success("Analysis complete")

        col1, col2 = st.columns([1, 2])

        with col1:
            st.markdown("**Overall Assessment**")
            result = results['native']
            st.metric("Recommendation", result.overall_assessment.recommendation.value)
            st.metric("Confidence", f"{result.overall_assessment.confidence:.2%}")

            relevant = result.get_relevant_guidelines()
            st.metric("Guidelines Flagged", len(relevant))
            if relevant:
                st.write("**Flagged:** " + ", ".join([g.code for g in relevant]))

        with col2:
            st.markdown("**Relevant Guidelines**")
            for g in results['native'].get_relevant_guidelines():
                with st.expander(f"**{g.code}. {g.name}** - Severity {g.severity.value if g.severity else 'N/A'} (Confidence: {g.confidence:.2%})"):
                    st.write(f"**Reasoning:** {g.reasoning}")
                    if g.disqualifiers:
                        st.write(f"**Disqualifiers ({len(g.disqualifiers)}):**")
                        for d in g.disqualifiers:
                            st.write(f"- {d.code}: {d.text[:100]}...")

# 2. Enhanced Native - auto-runs when tab is viewed
with tab2:
    log_timing("Rendering Enhanced Native tab")
    st.subheader("Enhanced Native")
    st.caption("N-grams + TF-IDF + Semantic Embeddings + Contextual Analysis")

    if 'enhanced' not in results:
        with st.status("Running Enhanced Native analysis...", expanded=True) as status:
            st.write("Loading ML models (sentence transformers)...")
            log_timing("Enhanced Native: RUNNING...")
            enhanced_analyzer = get_enhanced_analyzer_instance()
            st.write("Analyzing document with ML models...")
            results['enhanced'] = enhanced_analyzer.analyze(document_text, case_id=f"{case_id}_enhanced")
            log_timing("Enhanced Native: COMPLETE")
            status.update(label="Analysis complete!", state="complete", expanded=False)
    else:
        # Calculate precision against ground truth if available
        enhanced_relevant = [g.code for g in results['enhanced'].get_relevant_guidelines()]
        enhanced_set = set(enhanced_relevant)
        gt_guidelines = set(GROUND_TRUTH[selected_file]['guidelines']) if selected_file in GROUND_TRUTH else None
        if gt_guidelines and enhanced_set:
            enhanced_precision = len(gt_guidelines & enhanced_set) / len(enhanced_set)
            enhanced_precision_display = f"{enhanced_precision:.2%}"
        else:
            enhanced_precision_display = "N/A"

        col_metric1, col_metric2, col_metric3 = st.columns(3)
        with col_metric1:
            st.metric("Speed", "~3s")
        with col_metric2:
            st.metric("Cost", "$0")
        with col_metric3:
            st.metric("Precision", enhanced_precision_display)

        st.divider()
        st.success("Analysis complete")

        col1, col2 = st.columns([1, 2])

        with col1:
            st.markdown("**Overall Assessment**")
            result = results['enhanced']
            st.metric("Recommendation", result.overall_assessment.recommendation.value)
            st.metric("Confidence", f"{result.overall_assessment.confidence:.2%}")

            relevant = result.get_relevant_guidelines()
            st.metric("Guidelines Flagged", len(relevant))
            if relevant:
                st.write("**Flagged:** " + ", ".join([g.code for g in relevant]))

        with col2:
            st.markdown("**Relevant Guidelines**")
            for g in results['enhanced'].get_relevant_guidelines():
                with st.expander(f"**{g.code}. {g.name}** - Severity {g.severity.value if g.severity else 'N/A'} (Confidence: {g.confidence:.2%})"):
                    st.write(f"**Reasoning:** {g.reasoning}")
                    if g.disqualifiers:
                        st.write(f"**Disqualifiers ({len(g.disqualifiers)}):**")
                        for d in g.disqualifiers:
                            st.write(f"- {d.code}: {d.text[:100]}...")

# 3. LLM (if enabled) - auto-runs when tab is viewed
if include_llm:
    with tab3:
        log_timing("Rendering LLM tab")
        st.subheader("LLM Analysis (Independent)")
        st.caption("Gemini 2.0 Flash analyzing independently - no pre-filtering from native analyzer")

        if 'llm' not in results:
            # Try loading from file cache first
            cached_llm, cached_usage = load_cached_llm_result(case_id, "llm")
            if cached_llm:
                results['llm'] = cached_llm
                st.session_state['llm_from_cache'] = True
                if cached_usage:
                    st.session_state['llm_usage'] = cached_usage
            elif not api_key:
                st.warning("No API key configured. Set GEMINI_API_KEY to run LLM analysis.")
            else:
                with st.status("Running LLM analysis...", expanded=True) as status:
                    st.write("Calling Gemini API...")
                    log_timing("LLM: RUNNING...")
                    llm_analyzer = GeminiSEAD4Analyzer()
                    results['llm'] = llm_analyzer.analyze(document_text, case_id=f"{case_id}_llm")
                    # Capture token usage for cost calculation and save to cache
                    if llm_analyzer.get_last_usage():
                        st.session_state['llm_usage'] = llm_analyzer.get_last_usage()
                        save_llm_cache_metadata(case_id, "llm", llm_analyzer.get_last_usage())
                    st.session_state['llm_from_cache'] = False
                    log_timing("LLM: COMPLETE")
                    status.update(label="Analysis complete!", state="complete", expanded=False)
                    # Rerun to display results
                    st.rerun()
        if 'llm' in results:
            # Get actual cost from usage data if available
            llm_usage = st.session_state.get('llm_usage')
            llm_from_cache = st.session_state.get('llm_from_cache', False)
            if llm_usage:
                llm_cost_display = f"${llm_usage['total_cost']:.4f}"
            elif llm_from_cache:
                llm_cost_display = "(cached)"
            else:
                llm_cost_display = "~$0.02"

            # Calculate precision against ground truth if available
            llm_relevant = [g.code for g in results['llm'].get_relevant_guidelines()]
            llm_set = set(llm_relevant)
            gt_guidelines = set(GROUND_TRUTH[selected_file]['guidelines']) if selected_file in GROUND_TRUTH else None
            if gt_guidelines and llm_set:
                llm_precision = len(gt_guidelines & llm_set) / len(llm_set)
                llm_precision_display = f"{llm_precision:.2%}"
            else:
                llm_precision_display = "N/A"

            col_metric1, col_metric2, col_metric3 = st.columns(3)
            with col_metric1:
                st.metric("Speed", "~20s")
            with col_metric2:
                st.metric("Cost", llm_cost_display)
            with col_metric3:
                st.metric("Precision", llm_precision_display)

            st.divider()
            st.success("Analysis complete")

            col1, col2 = st.columns([1, 2])

            with col1:
                st.markdown("**Overall Assessment**")
                result = results['llm']
                st.metric("Recommendation", result.overall_assessment.recommendation.value)
                st.metric("Confidence", f"{result.overall_assessment.confidence:.2%}")

                relevant = result.get_relevant_guidelines()
                st.metric("Guidelines Flagged", len(relevant))
                if relevant:
                    st.write("**Flagged:** " + ", ".join([g.code for g in relevant]))

            with col2:
                st.markdown("**Relevant Guidelines**")
                for g in results['llm'].get_relevant_guidelines():
                    with st.expander(f"**{g.code}. {g.name}** - Severity {g.severity.value if g.severity else 'N/A'} (Confidence: {g.confidence:.2%})"):
                        st.write(f"**Reasoning:** {g.reasoning}")
                        if g.disqualifiers:
                            st.write(f"**Disqualifiers ({len(g.disqualifiers)}):**")
                            for d in g.disqualifiers:
                                st.write(f"- {d.code}: {d.text[:100]}...")

    # 4. Enhanced LLM (RAG) - runs independently, needs Enhanced Native first
    with tab4:
        log_timing("Rendering Enhanced LLM (RAG) tab")
        st.subheader("Enhanced LLM (RAG)")
        st.caption("Enhanced native guides LLM for focused analysis")

        if 'rag' not in results:
            # Try loading from file cache first
            cached_rag, cached_usage = load_cached_llm_result(case_id, "enhanced_native_rag")
            if cached_rag:
                results['rag'] = cached_rag
                st.session_state['rag_from_cache'] = True
                if cached_usage:
                    st.session_state['rag_usage'] = cached_usage
            elif not api_key:
                st.warning("No API key configured. Set GEMINI_API_KEY to run RAG analysis.")
            elif 'enhanced' not in results:
                st.warning("RAG analysis requires Enhanced Native results first. Click the Enhanced Native tab first.")
            else:
                with st.status("Running RAG analysis...", expanded=True) as status:
                    st.write("Preparing native guidance from Enhanced Native...")
                    native_guidance = {
                        'relevant_guidelines': [g.code for g in results['enhanced'].get_relevant_guidelines()],
                        'severe_concerns': [g.code for g in results['enhanced'].get_relevant_guidelines()
                                           if g.severity and g.severity.value in ['C', 'D']],
                        'recommendation': results['enhanced'].overall_assessment.recommendation.value,
                        'confidence': results['enhanced'].overall_assessment.confidence,
                        'key_concerns': results['enhanced'].overall_assessment.key_concerns
                    }
                    st.write("Calling Gemini API with native guidance...")
                    log_timing("RAG: RUNNING...")
                    llm_analyzer = GeminiSEAD4Analyzer()
                    results['rag'] = llm_analyzer.analyze(document_text, case_id=f"{case_id}_rag", native_analysis=native_guidance)
                    # Capture token usage for cost calculation and save to cache
                    if llm_analyzer.get_last_usage():
                        st.session_state['rag_usage'] = llm_analyzer.get_last_usage()
                        save_llm_cache_metadata(case_id, "enhanced_native_rag", llm_analyzer.get_last_usage())
                    st.session_state['rag_from_cache'] = False
                    log_timing("RAG: COMPLETE")
                    status.update(label="Analysis complete!", state="complete", expanded=False)
                    # Rerun to display results
                    st.rerun()
        if 'rag' in results:
            # Get actual cost from usage data if available
            rag_usage = st.session_state.get('rag_usage')
            rag_from_cache = st.session_state.get('rag_from_cache', False)
            if rag_usage:
                rag_cost_display = f"${rag_usage['total_cost']:.4f}"
            elif rag_from_cache:
                rag_cost_display = "(cached)"
            else:
                rag_cost_display = "~$0.02"

            # Calculate precision against ground truth if available
            rag_relevant = [g.code for g in results['rag'].get_relevant_guidelines()]
            rag_set = set(rag_relevant)
            gt_guidelines = set(GROUND_TRUTH[selected_file]['guidelines']) if selected_file in GROUND_TRUTH else None
            if gt_guidelines and rag_set:
                rag_precision = len(gt_guidelines & rag_set) / len(rag_set)
                rag_precision_display = f"{rag_precision:.2%}"
            else:
                rag_precision_display = "N/A"

            col_metric1, col_metric2, col_metric3 = st.columns(3)
            with col_metric1:
                st.metric("Speed", "~23s")
            with col_metric2:
                st.metric("Cost", rag_cost_display)
            with col_metric3:
                st.metric("Precision", rag_precision_display)

            st.divider()
            st.success("Analysis complete")

            native_guidance = {
                'relevant_guidelines': [g.code for g in results['enhanced'].get_relevant_guidelines()] if 'enhanced' in results else [],
            }
            if native_guidance['relevant_guidelines']:
                st.caption(f"**Native Guidance Provided:** Guidelines: {', '.join(native_guidance['relevant_guidelines'])}")

            col1, col2 = st.columns([1, 2])

            with col1:
                st.markdown("**Overall Assessment**")
                result = results['rag']
                st.metric("Recommendation", result.overall_assessment.recommendation.value)
                st.metric("Confidence", f"{result.overall_assessment.confidence:.2%}")

                relevant = result.get_relevant_guidelines()
                st.metric("Guidelines Flagged", len(relevant))
                if relevant:
                    st.write("**Flagged:** " + ", ".join([g.code for g in relevant]))

            with col2:
                st.markdown("**Relevant Guidelines**")
                for g in results['rag'].get_relevant_guidelines():
                    with st.expander(f"**{g.code}. {g.name}** - Severity {g.severity.value if g.severity else 'N/A'} (Confidence: {g.confidence:.2%})"):
                        st.write(f"**Reasoning:** {g.reasoning}")
                        if g.disqualifiers:
                            st.write(f"**Disqualifiers ({len(g.disqualifiers)}):**")
                            for d in g.disqualifiers:
                                st.write(f"- {d.code}: {d.text[:100]}...")

# Comparison Tab - shows results for analyses that have been run
with tab_compare:
    log_timing("Rendering Comparison tab")
    st.subheader("Comparative Analysis")
    st.caption("Side-by-side comparison of all analysis approaches")

    # Check what results are available
    has_native = 'native' in results
    has_enhanced = 'enhanced' in results

    if not has_native and not has_enhanced:
        st.info("Run at least one analysis by clicking on the Basic Native or Enhanced Native tabs first.")
    else:
        st.divider()

        # Agreement check (only for available results)
        recommendations = {}
        if has_native:
            recommendations['Basic Native'] = results['native'].overall_assessment.recommendation.value
        if has_enhanced:
            recommendations['Enhanced Native'] = results['enhanced'].overall_assessment.recommendation.value

        if include_llm and 'llm' in results:
            recommendations['LLM'] = results['llm'].overall_assessment.recommendation.value
        if include_llm and 'rag' in results:
            recommendations['Enhanced LLM (RAG)'] = results['rag'].overall_assessment.recommendation.value

        all_agree = len(set(recommendations.values())) == 1

        if all_agree:
            st.success(f"**All {len(recommendations)} Approaches Agree:** {list(recommendations.values())[0]}")
        else:
            st.warning(f"**Disagreement Detected** — Manual review recommended")

        # Summary table
        st.markdown("### Summary Comparison")

        summary_data = []

        # Get ground truth for precision calculation
        gt_guidelines = set(GROUND_TRUTH[selected_file]['guidelines']) if selected_file in GROUND_TRUTH else None

        def calc_precision(predicted_set, gt_set):
            """Calculate precision: correct predictions / total predictions"""
            if not predicted_set or not gt_set:
                return None
            return len(gt_set & predicted_set) / len(predicted_set)

        # Basic Native
        native_relevant = [g.code for g in results['native'].get_relevant_guidelines()]
        native_set = set(native_relevant)
        native_precision = calc_precision(native_set, gt_guidelines)
        summary_data.append({
            "Approach": "1. Basic Native",
            "Method": "Keywords",
            "Guidelines": ", ".join(native_relevant),
            "Count": len(native_relevant),
            "Recommendation": results['native'].overall_assessment.recommendation.value,
            "Confidence": f"{results['native'].overall_assessment.confidence:.2%}",
            "Precision": "N/A" if native_precision is None else f"{native_precision:.2%}",
            "Speed": "~100ms",
            "Cost": "$0"
        })

        # Enhanced Native
        enhanced_relevant = [g.code for g in results['enhanced'].get_relevant_guidelines()]
        enhanced_set = set(enhanced_relevant)
        enhanced_precision = calc_precision(enhanced_set, gt_guidelines)
        summary_data.append({
            "Approach": "2. Enhanced Native",
            "Method": "ML (N-grams + TF-IDF + Embeddings)",
            "Guidelines": ", ".join(enhanced_relevant),
            "Count": len(enhanced_relevant),
            "Recommendation": results['enhanced'].overall_assessment.recommendation.value,
            "Confidence": f"{results['enhanced'].overall_assessment.confidence:.2%}",
            "Precision": "N/A" if enhanced_precision is None else f"{enhanced_precision:.2%}",
            "Speed": "~3s",
            "Cost": "$0"
        })

        if include_llm and 'llm' in results:
            llm_relevant = [g.code for g in results['llm'].get_relevant_guidelines()]
            llm_set = set(llm_relevant)
            llm_precision = calc_precision(llm_set, gt_guidelines)
            # Get actual cost from usage data (or show cached/estimated)
            llm_usage = st.session_state.get('llm_usage')
            llm_from_cache = st.session_state.get('llm_from_cache', False)
            if llm_usage:
                llm_cost = f"${llm_usage['total_cost']:.4f}"
            elif llm_from_cache:
                llm_cost = "(cached)"
            else:
                llm_cost = "~$0.02"
            summary_data.append({
                "Approach": "3. LLM",
                "Method": "Gemini 2.0 Flash",
                "Guidelines": ", ".join(llm_relevant),
                "Count": len(llm_relevant),
                "Recommendation": results['llm'].overall_assessment.recommendation.value,
                "Confidence": f"{results['llm'].overall_assessment.confidence:.2%}",
                "Precision": "N/A" if llm_precision is None else f"{llm_precision:.2%}",
                "Speed": "~20s",
                "Cost": llm_cost
            })

        if include_llm and 'rag' in results:
            rag_relevant = [g.code for g in results['rag'].get_relevant_guidelines()]
            rag_set = set(rag_relevant)
            rag_precision = calc_precision(rag_set, gt_guidelines)
            # Get actual cost from usage data (or show cached/estimated)
            rag_usage = st.session_state.get('rag_usage')
            rag_from_cache = st.session_state.get('rag_from_cache', False)
            if rag_usage:
                rag_cost = f"${rag_usage['total_cost']:.4f}"
            elif rag_from_cache:
                rag_cost = "(cached)"
            else:
                rag_cost = "~$0.02"
            summary_data.append({
                "Approach": "4. Enhanced LLM (RAG)",
                "Method": "Enhanced guides Gemini",
                "Guidelines": ", ".join(rag_relevant),
                "Count": len(rag_relevant),
                "Recommendation": results['rag'].overall_assessment.recommendation.value,
                "Confidence": f"{results['rag'].overall_assessment.confidence:.2%}",
                "Precision": "N/A" if rag_precision is None else f"{rag_precision:.2%}",
                "Speed": "~23s",
                "Cost": rag_cost
            })

        st.dataframe(summary_data, width='stretch')

        # Ground truth comparison
        if selected_file in GROUND_TRUTH:
            st.divider()
            st.markdown("### Ground Truth Validation")
            gt_guidelines = set(GROUND_TRUTH[selected_file]['guidelines'])

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                native_set = set(native_relevant)
                precision = len(gt_guidelines & native_set) / len(native_set) if native_set else 0
                recall = len(gt_guidelines & native_set) / len(gt_guidelines) if gt_guidelines else 0
                st.metric("Basic Native Precision", f"{precision:.0%}")
                st.metric("Basic Native Recall", f"{recall:.0%}")
                if native_set != gt_guidelines:
                    false_pos = native_set - gt_guidelines
                    if false_pos:
                        st.caption(f"False Positives: {', '.join(false_pos)}")

            with col2:
                enhanced_set = set(enhanced_relevant)
                precision = len(gt_guidelines & enhanced_set) / len(enhanced_set) if enhanced_set else 0
                recall = len(gt_guidelines & enhanced_set) / len(gt_guidelines) if gt_guidelines else 0
                st.metric("Enhanced Native Precision", f"{precision:.0%}")
                st.metric("Enhanced Native Recall", f"{recall:.0%}")
                if enhanced_set != gt_guidelines:
                    false_pos = enhanced_set - gt_guidelines
                    if false_pos:
                        st.caption(f"False Positives: {', '.join(false_pos)}")

            if include_llm and 'llm' in results:
                with col3:
                    llm_set = set(llm_relevant)
                    precision = len(gt_guidelines & llm_set) / len(llm_set) if llm_set else 0
                    recall = len(gt_guidelines & llm_set) / len(gt_guidelines) if gt_guidelines else 0
                    st.metric("LLM Precision", f"{precision:.0%}")
                    st.metric("LLM Recall", f"{recall:.0%}")
                    if llm_set != gt_guidelines:
                        false_pos = llm_set - gt_guidelines
                        if false_pos:
                            st.caption(f"False Positives: {', '.join(false_pos)}")

            if include_llm and 'rag' in results:
                with col4:
                    rag_set = set(rag_relevant)
                    precision = len(gt_guidelines & rag_set) / len(rag_set) if rag_set else 0
                    recall = len(gt_guidelines & rag_set) / len(gt_guidelines) if gt_guidelines else 0
                    st.metric("Enhanced LLM (RAG) Precision", f"{precision:.0%}")
                    st.metric("Enhanced LLM (RAG) Recall", f"{recall:.0%}")
                    if rag_set != gt_guidelines:
                        false_pos = rag_set - gt_guidelines
                        if false_pos:
                            st.caption(f"False Positives: {', '.join(false_pos)}")

        # Guideline-by-guideline comparison
        st.divider()
        st.markdown("### Guideline-by-Guideline Comparison")

        all_codes = set()
        all_codes.update(native_relevant)
        all_codes.update(enhanced_relevant)
        if include_llm and 'llm' in results:
            all_codes.update(llm_relevant)
        if include_llm and 'rag' in results:
            all_codes.update(rag_relevant)

        for code in sorted(all_codes):
            st.markdown(f"### Guideline {code}")

            cols = st.columns(len(results))

            for i, (name, result) in enumerate(results.items()):
                with cols[i]:
                    guideline = next((g for g in result.guidelines if g.code == code), None)
                    if guideline and guideline.relevant:
                        st.success(f"**{name.upper()}**")
                        st.caption(f"Severity: {guideline.severity.value if guideline.severity else 'N/A'}")
                        st.caption(f"Confidence: {guideline.confidence:.2%}")
                    else:
                        st.error(f"**{name.upper()}**")
                        st.caption("Not flagged")

# Dashboard Tab
with tab_dashboard:
    log_timing("Rendering Dashboard tab")
    st.subheader("DOHA Case Statistics Dashboard")
    st.caption("Historical case data from the DOHA database")

    # Load case statistics
    df = load_case_statistics()

    if df is not None:
        # Overview metrics
        total_cases = len(df)
        granted = len(df[df['outcome'] == 'GRANTED'])
        denied = len(df[df['outcome'] == 'DENIED'])
        other = total_cases - granted - denied

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Cases", f"{total_cases:,}")
        with col2:
            st.metric("Granted", f"{granted:,}", f"{granted/total_cases:.1%}")
        with col3:
            st.metric("Denied", f"{denied:,}", f"{denied/total_cases:.1%}")
        with col4:
            st.metric("Other", f"{other:,}", f"{other/total_cases:.1%}")

        st.divider()

        # Charts side by side
        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            st.markdown("#### Outcome Distribution")
            outcome_counts = df['outcome'].value_counts()
            st.bar_chart(outcome_counts)

        with chart_col2:
            st.markdown("#### Cases by Guideline")
            # Build stacked bar data with outcome breakdown per guideline
            import altair as alt

            stacked_data = []
            for guidelines, outcome in zip(df['guidelines'], df['outcome']):
                if guidelines is not None:
                    # Categorize outcome
                    if outcome == 'GRANTED':
                        cat = 'Granted'
                    elif outcome == 'DENIED':
                        cat = 'Denied'
                    else:
                        cat = 'Other'
                    for g in guidelines:
                        stacked_data.append({'Guideline': g, 'Outcome': cat})

            if stacked_data:
                stacked_df = pd.DataFrame(stacked_data)
                # Aggregate counts
                agg_df = stacked_df.groupby(['Guideline', 'Outcome']).size().reset_index(name='Count')

                # Calculate percentages and stack positions
                totals = agg_df.groupby('Guideline')['Count'].transform('sum')
                agg_df['Percentage'] = (agg_df['Count'] / totals * 100).round(0).astype(int)
                # Only show label if segment is >= 10% (enough room for text)
                agg_df['Label'] = agg_df['Percentage'].apply(lambda x: f'{x}%' if x >= 10 else '')

                # Calculate y positions for text (center of each segment)
                # Sort by guideline and outcome to match stacking order
                agg_df = agg_df.sort_values(['Guideline', 'Outcome'])
                agg_df['y_end'] = agg_df.groupby('Guideline')['Count'].cumsum()
                agg_df['y_start'] = agg_df['y_end'] - agg_df['Count']
                agg_df['y_mid'] = (agg_df['y_start'] + agg_df['y_end']) / 2

                # Create percentage label for display
                agg_df['Pct_Label'] = agg_df['Percentage'].apply(lambda x: f'{x}%')

                # Common tooltip for both layers
                tooltip_fields = [
                    alt.Tooltip('Guideline:N', title='Guideline'),
                    alt.Tooltip('Outcome:N', title='Outcome'),
                    alt.Tooltip('Count:Q', title='Cases', format=','),
                    alt.Tooltip('Pct_Label:N', title='Percentage')
                ]

                # Bars
                bars = alt.Chart(agg_df).mark_bar().encode(
                    x=alt.X('Guideline:N', sort=list('ABCDEFGHIJKLM'), title='Guideline'),
                    y=alt.Y('Count:Q', title='Cases'),
                    color=alt.Color('Outcome:N',
                        scale=alt.Scale(
                            domain=['Granted', 'Denied', 'Other'],
                            range=['#1f77b4', '#aec7e8', '#d4a82e']  # Blue, Light Blue, Gold
                        ),
                        legend=alt.Legend(title='Outcome')
                    ),
                    order=alt.Order('Outcome:N', sort='ascending'),
                    tooltip=tooltip_fields
                )

                # Text labels centered in each segment
                text = alt.Chart(agg_df).mark_text(
                    align='center',
                    baseline='middle',
                    color='white',
                    fontSize=10,
                    fontWeight='bold'
                ).encode(
                    x=alt.X('Guideline:N', sort=list('ABCDEFGHIJKLM')),
                    y=alt.Y('y_mid:Q'),
                    text='Label:N',
                    tooltip=tooltip_fields
                )

                chart = (bars + text).properties(height=400)

                st.altair_chart(chart, width='stretch')

        st.divider()

        # Cross-tabulation: Guidelines vs Outcomes
        st.markdown("#### Approval/Denial Rates by Guideline")

        # Get all unique guidelines
        all_guidelines = set()
        for guidelines in df['guidelines']:
            if guidelines is not None:
                all_guidelines.update(guidelines)

        # Build cross-tab data
        crosstab_data = []
        for guideline in sorted(all_guidelines):
            # Filter cases that have this guideline
            mask = df['guidelines'].apply(lambda x: guideline in x if x is not None else False)
            guideline_cases = df[mask]
            g_total = len(guideline_cases)
            g_granted = len(guideline_cases[guideline_cases['outcome'] == 'GRANTED'])
            g_denied = len(guideline_cases[guideline_cases['outcome'] == 'DENIED'])

            crosstab_data.append({
                'Guideline': guideline,
                'Total Cases': g_total,
                'Granted': g_granted,
                'Denied': g_denied,
                'Approval Rate': f"{g_granted/g_total:.1%}" if g_total > 0 else "N/A",
                'Denial Rate': f"{g_denied/g_total:.1%}" if g_total > 0 else "N/A"
            })

        crosstab_df = pd.DataFrame(crosstab_data)
        st.dataframe(crosstab_df, hide_index=True)

    else:
        st.warning("Case statistics not available. Parquet file not found.")

log_timing("<<< MAIN ANALYSIS BLOCK END")

# Footer
st.sidebar.divider()
st.sidebar.caption("SEAD-4 Analyzer Demo v1.0")
st.sidebar.caption("Built with Streamlit")

log_timing("=== SCRIPT END ===")
