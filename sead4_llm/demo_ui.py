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

import streamlit as st
from pathlib import Path
import fitz  # PyMuPDF
import json
from datetime import datetime
import base64

from analyzers.native_analyzer import NativeSEAD4Analyzer
from analyzers.gemini_analyzer import GeminiSEAD4Analyzer
from schemas.models import SEAD4AnalysisResult
import os

# Lazy import for heavy ML dependencies with background loading
# This makes the app start instantly, then loads models in background
@st.cache_resource
def get_enhanced_analyzer():
    """
    Lazy import and cache of EnhancedNativeSEAD4Analyzer.
    First call downloads ML models (~80MB), subsequent calls use cache.
    """
    from analyzers.enhanced_native_analyzer import EnhancedNativeSEAD4Analyzer
    return EnhancedNativeSEAD4Analyzer


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


def display_pdf(file_path: Path):
    """Display PDF in an iframe using base64 encoding"""
    with open(file_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')

    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)


def load_cached_llm_result(case_id: str, suffix: str) -> SEAD4AnalysisResult | None:
    """
    Load cached LLM result from llm_cache/llm_response_*.txt file if it exists

    Args:
        case_id: Case ID (e.g., "PSH-25-0214")
        suffix: Suffix like "llm", "native_rag", "enhanced_native_rag"

    Returns:
        SEAD4AnalysisResult if cached file exists and can be parsed, None otherwise
    """
    cache_file = Path("llm_cache") / f"llm_response_{case_id}_{suffix}.txt"

    if not cache_file.exists():
        return None

    try:
        # Read cached response
        response_text = cache_file.read_text()

        # Parse using Gemini analyzer's parser (pass dummy key for cache parsing)
        import os
        original_key = os.getenv("GEMINI_API_KEY")
        os.environ["GEMINI_API_KEY"] = "dummy_key_for_cache_parsing"

        try:
            analyzer = GeminiSEAD4Analyzer()
            result = analyzer._parse_response(response_text, f"{case_id}_{suffix}", "")
        finally:
            # Restore original key
            if original_key:
                os.environ["GEMINI_API_KEY"] = original_key
            else:
                os.environ.pop("GEMINI_API_KEY", None)

        st.caption(f"Loaded from cache: {cache_file.name}")
        return result
    except Exception as e:
        st.warning(f"Failed to load cache {cache_file.name}: {e}")
        return None


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

# Run analysis button
analyze_button = st.sidebar.button("Run Comparison Analysis", type="primary")

# Initialize analysis state in session
if 'analysis_run' not in st.session_state:
    st.session_state.analysis_run = False

# Trigger analysis
if analyze_button:
    st.session_state.analysis_run = True

