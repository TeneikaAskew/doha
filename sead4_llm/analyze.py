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
    verbose: bool = False
):
    """Analyze a single document"""
    from schemas.models import SEAD4AnalysisResult
    from analyzers.claude_analyzer import SEAD4Analyzer

    # Load document
    input_path = Path(input_path)
    logger.info(f"Loading document: {input_path}")
    document_text = load_document(input_path)
    logger.info(f"Document length: {len(document_text)} characters")

    # Create analyzer
    analyzer = SEAD4Analyzer()
    logger.info("Using Claude analyzer")
    
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
    
    # Run analysis
    logger.info("Running SEAD-4 analysis...")
    case_id = input_path.stem
    
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


def analyze_batch(
    input_dir: str,
    output_dir: str,
    report_type: Optional[str] = None,
    quick: bool = True
):
    """Analyze multiple documents in a directory"""
    from analyzers.claude_analyzer import SEAD4Analyzer

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all documents
    documents = list(input_dir.glob("*.pdf")) + list(input_dir.glob("*.txt"))
    logger.info(f"Found {len(documents)} documents to analyze")

    # Create analyzer
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
  Analyze a single PDF:
    %(prog)s --input report.pdf
    
  Analyze with specific report type:
    %(prog)s --input credit_report.pdf --type financial
    
  Analyze with precedent matching:
    %(prog)s --input report.pdf --use-rag --index ./doha_index
    
  Batch analyze directory:
    %(prog)s --input-dir ./reports --output-dir ./results --batch
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

    # Other options
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    logger.add("sead4_analysis.log", rotation="10 MB", level=log_level)

    # Check for API key
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
            quick=True  # Always quick for batch
        )

    elif args.input:
        analyze_single(
            input_path=args.input,
            output_path=args.output,
            report_type=args.type,
            use_rag=args.use_rag,
            index_path=args.index,
            quick=args.quick,
            verbose=args.verbose
        )
        
    else:
        parser.print_help()
        return 1
        
    return 0


if __name__ == "__main__":
    exit(main())
