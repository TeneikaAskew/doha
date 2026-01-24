#!/usr/bin/env python3
"""
SEAD-4 Adjudicative Guidelines Analyzer

LLM-powered analysis of security clearance reports with explainable,
citation-backed assessments and optional precedent matching.

Usage:
    python analyze.py --input report.pdf
    python analyze.py --input report.txt --output result.json
    python analyze.py --input report.pdf --use-rag --index ./doha_index
    python analyze.py --input-dir ./reports --batch
"""
import argparse
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional
from loguru import logger

# PDF parsing
try:
    import fitz  # PyMuPDF
    HAS_PDF = True
except ImportError:
    HAS_PDF = False


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from a PDF file"""
    if not HAS_PDF:
        raise ImportError("PyMuPDF required for PDF support. Install with: pip install PyMuPDF")
        
    doc = fitz.open(pdf_path)
    text_parts = []
    
    for page in doc:
        text_parts.append(page.get_text())
        
    doc.close()
    return "\n".join(text_parts)


def load_document(path: Path) -> str:
    """Load document text from file"""
    path = Path(path)
    
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")
        
    if path.suffix.lower() == '.pdf':
        return extract_text_from_pdf(path)
    else:
        # Assume text file
        return path.read_text(encoding='utf-8')


def analyze_single(
    input_path: str,
    output_path: Optional[str] = None,
    report_type: Optional[str] = None,
    use_rag: bool = False,
    index_path: Optional[str] = None,
    quick: bool = False,
    verbose: bool = False,
    provider: str = "gemini",
    compare_mode: bool = False,
    use_native_rag: bool = False,
    use_enhanced: bool = False
):
    """Analyze a single document"""
    from schemas.models import SEAD4AnalysisResult, ComparisonAnalysisResult

    # Load document
    input_path = Path(input_path)
    logger.info(f"Loading document: {input_path}")
    document_text = load_document(input_path)
    logger.info(f"Document length: {len(document_text)} characters")

    # Get precedents if RAG enabled
    precedents = None
    if use_rag and index_path:
        from rag.retriever import PrecedentRetriever

        logger.info(f"Loading precedent index from: {index_path}")
        retriever = PrecedentRetriever(index_path=Path(index_path))
        retriever.load()

        logger.info("Retrieving similar precedents...")
        precedents = retriever.retrieve(document_text, num_precedents=5)
        logger.info(f"Found {len(precedents)} relevant precedents")

    case_id = input_path.stem

    # Run native RAG mode if requested (native guides LLM)
    if use_native_rag:
        if use_enhanced:
            from analyzers.enhanced_native_analyzer import EnhancedNativeSEAD4Analyzer
            logger.info("Running ENHANCED native analysis to guide LLM...")
            native_analyzer = EnhancedNativeSEAD4Analyzer(use_embeddings=True)
        else:
            from analyzers.native_analyzer import NativeSEAD4Analyzer
            logger.info("Running native analysis to guide LLM...")
            native_analyzer = NativeSEAD4Analyzer()
        native_result = native_analyzer.analyze(
            document_text=document_text,
            case_id=f"{case_id}_native_rag",
            report_type=report_type,
            quick_mode=quick,
            precedents=precedents
        )

        # Extract guidance from native analysis
        native_guidance = {
            'relevant_guidelines': [g.code for g in native_result.get_relevant_guidelines()],
            'severe_concerns': [g.code for g in native_result.get_severe_concerns()],
            'recommendation': native_result.overall_assessment.recommendation.value,
            'confidence': native_result.overall_assessment.confidence,
            'key_concerns': native_result.overall_assessment.key_concerns
        }

        logger.info(f"Native identified guidelines: {native_guidance['relevant_guidelines']}")
        logger.debug(f"Native guidance: {native_guidance}")

        # Run LLM with native guidance
        logger.info(f"Running LLM ({provider}) with native guidance...")
        if provider == "gemini":
            from analyzers.gemini_analyzer import GeminiSEAD4Analyzer
            analyzer = GeminiSEAD4Analyzer()
        else:
            from analyzers.claude_analyzer import SEAD4Analyzer
            analyzer = SEAD4Analyzer()

        result = analyzer.analyze(
            document_text=document_text,
            case_id=case_id,
            report_type=report_type,
            quick_mode=quick,
            precedents=precedents,
            native_analysis=native_guidance
        )

    # Run comparison mode if requested (shows all 4 approaches)
    elif compare_mode:
        logger.info("COMPARISON MODE: Running all FOUR analysis approaches...")

        # 1. Basic Native Analysis (always run for comparison)
        from analyzers.native_analyzer import NativeSEAD4Analyzer
        logger.info("1/4: Running basic native (keyword-only) analysis...")
        native_analyzer = NativeSEAD4Analyzer()
        native_result = native_analyzer.analyze(
            document_text=document_text,
            case_id=f"{case_id}_native",
            report_type=report_type,
            quick_mode=quick,
            precedents=precedents
        )

        # 2. Enhanced Native Analysis (always run in comparison mode)
        from analyzers.enhanced_native_analyzer import EnhancedNativeSEAD4Analyzer
        logger.info("2/4: Running ENHANCED native (N-grams + TF-IDF + Embeddings) analysis...")
        enhanced_analyzer = EnhancedNativeSEAD4Analyzer(use_embeddings=True)
        enhanced_native_result = enhanced_analyzer.analyze(
            document_text=document_text,
            case_id=f"{case_id}_enhanced_native",
            report_type=report_type,
            quick_mode=quick,
            precedents=precedents
        )

        # 3. LLM Analysis (no guidance)
        logger.info(f"3/4: Running LLM ({provider}) analysis (no native guidance)...")
        if provider == "gemini":
            from analyzers.gemini_analyzer import GeminiSEAD4Analyzer
            llm_analyzer = GeminiSEAD4Analyzer()
        else:
            from analyzers.claude_analyzer import SEAD4Analyzer
            llm_analyzer = SEAD4Analyzer()

        llm_result = llm_analyzer.analyze(
            document_text=document_text,
            case_id=f"{case_id}_llm",
            report_type=report_type,
            quick_mode=quick,
            precedents=precedents
        )

        # 4. Enhanced Native→LLM RAG (enhanced guides LLM for best accuracy)
        logger.info(f"4/4: Running LLM ({provider}) with enhanced native guidance (RAG)...")

        # Always use enhanced native result for guidance in comparison mode
        native_guidance = {
            'relevant_guidelines': [g.code for g in enhanced_native_result.get_relevant_guidelines()],
            'severe_concerns': [g.code for g in enhanced_native_result.get_severe_concerns()],
            'recommendation': enhanced_native_result.overall_assessment.recommendation.value,
            'confidence': enhanced_native_result.overall_assessment.confidence,
            'key_concerns': enhanced_native_result.overall_assessment.key_concerns
        }
        logger.debug(f"Native guidance from enhanced native: {native_guidance}")

        native_rag_result = llm_analyzer.analyze(
            document_text=document_text,
            case_id=f"{case_id}_enhanced_native_rag",
            report_type=report_type,
            quick_mode=quick,
            precedents=precedents,
            native_analysis=native_guidance
        )

        result = ComparisonAnalysisResult(
            case_id=case_id,
            analysis_timestamp=datetime.now().isoformat(),
            native_result=native_result,
            enhanced_native_result=enhanced_native_result,
            llm_result=llm_result,
            native_rag_result=native_rag_result
        )
    else:
        # Single analysis
        if provider == "gemini":
            from analyzers.gemini_analyzer import GeminiSEAD4Analyzer
            analyzer = GeminiSEAD4Analyzer()
            logger.info("Using Google Gemini analyzer")
        elif provider == "native":
            # Check if enhanced flag is set
            if use_enhanced:
                from analyzers.enhanced_native_analyzer import EnhancedNativeSEAD4Analyzer
                analyzer = EnhancedNativeSEAD4Analyzer(use_embeddings=True)
                logger.info("Using ENHANCED native analyzer (N-grams + TF-IDF + Embeddings)")
            else:
                from analyzers.native_analyzer import NativeSEAD4Analyzer
                analyzer = NativeSEAD4Analyzer()
                logger.info("Using native (rule-based) analyzer")
        else:
            from analyzers.claude_analyzer import SEAD4Analyzer
            analyzer = SEAD4Analyzer()
            logger.info("Using Claude analyzer")

        logger.info("Running SEAD-4 analysis...")
        result = analyzer.analyze(
            document_text=document_text,
            case_id=case_id,
            report_type=report_type,
            quick_mode=quick,
            precedents=precedents
        )
    
    # Output results
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(result.model_dump(), f, indent=2, default=str)
            
        logger.info(f"Results saved to: {output_path}")
    
    # Print summary
    if compare_mode:
        _print_comparison_results(result, verbose)
    else:
        _print_single_results(result, verbose)

    return result


def _print_single_results(result, verbose: bool = False):
    """Print results from single analysis"""
    print("\n" + "=" * 70)
    print("SEAD-4 ANALYSIS RESULTS")
    print("=" * 70)
    print(f"\nCase ID: {result.case_id}")
    print(f"Analysis Time: {result.analysis_timestamp}")
    
    print(f"\n{'─' * 70}")
    print("OVERALL ASSESSMENT")
    print(f"{'─' * 70}")
    print(f"Recommendation: {result.overall_assessment.recommendation.value}")
    print(f"Confidence: {result.overall_assessment.confidence:.0%}")
    print(f"\nSummary: {result.overall_assessment.summary}")
    
    if result.overall_assessment.key_concerns:
        print(f"\nKey Concerns:")
        for concern in result.overall_assessment.key_concerns:
            print(f"  • {concern}")
            
    if result.overall_assessment.key_mitigations:
        print(f"\nKey Mitigating Factors:")
        for mitigation in result.overall_assessment.key_mitigations:
            print(f"  • {mitigation}")
            
    if result.overall_assessment.bond_amendment_applies:
        print(f"\n⚠️  BOND AMENDMENT APPLIES: {result.overall_assessment.bond_amendment_details}")
    
    print(f"\n{'─' * 70}")
    print("RELEVANT GUIDELINES")
    print(f"{'─' * 70}")
    
    relevant = result.get_relevant_guidelines()
    if relevant:
        for g in relevant:
            severity_display = f"Severity {g.severity.value}" if g.severity else "Severity N/A"
            print(f"\n{g.code}. {g.name} [{severity_display}]")
            print(f"   Confidence: {g.confidence:.0%}")
            
            if g.disqualifiers:
                print(f"   Disqualifiers:")
                for d in g.disqualifiers[:3]:  # Show top 3
                    print(f"     - {d.code}: {d.text[:60]}...")
                    
            if g.mitigators:
                applicable = [m for m in g.mitigators if m.applicability.value in ['FULL', 'PARTIAL']]
                if applicable:
                    print(f"   Mitigators:")
                    for m in applicable[:3]:
                        print(f"     - {m.code} ({m.applicability.value}): {m.text[:50]}...")
                        
            if verbose:
                print(f"   Reasoning: {g.reasoning}")
    else:
        print("\nNo guidelines flagged as relevant.")
    
    # Show precedents if available
    if result.similar_precedents:
        print(f"\n{'─' * 70}")
        print("SIMILAR PRECEDENTS")
        print(f"{'─' * 70}")
        for p in result.similar_precedents[:3]:
            print(f"\n  {p.case_number} - {p.outcome}")
            print(f"  Guidelines: {', '.join(p.guidelines)}")
            print(f"  Relevance: {p.relevance_score:.0%}")
            print(f"  {p.key_similarities[:100]}...")
    
    # Show follow-ups
    if result.follow_up_recommendations:
        print(f"\n{'─' * 70}")
        print("RECOMMENDED FOLLOW-UPS")
        print(f"{'─' * 70}")
        for fu in result.follow_up_recommendations:
            priority_marker = "❗" if fu.priority == "HIGH" else "•"
            print(f"  {priority_marker} [{fu.priority}] {fu.action}")
    
    print("\n" + "=" * 70)
    
    return result


def _print_comparison_results(comparison_result, verbose: bool = False):
    """Print comparison results showing all analysis approaches"""
    print("\n" + "=" * 70)
    print("SEAD-4 COMPARATIVE ANALYSIS RESULTS")
    print("=" * 70)
    print(f"\nCase ID: {comparison_result.case_id}")
    print(f"Analysis Time: {comparison_result.analysis_timestamp}")

    # Print comparison summary
    summary = comparison_result.get_comparison_summary()
    print(f"\n{'─' * 70}")
    print("COMPARISON SUMMARY")
    print(f"{'─' * 70}")

    # Comparison mode always runs all 4 approaches
    print(f"All Four Agree: {'YES ✓' if summary.get('agreement_all_four') else 'NO ✗'}")
    print(f"\n1. Basic Native (Keywords):   {summary['native']['recommendation']:20} (Confidence: {summary['native']['confidence']:.0%})")
    print(f"2. Enhanced Native (ML):      {summary['enhanced_native']['recommendation']:20} (Confidence: {summary['enhanced_native']['confidence']:.0%})")
    print(f"3. LLM (No Guidance):         {summary['llm']['recommendation']:20} (Confidence: {summary['llm']['confidence']:.0%})")
    print(f"4. Enhanced→LLM RAG:          {summary['native_rag']['recommendation']:20} (Confidence: {summary['native_rag']['confidence']:.0%})")

    # Section 1: BASIC NATIVE ANALYSIS
    print(f"\n{'=' * 70}")
    print("SECTION 1: BASIC NATIVE (KEYWORD-ONLY) ANALYSIS")
    print("=" * 70)
    print("\nKeyword matching, pattern recognition, and statistical precedent analysis.")
    print("NO LLM API calls. Fast (~100ms), deterministic, transparent logic.")

    _print_analysis_section(comparison_result.native_result, verbose, "Basic Native")

    # Section 2: ENHANCED NATIVE ANALYSIS (always present in comparison mode)
    print(f"\n{'=' * 70}")
    print("SECTION 2: ENHANCED NATIVE (N-GRAMS + TF-IDF + EMBEDDINGS)")
    print("=" * 70)
    print("\nN-gram phrase matching, TF-IDF weighting, semantic embeddings, contextual analysis.")
    print("NO LLM API calls. Slower (~3s) but 83% precision vs 50% for basic.")

    _print_analysis_section(comparison_result.enhanced_native_result, verbose, "Enhanced Native")

    # Section 3: LLM ANALYSIS (No Guidance)
    print(f"\n{'=' * 70}")
    print("SECTION 3: LLM-BASED ANALYSIS (No Native Guidance)")
    print("=" * 70)
    print("\nAdvanced language model with deep semantic understanding.")
    print("Analyzes document independently without native pre-processing.")

    _print_analysis_section(comparison_result.llm_result, verbose, "LLM")

    # Section 4: ENHANCED NATIVE→LLM RAG (always present in comparison mode)
    print(f"\n{'=' * 70}")
    print("SECTION 4: ENHANCED NATIVE→LLM RAG (Enhanced Guides LLM)")
    print("=" * 70)
    print("\nCombines enhanced native analysis with LLM reasoning.")
    print("Enhanced identifies key guidelines, LLM performs deep analysis on those areas.")
    print("Best accuracy through guided focus.")

    _print_analysis_section(comparison_result.native_rag_result, verbose, "Enhanced Native→LLM RAG")

    print("\n" + "=" * 70)


def _print_analysis_section(result, verbose: bool, analysis_type: str):
    """Print a single analysis section"""
    print(f"\n{'─' * 70}")
    print(f"{analysis_type.upper()} - OVERALL ASSESSMENT")
    print(f"{'─' * 70}")
    print(f"Recommendation: {result.overall_assessment.recommendation.value}")
    print(f"Confidence: {result.overall_assessment.confidence:.0%}")
    print(f"\nSummary: {result.overall_assessment.summary}")

    if result.overall_assessment.key_concerns:
        print(f"\nKey Concerns:")
        for concern in result.overall_assessment.key_concerns:
            print(f"  • {concern}")

    if result.overall_assessment.key_mitigations:
        print(f"\nKey Mitigating Factors:")
        for mitigation in result.overall_assessment.key_mitigations:
            print(f"  • {mitigation}")

    print(f"\n{'─' * 70}")
    print(f"{analysis_type.upper()} - RELEVANT GUIDELINES")
    print(f"{'─' * 70}")

    relevant = result.get_relevant_guidelines()
    if relevant:
        for g in relevant:
            severity_display = f"Severity {g.severity.value}" if g.severity else "Severity N/A"
            print(f"\n{g.code}. {g.name} [{severity_display}]")
            print(f"   Confidence: {g.confidence:.0%}")

            if g.disqualifiers and len(g.disqualifiers) > 0:
                print(f"   Disqualifiers ({len(g.disqualifiers)}):")
                for d in g.disqualifiers[:2]:  # Show top 2
                    print(f"     - {d.code}: {d.text[:50]}...")

            if g.mitigators:
                applicable = [m for m in g.mitigators if m.applicability.value in ['FULL', 'PARTIAL']]
                if applicable:
                    print(f"   Mitigators ({len(applicable)}):")
                    for m in applicable[:2]:
                        print(f"     - {m.code} ({m.applicability.value})")

            if verbose:
                print(f"   Reasoning: {g.reasoning}")
    else:
        print("\nNo guidelines flagged as relevant.")

    # Show precedents if available
    if result.similar_precedents:
        print(f"\n{'─' * 70}")
        print(f"{analysis_type.upper()} - SIMILAR PRECEDENTS")
        print(f"{'─' * 70}")
        for p in result.similar_precedents[:3]:
            print(f"\n  {p.case_number} - {p.outcome}")
            print(f"  Guidelines: {', '.join(p.guidelines)}")
            print(f"  Relevance: {p.relevance_score:.0%}")
            print(f"  {p.key_similarities[:80]}...")


def analyze_batch(
    input_dir: str,
    output_dir: str,
    report_type: Optional[str] = None,
    quick: bool = True,
    provider: str = "gemini"
):
    """Analyze multiple documents in a directory"""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all documents
    documents = list(input_dir.glob("*.pdf")) + list(input_dir.glob("*.txt"))
    logger.info(f"Found {len(documents)} documents to analyze")

    # Create analyzer based on provider
    if provider == "gemini":
        from analyzers.gemini_analyzer import GeminiSEAD4Analyzer
        analyzer = GeminiSEAD4Analyzer()
        logger.info("Using Google Gemini analyzer")
    else:
        from analyzers.claude_analyzer import SEAD4Analyzer
        analyzer = SEAD4Analyzer()
        logger.info("Using Claude analyzer")
    
    results = []
    for i, doc_path in enumerate(documents):
        logger.info(f"Processing {i+1}/{len(documents)}: {doc_path.name}")
        
        try:
            document_text = load_document(doc_path)
            
            result = analyzer.analyze(
                document_text=document_text,
                case_id=doc_path.stem,
                report_type=report_type,
                quick_mode=quick
            )
            
            # Save individual result
            output_path = output_dir / f"{doc_path.stem}_analysis.json"
            with open(output_path, 'w') as f:
                json.dump(result.model_dump(), f, indent=2, default=str)
                
            results.append({
                'file': doc_path.name,
                'recommendation': result.overall_assessment.recommendation.value,
                'confidence': result.overall_assessment.confidence,
                'relevant_guidelines': [g.code for g in result.get_relevant_guidelines()]
            })
            
        except Exception as e:
            logger.error(f"Failed to process {doc_path}: {e}")
            results.append({
                'file': doc_path.name,
                'error': str(e)
            })
    
    # Save summary
    summary_path = output_dir / "batch_summary.json"
    with open(summary_path, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total_documents': len(documents),
            'successful': len([r for r in results if 'error' not in r]),
            'results': results
        }, f, indent=2)
        
    logger.info(f"Batch analysis complete. Summary saved to {summary_path}")
    
    # Print summary
    print(f"\nBatch Analysis Complete")
    print(f"{'─' * 40}")
    print(f"Total documents: {len(documents)}")
    print(f"Successful: {len([r for r in results if 'error' not in r])}")
    print(f"Results saved to: {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description='SEAD-4 Adjudicative Guidelines Analyzer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # MODE 1: Native Analysis Only (fast, no API cost)
    %(prog)s --input report.pdf --provider native

  # MODE 2: LLM Analysis Only (Gemini)
    %(prog)s --input report.pdf --provider gemini

  # MODE 3: Enhanced Native Analysis (N-grams, TF-IDF, embeddings)
    %(prog)s --input report.pdf --provider native --enhanced

  # MODE 4: Native→LLM RAG (native guides LLM for better accuracy)
    %(prog)s --input report.pdf --use-native-rag
    %(prog)s --input report.pdf --use-native-rag --use-rag --index ./doha_index

  Compare all FOUR approaches side-by-side:
    %(prog)s --input report.pdf --compare
    (Shows: Basic Native, Enhanced Native, LLM, and Enhanced→LLM RAG)

  With precedent case matching (RAG):
    %(prog)s --input report.pdf --use-rag --index ./doha_index

  Process entire folder:
    %(prog)s --input test_reports/ --use-native-rag
        """
    )
    
    # Input options
    parser.add_argument('--input', '-i', help='Path to document (PDF or text)')
    parser.add_argument('--input-dir', help='Directory of documents for batch processing')
    
    # Output options
    parser.add_argument('--output', '-o', help='Output JSON path')
    parser.add_argument('--output-dir', default='./analysis_results', help='Output directory for batch')
    
    # Analysis options
    parser.add_argument('--type', '-t', choices=['financial', 'criminal', 'foreign'],
                       help='Report type for specialized analysis')
    parser.add_argument('--quick', '-q', action='store_true',
                       help='Quick analysis mode (less detailed)')
    parser.add_argument('--batch', '-b', action='store_true',
                       help='Batch processing mode')
    
    # RAG options
    parser.add_argument('--use-rag', action='store_true',
                       help='Use precedent retrieval (RAG)')
    parser.add_argument('--index', help='Path to DOHA case index for RAG')

    # Provider options
    parser.add_argument('--provider', '-p', choices=['claude', 'gemini', 'native'], default='gemini',
                       help='Analysis provider: claude (LLM), gemini (LLM), or native (rule-based). Default: gemini')

    # Comparison mode
    parser.add_argument('--compare', '-c', action='store_true',
                       help='Run both native and LLM analysis for comparison')

    # Native RAG mode
    parser.add_argument('--use-native-rag', action='store_true',
                       help='Use native analysis to guide LLM (improves accuracy by focusing LLM on relevant guidelines)')

    # Enhanced native analyzer
    parser.add_argument('--enhanced', '-e', action='store_true',
                       help='Use enhanced native analyzer with N-grams, TF-IDF, and semantic embeddings (requires scikit-learn and sentence-transformers)')

    # Other options
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    logger.add("sead4_analysis.log", rotation="10 MB", level=log_level)

    # Check for API key based on provider (skip for native-only or compare with native)
    if args.provider == "gemini" or (args.compare and not args.provider == "native"):
        if not os.getenv("GEMINI_API_KEY"):
            print("Error: GEMINI_API_KEY environment variable not set")
            print("Set it with: export GEMINI_API_KEY=your_key_here")
            print("(Note: For native-only analysis, use --provider native)")
            return 1
    elif args.provider == "claude":
        if not os.getenv("ANTHROPIC_API_KEY"):
            print("Error: ANTHROPIC_API_KEY environment variable not set")
            print("Set it with: export ANTHROPIC_API_KEY=your_key_here")
            return 1

    # Run appropriate mode
    if args.batch or args.input_dir:
        if not args.input_dir:
            print("Error: --input-dir required for batch mode")
            return 1

        analyze_batch(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            report_type=args.type,
            quick=True,  # Always quick for batch
            provider=args.provider
        )

    elif args.input:
        analyze_single(
            input_path=args.input,
            output_path=args.output,
            report_type=args.type,
            use_rag=args.use_rag,
            index_path=args.index,
            quick=args.quick,
            verbose=args.verbose,
            provider=args.provider,
            compare_mode=args.compare,
            use_native_rag=args.use_native_rag,
            use_enhanced=args.enhanced
        )
        
    else:
        parser.print_help()
        return 1
        
    return 0


if __name__ == "__main__":
    exit(main())