# Main area
if st.session_state.analysis_run:
    # Load PDF
    with st.spinner(f"Loading {selected_file}..."):
        doc = fitz.open(selected_path)
        document_text = ""
        for page in doc:
            document_text += page.get_text()
        doc.close()

        st.success(f"Loaded {len(document_text):,} characters from PDF")

    # Create tabs for each approach
    if include_llm:
        tab_pdf, tab1, tab2, tab3, tab4, tab_compare = st.tabs([
            "Document View",
            "Basic Native",
            "Enhanced Native",
            "LLM (Independent)",
            "Enhanced LLM (RAG)",
            "Comparison"
        ])
    else:
        tab_pdf, tab1, tab2, tab_compare = st.tabs([
            "Document View",
            "Basic Native",
            "Enhanced Native",
            "Comparison"
        ])

    # Run analyses
    results = {}

    # Document View Tab
    with tab_pdf:
        st.subheader("Case Document & Analyst Assessment")
        st.caption(f"Viewing: {selected_file}")

        # Create two columns: PDF on left, analyst input on right
        col_pdf, col_analyst = st.columns([2, 1])

        with col_pdf:
            st.caption("Review the case document below")
            display_pdf(selected_path)

        with col_analyst:
            st.markdown("**Analyst Assessment**")
            st.caption("Record your independent analysis of this case")

            # Initialize session state for analyst input if not exists
            if 'analyst_guidelines' not in st.session_state:
                st.session_state.analyst_guidelines = []
            if 'analyst_assessments' not in st.session_state:
                st.session_state.analyst_assessments = {}

            # Guideline multi-select
            selected_guidelines = st.multiselect(
                "Select applicable SEAD-4 Guidelines:",
                options=list(SEAD4_GUIDELINES.keys()),
                format_func=lambda x: f"{x}: {SEAD4_GUIDELINES[x]}",
                default=st.session_state.analyst_guidelines,
                help="Select all guidelines that apply to this case"
            )
            st.session_state.analyst_guidelines = selected_guidelines

            st.divider()

            # For each selected guideline, get severity and justification
            if selected_guidelines:
                st.markdown("**Guideline Details**")

                for guideline in selected_guidelines:
                    with st.expander(f"**{guideline}: {SEAD4_GUIDELINES[guideline]}**", expanded=True):
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

    # 1. Basic Native
    with tab1:
        st.subheader("Basic Native")
        st.caption("Keyword matching and pattern recognition")

        col_metric1, col_metric2, col_metric3 = st.columns(3)
        with col_metric1:
            st.metric("Speed", "~100ms")
        with col_metric2:
            st.metric("Cost", "$0")
        with col_metric3:
            st.metric("Precision", "~50%")

        st.divider()

        with st.spinner("Running basic native analysis..."):
            native_analyzer = NativeSEAD4Analyzer()
            results['native'] = native_analyzer.analyze(document_text, case_id=f"{case_id}_native")

        st.success("Analysis complete")

        # Display results
        col1, col2 = st.columns([1, 2])

        with col1:
            st.markdown("**Overall Assessment**")
            result = results['native']
            st.metric("Recommendation", result.overall_assessment.recommendation.value)
            st.metric("Confidence", f"{result.overall_assessment.confidence:.1%}")

            relevant = result.get_relevant_guidelines()
            st.metric("Guidelines Flagged", len(relevant))
            if relevant:
                st.write("**Flagged:** " + ", ".join([g.code for g in relevant]))

        with col2:
            st.markdown("**Relevant Guidelines**")
            for g in results['native'].get_relevant_guidelines():
                with st.expander(f"**{g.code}. {g.name}** - Severity {g.severity.value if g.severity else 'N/A'} (Confidence: {g.confidence:.1%})"):
                    st.write(f"**Reasoning:** {g.reasoning}")
                    if g.disqualifiers:
                        st.write(f"**Disqualifiers ({len(g.disqualifiers)}):**")
                        for d in g.disqualifiers:
                            st.write(f"- {d.code}: {d.text[:100]}...")

    # 2. Enhanced Native
    with tab2:
        st.subheader("Enhanced Native")
        st.caption("N-grams + TF-IDF + Semantic Embeddings + Contextual Analysis")

        col_metric1, col_metric2, col_metric3 = st.columns(3)
        with col_metric1:
            st.metric("Speed", "~3s")
        with col_metric2:
            st.metric("Cost", "$0")
        with col_metric3:
            st.metric("Precision", "~83%")

        st.divider()

        with st.spinner("Running enhanced native analysis (loading ML models)..."):
            EnhancedNativeSEAD4Analyzer = get_enhanced_analyzer()
            enhanced_analyzer = EnhancedNativeSEAD4Analyzer(use_embeddings=True)
            results['enhanced'] = enhanced_analyzer.analyze(document_text, case_id=f"{case_id}_enhanced")

        st.success("Analysis complete")

        # Display results
        col1, col2 = st.columns([1, 2])

        with col1:
            st.markdown("**Overall Assessment**")
            result = results['enhanced']
            st.metric("Recommendation", result.overall_assessment.recommendation.value)
            st.metric("Confidence", f"{result.overall_assessment.confidence:.1%}")

            relevant = result.get_relevant_guidelines()
            st.metric("Guidelines Flagged", len(relevant))
            if relevant:
                st.write("**Flagged:** " + ", ".join([g.code for g in relevant]))

        with col2:
            st.markdown("**Relevant Guidelines**")
            for g in results['enhanced'].get_relevant_guidelines():
                with st.expander(f"**{g.code}. {g.name}** - Severity {g.severity.value if g.severity else 'N/A'} (Confidence: {g.confidence:.1%})"):
                    st.write(f"**Reasoning:** {g.reasoning}")
                    if g.disqualifiers:
                        st.write(f"**Disqualifiers ({len(g.disqualifiers)}):**")
                        for d in g.disqualifiers:
                            st.write(f"- {d.code}: {d.text[:100]}...")

    # 3. LLM (if enabled)
    if include_llm:
        with tab3:
            st.subheader("LLM Analysis (Independent)")
            st.caption("Gemini 2.0 Flash analyzing independently - no pre-filtering from native analyzer")

            col_metric1, col_metric2, col_metric3 = st.columns(3)
            with col_metric1:
                st.metric("Speed", "~20s")
            with col_metric2:
                st.metric("Cost", "~$0.02")
            with col_metric3:
                st.metric("Precision", "~90%")

            st.divider()

            # Try loading from cache first
            cached_result = load_cached_llm_result(case_id, "llm")

            if cached_result:
                results['llm'] = cached_result
                st.success("Loaded from cache (no API call needed)")
            else:
                # Check if API key is available
                if not api_key:
                    st.error("GEMINI_API_KEY not configured")
                    st.info("""
                    **To use LLM analysis:**
                    - **Streamlit Cloud:** Add `GEMINI_API_KEY = "your-key"` in App Settings → Secrets
                    - **Local:** Run `export GEMINI_API_KEY=your_key` in terminal
                    """)
                else:
                    with st.spinner("Running LLM analysis (this may take 20-30 seconds)..."):
                        try:
                            llm_analyzer = GeminiSEAD4Analyzer()
                            results['llm'] = llm_analyzer.analyze(document_text, case_id=f"{case_id}_llm")
                            st.success("Analysis complete")
                        except Exception as e:
                            st.error(f"LLM analysis failed: {e}")
                            st.info("Check that your GEMINI_API_KEY is valid")

            # Display results (if available)
            if 'llm' in results:
                col1, col2 = st.columns([1, 2])

                with col1:
                    st.markdown("**Overall Assessment**")
                    result = results['llm']
                    st.metric("Recommendation", result.overall_assessment.recommendation.value)
                    st.metric("Confidence", f"{result.overall_assessment.confidence:.1%}")

                    relevant = result.get_relevant_guidelines()
                    st.metric("Guidelines Flagged", len(relevant))
                    if relevant:
                        st.write("**Flagged:** " + ", ".join([g.code for g in relevant]))

                with col2:
                    st.markdown("**Relevant Guidelines**")
                    for g in results['llm'].get_relevant_guidelines():
                        with st.expander(f"**{g.code}. {g.name}** - Severity {g.severity.value if g.severity else 'N/A'} (Confidence: {g.confidence:.1%})"):
                            st.write(f"**Reasoning:** {g.reasoning}")
                            if g.disqualifiers:
                                st.write(f"**Disqualifiers ({len(g.disqualifiers)}):**")
                                for d in g.disqualifiers:
                                    st.write(f"- {d.code}: {d.text[:100]}...")

        # 4. Enhanced LLM (RAG)
        with tab4:
            st.subheader("Enhanced LLM (RAG)")
            st.caption("Enhanced native guides LLM for focused analysis")

            col_metric1, col_metric2, col_metric3 = st.columns(3)
            with col_metric1:
                st.metric("Speed", "~23s")
            with col_metric2:
                st.metric("Cost", "~$0.02")
            with col_metric3:
                st.metric("Precision", "~95%")

            st.divider()

            # Try loading from cache first
            cached_result = load_cached_llm_result(case_id, "enhanced_native_rag")

            # Build guidance from enhanced native (needed for display even if cached)
            native_guidance = {
                'relevant_guidelines': [g.code for g in results['enhanced'].get_relevant_guidelines()],
                'severe_concerns': [g.code for g in results['enhanced'].get_relevant_guidelines()
                                   if g.severity and g.severity.value in ['C', 'D']],
                'recommendation': results['enhanced'].overall_assessment.recommendation.value,
                'confidence': results['enhanced'].overall_assessment.confidence,
                'key_concerns': results['enhanced'].overall_assessment.key_concerns
            }

            if cached_result:
                results['rag'] = cached_result
                st.success("Loaded from cache (no API call needed)")
            else:
                # Check if API key is available
                if not api_key:
                    st.error("GEMINI_API_KEY not configured")
                    st.info("""
                    **To use RAG analysis:**
                    - **Streamlit Cloud:** Add `GEMINI_API_KEY = "your-key"` in App Settings → Secrets
                    - **Local:** Run `export GEMINI_API_KEY=your_key` in terminal
                    """)
                else:
                    with st.spinner("Running LLM with enhanced native guidance..."):
                        try:
                            llm_analyzer = GeminiSEAD4Analyzer()
                            results['rag'] = llm_analyzer.analyze(
                                document_text,
                                case_id=f"{case_id}_rag",
                                native_analysis=native_guidance
                            )
                            st.success("Analysis complete")
                        except Exception as e:
                            st.error(f"RAG analysis failed: {e}")
                            st.info("Check that your GEMINI_API_KEY is valid")

            # Display results (if available)
            if 'rag' in results:
                col1, col2 = st.columns([1, 2])

                with col1:
                    st.markdown("**Overall Assessment**")
                    result = results['rag']
                    st.metric("Recommendation", result.overall_assessment.recommendation.value)
                    st.metric("Confidence", f"{result.overall_assessment.confidence:.1%}")

                    relevant = result.get_relevant_guidelines()
                    st.metric("Guidelines Flagged", len(relevant))
                    if relevant:
                        st.write("**Flagged:** " + ", ".join([g.code for g in relevant]))

                    # Show what enhanced native suggested
                    st.divider()
                    st.caption("**Native Guidance Provided:**")
                    st.caption(f"Guidelines: {', '.join(native_guidance['relevant_guidelines'])}")

                with col2:
                    st.markdown("**Relevant Guidelines**")
                    for g in results['rag'].get_relevant_guidelines():
                        with st.expander(f"**{g.code}. {g.name}** - Severity {g.severity.value if g.severity else 'N/A'} (Confidence: {g.confidence:.1%})"):
                            st.write(f"**Reasoning:** {g.reasoning}")
                            if g.disqualifiers:
                                st.write(f"**Disqualifiers ({len(g.disqualifiers)}):**")
                                for d in g.disqualifiers:
                                    st.write(f"- {d.code}: {d.text[:100]}...")

    # Comparison Tab
    with tab_compare:
        st.subheader("Comparative Analysis")
        st.caption("Side-by-side comparison of all analysis approaches")
        st.divider()

        # Agreement check
        recommendations = {
            'Basic Native': results['native'].overall_assessment.recommendation.value,
            'Enhanced Native': results['enhanced'].overall_assessment.recommendation.value
        }

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

        # Basic Native
        native_relevant = [g.code for g in results['native'].get_relevant_guidelines()]
        summary_data.append({
            "Approach": "1. Basic Native",
            "Method": "Keywords",
            "Guidelines": ", ".join(native_relevant),
            "Count": len(native_relevant),
            "Recommendation": results['native'].overall_assessment.recommendation.value,
            "Confidence": f"{results['native'].overall_assessment.confidence:.1%}",
            "Speed": "~100ms",
            "Cost": "$0"
        })

        # Enhanced Native
        enhanced_relevant = [g.code for g in results['enhanced'].get_relevant_guidelines()]
        summary_data.append({
            "Approach": "2. Enhanced Native",
            "Method": "ML (N-grams + TF-IDF + Embeddings)",
            "Guidelines": ", ".join(enhanced_relevant),
            "Count": len(enhanced_relevant),
            "Recommendation": results['enhanced'].overall_assessment.recommendation.value,
            "Confidence": f"{results['enhanced'].overall_assessment.confidence:.1%}",
            "Speed": "~3s",
            "Cost": "$0"
        })

        if include_llm and 'llm' in results:
            llm_relevant = [g.code for g in results['llm'].get_relevant_guidelines()]
            summary_data.append({
                "Approach": "3. LLM",
                "Method": "Gemini 2.0 Flash",
                "Guidelines": ", ".join(llm_relevant),
                "Count": len(llm_relevant),
                "Recommendation": results['llm'].overall_assessment.recommendation.value,
                "Confidence": f"{results['llm'].overall_assessment.confidence:.1%}",
                "Speed": "~20s",
                "Cost": "~$0.02"
            })

        if include_llm and 'rag' in results:
            rag_relevant = [g.code for g in results['rag'].get_relevant_guidelines()]
            summary_data.append({
                "Approach": "4. Enhanced LLM (RAG)",
                "Method": "Enhanced guides Gemini",
                "Guidelines": ", ".join(rag_relevant),
                "Count": len(rag_relevant),
                "Recommendation": results['rag'].overall_assessment.recommendation.value,
                "Confidence": f"{results['rag'].overall_assessment.confidence:.1%}",
                "Speed": "~23s",
                "Cost": "~$0.02"
            })

        st.dataframe(summary_data, use_container_width=True)

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
                        st.caption(f"Confidence: {guideline.confidence:.1%}")
                    else:
                        st.error(f"**{name.upper()}**")
                        st.caption("Not flagged")

