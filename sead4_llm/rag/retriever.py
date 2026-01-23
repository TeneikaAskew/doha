"""
Precedent Retriever for RAG-Augmented Analysis

Retrieves similar DOHA cases to augment LLM analysis with precedents.
"""
from pathlib import Path
from typing import List, Optional, Dict
from loguru import logger

from rag.indexer import DOHAIndexer, IndexedCase


class PrecedentRetriever:
    """
    Retrieves relevant DOHA case precedents for analysis augmentation
    
    Provides similar cases based on:
    - Document content similarity
    - Matching guidelines
    - Similar fact patterns
    """
    
    def __init__(self, index_path: Optional[Path] = None):
        self.index_path = index_path
        self.indexer: Optional[DOHAIndexer] = None
        self._loaded = False
        
    def load(self, index_path: Optional[Path] = None):
        """Load the DOHA case index"""
        path = index_path or self.index_path
        
        if path is None:
            raise ValueError("No index path specified")
            
        self.indexer = DOHAIndexer(index_path=path)
        self.indexer.load()
        self._loaded = True
        
        logger.info(f"Loaded precedent index with {len(self.indexer.cases)} cases")
        
    def retrieve(
        self,
        document_text: str,
        guidelines: Optional[List[str]] = None,
        num_precedents: int = 5,
        include_favorable: bool = True,
        include_unfavorable: bool = True
    ) -> List[Dict]:
        """
        Retrieve relevant precedent cases
        
        Args:
            document_text: The document being analyzed
            guidelines: Specific guidelines to match (optional)
            num_precedents: Number of precedents to retrieve
            include_favorable: Include GRANTED cases
            include_unfavorable: Include DENIED/REVOKED cases
            
        Returns:
            List of precedent dicts suitable for prompt augmentation
        """
        if not self._loaded:
            self.load()
            
        # First, do a semantic search
        results = self.indexer.search(
            query=document_text[:5000],  # Use first 5000 chars
            top_k=num_precedents * 3,  # Get extra for filtering
            filter_guidelines=guidelines
        )
        
        # Filter by outcome preference
        filtered = []
        for case, score in results:
            if case.outcome == 'GRANTED' and not include_favorable:
                continue
            if case.outcome in ['DENIED', 'REVOKED'] and not include_unfavorable:
                continue
            filtered.append((case, score))
            
        # Take top N
        filtered = filtered[:num_precedents]
        
        # Convert to prompt-ready format
        precedents = []
        for case, score in filtered:
            precedents.append({
                'case_number': f"ISCR {case.case_number}",
                'outcome': case.outcome,
                'guidelines': case.guidelines,
                'summary': case.summary,
                'key_facts': case.key_facts,
                'relevance_score': score,
                'year': case.year
            })
            
        logger.debug(f"Retrieved {len(precedents)} precedents")
        return precedents
        
    def retrieve_by_guideline(
        self,
        guideline: str,
        outcome: Optional[str] = None,
        num_cases: int = 3
    ) -> List[Dict]:
        """
        Retrieve cases for a specific guideline
        
        Useful for finding precedents for specific concerns.
        """
        if not self._loaded:
            self.load()
            
        results = self.indexer.search(
            query=f"Guideline {guideline}",
            top_k=num_cases * 2,
            filter_guidelines=[guideline],
            filter_outcome=outcome
        )
        
        return [
            {
                'case_number': f"ISCR {case.case_number}",
                'outcome': case.outcome,
                'guidelines': case.guidelines,
                'summary': case.summary,
                'key_facts': case.key_facts,
                'relevance_score': score
            }
            for case, score in results[:num_cases]
        ]
        
    def get_guideline_statistics(self) -> Dict:
        """Get statistics about cases in the index by guideline"""
        if not self._loaded:
            self.load()
            
        stats = {
            code: {'total': 0, 'granted': 0, 'denied': 0}
            for code in "ABCDEFGHIJKLM"
        }
        
        for case in self.indexer.cases:
            for g in case.guidelines:
                if g in stats:
                    stats[g]['total'] += 1
                    if case.outcome == 'GRANTED':
                        stats[g]['granted'] += 1
                    elif case.outcome in ['DENIED', 'REVOKED']:
                        stats[g]['denied'] += 1
                        
        return stats


class RAGAnalyzer:
    """
    Combines precedent retrieval with LLM analysis
    
    Wrapper that integrates retriever with the main analyzer.
    """
    
    def __init__(
        self,
        analyzer,  # SEAD4Analyzer instance
        retriever: PrecedentRetriever
    ):
        self.analyzer = analyzer
        self.retriever = retriever
        
    def analyze_with_precedents(
        self,
        document_text: str,
        case_id: Optional[str] = None,
        report_type: Optional[str] = None,
        num_precedents: int = 5
    ):
        """
        Analyze document with precedent augmentation
        
        Args:
            document_text: Document to analyze
            case_id: Optional identifier
            report_type: Type of report
            num_precedents: Number of precedents to include
            
        Returns:
            SEAD4AnalysisResult with precedents
        """
        # First, do a quick analysis to identify likely guidelines
        from schemas.models import SimpleAnalysisResult
        
        quick_result = self.analyzer.analyze(
            document_text,
            case_id=f"{case_id}_quick" if case_id else None,
            quick_mode=True
        )
        
        # Get relevant guidelines from quick analysis
        relevant_guidelines = [
            g.code for g in quick_result.guidelines if g.relevant
        ]
        
        # Retrieve precedents
        precedents = self.retriever.retrieve(
            document_text=document_text,
            guidelines=relevant_guidelines if relevant_guidelines else None,
            num_precedents=num_precedents
        )
        
        # Full analysis with precedents
        result = self.analyzer.analyze(
            document_text=document_text,
            case_id=case_id,
            report_type=report_type,
            precedents=precedents
        )
        
        return result


def create_retriever(index_path: Path) -> PrecedentRetriever:
    """Factory function to create a retriever"""
    retriever = PrecedentRetriever(index_path=index_path)
    retriever.load()
    return retriever


if __name__ == "__main__":
    import os
    
    print("Precedent Retriever Demo")
    print("=" * 40)
    
    # Check if demo index exists
    demo_index = Path("./demo_index")
    
    if demo_index.exists():
        retriever = PrecedentRetriever(index_path=demo_index)
        retriever.load()
        
        # Test retrieval
        test_doc = """
        The applicant has approximately $45,000 in delinquent debt, including
        credit cards, medical bills, and a repossessed vehicle. The applicant
        filed for Chapter 7 bankruptcy in 2021 which was discharged in 2022.
        The applicant reports that the financial problems were due to a period
        of unemployment following COVID-19 related layoffs.
        """
        
        print("\nTest document describes: Financial difficulties with bankruptcy")
        print("\nRetrieving similar precedents...")
        
        precedents = retriever.retrieve(test_doc, guidelines=['F'], num_precedents=3)
        
        for p in precedents:
            print(f"\n  {p['case_number']} ({p['outcome']})")
            print(f"  Guidelines: {', '.join(p['guidelines'])}")
            print(f"  Relevance: {p['relevance_score']:.3f}")
            print(f"  Summary: {p['summary'][:80]}...")
    else:
        print("\nDemo index not found. Run indexer.py first to create sample index.")
