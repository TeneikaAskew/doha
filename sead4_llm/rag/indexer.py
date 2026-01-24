"""
DOHA Case Indexer for RAG

Indexes DOHA case decisions for precedent retrieval.
Uses a simple but effective approach with sentence embeddings.
"""
import json
import pickle
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from loguru import logger

# For embeddings - can use various providers
try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    logger.warning("sentence-transformers not installed. Install with: pip install sentence-transformers")


@dataclass
class IndexedCase:
    """A DOHA case indexed for retrieval"""
    case_number: str
    year: int
    outcome: str  # GRANTED, DENIED, REVOKED
    guidelines: List[str]
    summary: str
    key_facts: List[str]
    judge: str
    embedding: Optional[np.ndarray] = None
    
    def to_dict(self) -> dict:
        return {
            'case_number': self.case_number,
            'year': self.year,
            'outcome': self.outcome,
            'guidelines': self.guidelines,
            'summary': self.summary,
            'key_facts': self.key_facts,
            'judge': self.judge
        }


class DOHAIndexer:
    """
    Indexes DOHA cases for semantic search
    
    Uses sentence-transformers for embedding generation.
    Stores index as numpy arrays for fast retrieval.
    """
    
    def __init__(
        self, 
        model_name: str = "all-MiniLM-L6-v2",
        index_path: Optional[Path] = None
    ):
        self.model_name = model_name
        self.index_path = index_path or Path("doha_index")
        self.cases: List[IndexedCase] = []
        self.embeddings: Optional[np.ndarray] = None
        self.model = None
        
    def _load_model(self):
        """Lazy load the embedding model"""
        if self.model is None:
            if not HAS_SENTENCE_TRANSFORMERS:
                raise ImportError("sentence-transformers required for indexing")
            self.model = SentenceTransformer(self.model_name)
            
    def _create_search_text(self, case: IndexedCase) -> str:
        """Create searchable text representation of a case"""
        parts = [
            f"Guidelines: {', '.join(case.guidelines)}",
            f"Outcome: {case.outcome}",
            case.summary,
            " ".join(case.key_facts[:5])  # First 5 key facts
        ]
        return " ".join(parts)
        
    def add_case(self, case: IndexedCase):
        """Add a single case to the index"""
        self._load_model()
        
        # Generate embedding
        search_text = self._create_search_text(case)
        embedding = self.model.encode(search_text)
        case.embedding = embedding
        
        self.cases.append(case)
        
        # Update embeddings matrix
        if self.embeddings is None:
            self.embeddings = embedding.reshape(1, -1)
        else:
            self.embeddings = np.vstack([self.embeddings, embedding])
            
    def add_cases_batch(self, cases: List[IndexedCase], batch_size: int = 32):
        """Add multiple cases efficiently"""
        self._load_model()
        
        logger.info(f"Indexing {len(cases)} cases...")
        
        # Generate all search texts
        search_texts = [self._create_search_text(c) for c in cases]
        
        # Batch encode
        embeddings = self.model.encode(
            search_texts,
            batch_size=batch_size,
            show_progress_bar=True
        )
        
        # Assign embeddings to cases
        for case, emb in zip(cases, embeddings):
            case.embedding = emb
            
        self.cases.extend(cases)
        
        if self.embeddings is None:
            self.embeddings = embeddings
        else:
            self.embeddings = np.vstack([self.embeddings, embeddings])
            
        logger.info(f"Index now contains {len(self.cases)} cases")
        
    def save(self, path: Optional[Path] = None):
        """Save index to disk"""
        path = path or self.index_path
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        
        # Save cases (without embeddings)
        cases_data = [c.to_dict() for c in self.cases]
        with open(path / "cases.json", 'w') as f:
            json.dump(cases_data, f, indent=2)
            
        # Save embeddings
        if self.embeddings is not None:
            np.save(path / "embeddings.npy", self.embeddings)
            
        # Save metadata
        metadata = {
            'model_name': self.model_name,
            'num_cases': len(self.cases),
            'embedding_dim': self.embeddings.shape[1] if self.embeddings is not None else 0
        }
        with open(path / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
            
        logger.info(f"Index saved to {path}")
        
    def load(self, path: Optional[Path] = None):
        """Load index from disk"""
        path = path or self.index_path
        path = Path(path)
        
        if not path.exists():
            raise FileNotFoundError(f"Index not found at {path}")
            
        # Load cases
        with open(path / "cases.json") as f:
            cases_data = json.load(f)
            
        self.cases = [
            IndexedCase(
                case_number=c['case_number'],
                year=c['year'],
                outcome=c['outcome'],
                guidelines=c['guidelines'],
                summary=c['summary'],
                key_facts=c['key_facts'],
                judge=c['judge']
            )
            for c in cases_data
        ]
        
        # Load embeddings
        embeddings_path = path / "embeddings.npy"
        if embeddings_path.exists():
            self.embeddings = np.load(embeddings_path)
            
            # Assign embeddings to cases
            for i, case in enumerate(self.cases):
                case.embedding = self.embeddings[i]
                
        logger.info(f"Loaded index with {len(self.cases)} cases from {path}")
        
    def search(
        self, 
        query: str, 
        top_k: int = 5,
        filter_guidelines: Optional[List[str]] = None,
        filter_outcome: Optional[str] = None
    ) -> List[Tuple[IndexedCase, float]]:
        """
        Search for similar cases
        
        Args:
            query: Search query (e.g., document text or description)
            top_k: Number of results to return
            filter_guidelines: Only return cases with these guidelines
            filter_outcome: Only return cases with this outcome
            
        Returns:
            List of (case, similarity_score) tuples
        """
        if not self.cases:
            return []
            
        self._load_model()
        
        # Encode query
        query_embedding = self.model.encode(query)
        
        # Calculate similarities
        similarities = np.dot(self.embeddings, query_embedding) / (
            np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(query_embedding)
        )
        
        # Apply filters
        mask = np.ones(len(self.cases), dtype=bool)
        
        if filter_guidelines:
            filter_set = set(filter_guidelines)
            mask &= np.array([
                bool(set(c.guidelines) & filter_set) 
                for c in self.cases
            ])
            
        if filter_outcome:
            mask &= np.array([
                c.outcome == filter_outcome 
                for c in self.cases
            ])
            
        # Apply mask
        masked_similarities = similarities.copy()
        masked_similarities[~mask] = -1
        
        # Get top-k
        top_indices = np.argsort(masked_similarities)[-top_k:][::-1]
        
        results = [
            (self.cases[i], float(similarities[i]))
            for i in top_indices
            if similarities[i] > 0
        ]
        
        return results


def create_index_from_extracted_cases(
    cases_path: Path,
    output_path: Path
) -> DOHAIndexer:
    """
    Create index from previously extracted case data
    
    Args:
        cases_path: Path to JSON file with extracted case data
        output_path: Where to save the index
        
    Returns:
        Populated DOHAIndexer
    """
    with open(cases_path) as f:
        cases_data = json.load(f)
        
    indexer = DOHAIndexer(index_path=output_path)
    
    indexed_cases = []
    for c in cases_data:
        # Determine outcome (check both 'outcome' and 'overall_decision' keys)
        outcome = c.get('outcome', c.get('overall_decision', 'UNKNOWN'))
        if outcome not in ['GRANTED', 'DENIED', 'REVOKED', 'REMANDED']:
            outcome = 'UNKNOWN'

        # Get relevant guidelines
        guidelines = []
        if 'guideline_labels' in c:
            codes = list("ABCDEFGHIJKLM")
            guidelines = [codes[i] for i, v in enumerate(c['guideline_labels']) if v]
        elif 'guidelines' in c:
            # Handle both list format (e.g., ['A', 'I', 'M']) and dict format (e.g., {'A': {'relevant': True}})
            if isinstance(c['guidelines'], list):
                guidelines = c['guidelines']
            else:
                guidelines = [g for g, data in c['guidelines'].items() if data.get('relevant')]

        # Get key facts - use sor_allegations for hearings, discussion summary for appeals
        case_type = c.get('case_type', 'hearing')
        if case_type == 'appeal':
            # For appeals, use first part of discussion as key facts
            discussion = c.get('discussion', '')
            key_facts = [discussion[:500]] if discussion else []
        else:
            key_facts = c.get('sor_allegations', [])[:5]

        # Get summary - use 'summary' field or fall back to 'text' or 'full_text'
        summary = c.get('summary', '')
        if not summary:
            summary = c.get('text', c.get('full_text', ''))[:500]

        # Get judge - handle both direct 'judge' field and nested 'metadata.judge'
        judge = c.get('judge', '')
        if not judge:
            judge = c.get('metadata', {}).get('judge', '')

        # Extract year from case number
        case_number = c.get('case_number', 'Unknown')
        try:
            if case_number.startswith('appeal-'):
                # Appeal format: "appeal-2019-108902"
                year = int(case_number.split('-')[1])
            else:
                # Hearing format: "19-12345"
                year_str = case_number[:2]
                year = int(year_str) + (2000 if int(year_str) < 50 else 1900)
        except (ValueError, IndexError):
            year = 2020  # Default fallback

        indexed_cases.append(IndexedCase(
            case_number=case_number,
            year=year,
            outcome=outcome,
            guidelines=guidelines,
            summary=summary[:500] if summary else '',
            key_facts=key_facts,
            judge=judge
        ))
        
    indexer.add_cases_batch(indexed_cases)
    indexer.save()
    
    return indexer


if __name__ == "__main__":
    # Demo usage
    print("DOHA Case Indexer")
    print("=" * 40)
    
    # Create sample cases for demo
    sample_cases = [
        IndexedCase(
            case_number="22-01234",
            year=2022,
            outcome="DENIED",
            guidelines=["F", "E"],
            summary="Applicant had $50,000 in delinquent debt and falsified SF-86",
            key_facts=["Bankruptcy in 2020", "Failed to disclose debts"],
            judge="Smith"
        ),
        IndexedCase(
            case_number="23-00567",
            year=2023,
            outcome="GRANTED",
            guidelines=["F"],
            summary="Applicant had financial difficulties but demonstrated rehabilitation",
            key_facts=["Medical bankruptcy", "All debts now resolved", "Financial counseling completed"],
            judge="Jones"
        ),
        IndexedCase(
            case_number="21-02345",
            year=2021,
            outcome="DENIED",
            guidelines=["G", "J"],
            summary="Multiple DUI convictions, most recent in 2020",
            key_facts=["3 DUI convictions", "Currently on probation", "No treatment"],
            judge="Williams"
        )
    ]
    
    if HAS_SENTENCE_TRANSFORMERS:
        print("\nCreating index with sample cases...")
        indexer = DOHAIndexer(index_path=Path("./demo_index"))
        indexer.add_cases_batch(sample_cases)
        
        # Test search
        print("\nSearching for: 'applicant with debt and bankruptcy'")
        results = indexer.search("applicant with debt and bankruptcy", top_k=2)
        
        for case, score in results:
            print(f"\n  {case.case_number} (Score: {score:.3f})")
            print(f"  Outcome: {case.outcome}")
            print(f"  Guidelines: {', '.join(case.guidelines)}")
            print(f"  Summary: {case.summary[:100]}...")
    else:
        print("\nInstall sentence-transformers to test: pip install sentence-transformers")