else:
    # Welcome screen
    st.info("Select a test case from the sidebar and click **Run Comparison Analysis** to begin")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        ### Approach Overview

        This tool compares **4 different analysis methods** for SEAD-4 security clearance evaluation:

        **1. Basic Native**
        - Keyword matching and pattern recognition
        - Fast (~100ms), 0 cost, ~50% precision
        - Fully offline, no ML dependencies

        **2. Enhanced Native**
        - N-gram phrase matching + TF-IDF weighting
        - Semantic embeddings (sentence transformers)
        - Contextual co-occurrence analysis
        - Moderate speed (~3s), 0 cost, ~83% precision

        **3. LLM (Independent)**
        - Deep semantic understanding (Gemini 2.0 Flash)
        - Independent analysis without pre-filtering from native analyzer
        - Slower (~20s), ~$0.02 cost, ~90% precision

        **4. Enhanced LLM (RAG)**
        - Enhanced native identifies key guidelines
        - LLM performs targeted deep analysis
        - Best of both: precision + reasoning
        - Speed (~23s), ~$0.02 cost, ~95% precision
        """)

    with col2:
        st.markdown("""
        ### Available Test Cases

        Three cases with verified ground truth:

        **PSH-25-0137**
        - Alcohol + PTSD case
        - Expected: Guidelines G, I

        **PSH-25-0214**
        - DUI + Lack of Candor
        - Expected: Guidelines E, G

        **PSH-25-0181**
        - Alcohol case
        - Expected: Guideline G

        ### Metrics

        Each approach is evaluated on:
        - **Precision:** Accuracy of flagged guidelines
        - **Recall:** Coverage of relevant guidelines
        - **Speed:** Analysis completion time
        - **Cost:** API usage charges
        """)

# Footer
st.sidebar.divider()
st.sidebar.caption("SEAD-4 Analyzer Demo v1.0")
st.sidebar.caption("Built with Streamlit")

# Background loading: Pre-load ML models after UI renders
# This ensures models are ready when user clicks "Run Comparison Analysis"
# First load takes ~3-5 seconds, cached for all subsequent uses
try:
    get_enhanced_analyzer()
except Exception:
    # Silent fail - models will load on first use instead
    pass
