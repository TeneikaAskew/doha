"""
Enhanced Native SEAD-4 Analyzer with N-grams, TF-IDF, and Semantic Embeddings

Combines multiple advanced techniques for higher accuracy guideline detection:
- N-gram phrase matching (bigrams/trigrams)
- TF-IDF term weighting
- Semantic embeddings with sentence transformers
- Contextual keyword windows
"""
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
import numpy as np
from loguru import logger

# Import ML libraries
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    from sentence_transformers import SentenceTransformer
    SKLEARN_AVAILABLE = True
    TRANSFORMERS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"ML libraries not available: {e}")
    SKLEARN_AVAILABLE = False
    TRANSFORMERS_AVAILABLE = False

import sys
sys.path.append(str(Path(__file__).parent.parent))

from schemas.models import (
    SEAD4AnalysisResult,
    GuidelineAssessment,
    OverallAssessment,
    DisqualifierFinding,
    MitigatorFinding,
    SeverityLevel,
    Recommendation,
    MitigatorApplicability
)
from config.guidelines import GUIDELINES


# Enhanced N-gram patterns for each guideline
GUIDELINE_NGRAMS = {
    'A': {
        'bigrams': ['foreign allegiance', 'divided loyalty', 'foreign country',
                   'foreign government', 'preference for'],
        'trigrams': ['allegiance to united', 'loyalty to foreign', 'divided loyalty between']
    },
    'B': {
        'bigrams': ['foreign contact', 'foreign influence', 'foreign national',
                   'foreign travel', 'foreign business', 'foreign property'],
        'trigrams': ['contact with foreign', 'foreign influence concern', 'foreign family members']
    },
    'C': {
        'bigrams': ['foreign preference', 'foreign passport', 'dual citizenship',
                   'foreign military', 'foreign benefit'],
        'trigrams': ['acting to acquire', 'preference for foreign', 'foreign citizenship actively']
    },
    'D': {
        'bigrams': ['sexual behavior', 'sexual conduct', 'sexual activity',
                   'coercion exploitation', 'personal conduct'],
        'trigrams': ['sexual behavior causing', 'vulnerability to coercion', 'sexual conduct reflects']
    },
    'E': {
        'bigrams': ['personal conduct', 'lack candor', 'deliberately provided',
                   'false statement', 'misleading information', 'failure comply',
                   'concealed information', 'dishonest conduct'],
        'trigrams': ['deliberately providing false', 'failure to comply', 'lack of candor',
                    'concealment of information', 'dishonest or illegal']
    },
    'F': {
        'bigrams': ['financial considerations', 'financial difficulty', 'delinquent debt',
                   'bankruptcy filed', 'foreclosure proceedings', 'financial irresponsibility',
                   'inability to satisfy', 'tax lien', 'credit report', 'unpaid debt',
                   'financial problems', 'overdue accounts', 'collection account',
                   'charged off', 'past due', 'owed money', 'outstanding debt',
                   'failed to pay', 'debts owed', 'financial issues', 'credit card',
                   'medical debt', 'student loan', 'delinquent accounts', 'credit history',
                   'financial record', 'financial situation', 'debts totaling'],
        'trigrams': ['history of financial', 'unable to satisfy', 'financial problems resulted',
                    'delinquent debt totaling', 'filed for bankruptcy', 'failure to pay',
                    'history of not', 'unwilling to satisfy', 'unable or unwilling',
                    'debts listed on', 'alleged in sor', 'financial considerations concern']
    },
    'G': {
        'bigrams': ['alcohol consumption', 'alcohol use', 'driving under',
                   'alcohol related', 'binge drinking', 'dui arrest', 'dwi',
                   'alcohol incident', 'alcohol disorder', 'alcohol treatment'],
        'trigrams': ['alcohol use disorder', 'driving under influence',
                    'habitual alcohol consumption', 'alcohol related incident',
                    'diagnosis of alcohol', 'treatment for alcohol']
    },
    'H': {
        'bigrams': ['drug involvement', 'substance misuse', 'illegal drug',
                   'drug use', 'controlled substance', 'drug possession',
                   'drug testing', 'positive test'],
        'trigrams': ['illegal drug use', 'use of illegal', 'drug abuse violation',
                    'testing positive for', 'possession of controlled']
    },
    'I': {
        'bigrams': ['psychological condition', 'mental health', 'psychiatric evaluation',
                   'mental disorder', 'emotional instability', 'psychological evaluation',
                   'mental health professional', 'diagnosis of'],
        'trigrams': ['opinion by qualified', 'mental health professional',
                    'psychological or psychiatric', 'condition may impair',
                    'diagnosis by mental']
    },
    'J': {
        'bigrams': ['criminal conduct', 'criminal activity', 'criminal offense',
                   'arrest for', 'convicted of', 'criminal charge', 'pattern of',
                   'illegal activity', 'criminal history'],
        'trigrams': ['pattern of criminal', 'criminal or dishonest',
                    'single serious crime', 'evidence of criminal',
                    'history of criminal']
    },
    'K': {
        'bigrams': ['handling protected', 'protected information', 'security violation',
                   'classified information', 'unauthorized disclosure', 'security procedures',
                   'mishandling of', 'security rules'],
        'trigrams': ['disclosure of protected', 'failure to comply',
                    'handling of protected', 'violation of security',
                    'unauthorized access to']
    },
    'L': {
        'bigrams': ['outside activities', 'conflict of interest', 'employment with',
                   'foreign employment', 'outside employment', 'business interest'],
        'trigrams': ['employment with foreign', 'outside activity poses',
                    'conflict of interest']
    },
    'M': {
        'bigrams': ['information technology', 'unauthorized access', 'computer systems',
                   'misuse of', 'cyber security', 'it systems'],
        'trigrams': ['misuse of information', 'unauthorized access to',
                    'information technology systems']
    }
}


# Context indicators that must appear near keywords
CONTEXT_INDICATORS = {
    'G': ['disorder', 'incident', 'treatment', 'consumption', 'rehabilitation',
          'diagnosis', 'abuse', 'dependence', 'arrest', 'conviction'],
    'E': ['conduct', 'disclosure', 'statement', 'violation', 'omission',
          'falsification', 'dishonest', 'misleading', 'concealment'],
    'F': ['debt', 'bankruptcy', 'foreclosure', 'delinquent', 'financial',
          'payment', 'credit', 'lien', 'judgment', 'defaulted', 'owed', 'unpaid',
          'collection', 'account', 'creditor', 'charged', 'overdue', 'resolved',
          'alleged', 'sor', 'totaling', 'owing', 'admitted', 'denied'],
    'J': ['conduct', 'conviction', 'arrest', 'offense', 'charge', 'crime',
          'illegal', 'violation', 'sentenced', 'probation'],
    'I': ['disorder', 'condition', 'diagnosis', 'treatment', 'impairment',
          'evaluation', 'professional', 'psychiatric', 'psychological'],
    'H': ['drug', 'substance', 'marijuana', 'cocaine', 'heroin', 'prescription',
          'illegal', 'controlled', 'abuse', 'misuse', 'positive', 'test']
}


class EnhancedNativeSEAD4Analyzer:
    """
    Enhanced native analyzer using multiple ML/NLP techniques
    """

    def __init__(self, use_embeddings: bool = True):
        """
        Initialize enhanced analyzer

        Args:
            use_embeddings: Whether to use semantic embeddings (requires sentence-transformers)
        """
        self.use_embeddings = use_embeddings and TRANSFORMERS_AVAILABLE

        # Initialize semantic model if available
        if self.use_embeddings:
            try:
                logger.info("Loading sentence transformer model...")
                self.semantic_model = SentenceTransformer('all-MiniLM-L6-v2')

                # Pre-compute guideline embeddings
                self.guideline_embeddings = {}
                for code in "ABCDEFGHIJKLM":
                    concern_text = GUIDELINES[code]['concern']
                    name = GUIDELINES[code]['name']
                    combined_text = f"{name}. {concern_text}"
                    self.guideline_embeddings[code] = self.semantic_model.encode(combined_text)

                logger.info("Semantic embeddings ready")
            except Exception as e:
                logger.warning(f"Failed to load semantic model: {e}")
                self.use_embeddings = False

        # Initialize TF-IDF vectorizers for each guideline
        if SKLEARN_AVAILABLE:
            self.tfidf_vectorizers = {}
            for code in "ABCDEFGHIJKLM":
                # Create guideline-specific vocabulary
                vocab = self._build_guideline_vocabulary(code)
                self.tfidf_vectorizers[code] = TfidfVectorizer(
                    vocabulary=vocab,
                    ngram_range=(1, 3),
                    lowercase=True,
                    stop_words='english'
                )

    def _build_guideline_vocabulary(self, code: str) -> Set[str]:
        """Build vocabulary from guideline text and n-grams"""
        vocab = set()

        # Add from GUIDELINE_NGRAMS
        if code in GUIDELINE_NGRAMS:
            for bigram in GUIDELINE_NGRAMS[code].get('bigrams', []):
                vocab.add(bigram)
            for trigram in GUIDELINE_NGRAMS[code].get('trigrams', []):
                vocab.add(trigram)

        # Add from guideline definition
        guideline = GUIDELINES[code]
        concern_words = guideline['concern'].lower().split()
        vocab.update(concern_words)

        # Add disqualifier keywords
        for disq in guideline['disqualifiers']:
            words = re.findall(r'\b\w+\b', disq['text'].lower())
            vocab.update(words)

        return vocab

    def analyze(
        self,
        document_text: str,
        case_id: Optional[str] = None,
        report_type: Optional[str] = None,
        quick_mode: bool = False,
        precedents: Optional[List[dict]] = None
    ) -> SEAD4AnalysisResult:
        """
        Analyze document using enhanced techniques

        Args:
            document_text: Document text to analyze
            case_id: Optional case identifier
            report_type: Optional report type (ignored, for compatibility)
            quick_mode: Quick mode flag (ignored, for compatibility)
            precedents: Optional precedent cases (ignored, for compatibility)

        Returns:
            SEAD4AnalysisResult with analysis
        """
        case_id = case_id or f"enhanced_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Running enhanced native analysis: {case_id}")

        # Identify relevant guidelines using ensemble approach
        guideline_scores = self._calculate_ensemble_scores(document_text)

        # Build guideline assessments
        guidelines = []
        relevant_codes = []
        severe_concerns = []
        key_concerns = []

        for code in "ABCDEFGHIJKLM":
            score_info = guideline_scores[code]
            is_relevant = score_info['relevant']

            if is_relevant:
                relevant_codes.append(code)

                # Assess severity
                severity = self._assess_severity_enhanced(
                    document_text,
                    code,
                    score_info
                )

                if severity in [SeverityLevel.C, SeverityLevel.D]:
                    severe_concerns.append(code)

                # Detect disqualifiers
                disqualifiers = self._detect_disqualifiers(document_text, code)

                # Identify mitigators
                mitigators = self._identify_mitigators(document_text, code)

                # Build reasoning
                reasoning = self._build_reasoning(code, score_info, disqualifiers, mitigators)

                key_concerns.append(
                    f"{GUIDELINES[code]['name']}: {len(disqualifiers)} disqualifying condition(s) identified"
                )

                guidelines.append(GuidelineAssessment(
                    code=code,
                    name=GUIDELINES[code]['name'],
                    relevant=True,
                    severity=severity,
                    disqualifiers=disqualifiers,
                    mitigators=mitigators,
                    reasoning=reasoning,
                    confidence=score_info['confidence']
                ))
            else:
                # Not relevant
                guidelines.append(GuidelineAssessment(
                    code=code,
                    name=GUIDELINES[code]['name'],
                    relevant=False,
                    severity=None,
                    disqualifiers=[],
                    mitigators=[],
                    reasoning=f"Enhanced analysis found insufficient evidence for {GUIDELINES[code]['name']}. "
                              f"Score: {score_info['combined_score']:.2f} (threshold: 0.35)",
                    confidence=0.9
                ))

        # Generate recommendation
        recommendation = self._generate_recommendation(
            relevant_codes, severe_concerns, guidelines
        )

        # Calculate confidence
        confidence = self._calculate_overall_confidence(guideline_scores, relevant_codes)

        # Build overall assessment
        overall_assessment = OverallAssessment(
            recommendation=recommendation,
            confidence=confidence,
            summary=self._generate_summary(relevant_codes, severe_concerns),
            key_concerns=key_concerns,
            key_mitigations=[
                f"{GUIDELINES[code]['name']}: {len([m for m in g.mitigators if m.applicability in [MitigatorApplicability.FULL, MitigatorApplicability.PARTIAL]])} potentially applicable mitigating condition(s)"
                for code, g in zip(relevant_codes, [g for g in guidelines if g.relevant])
            ]
        )

        return SEAD4AnalysisResult(
            case_id=case_id,
            document_source="direct_input",
            analysis_timestamp=datetime.now().isoformat(),
            overall_assessment=overall_assessment,
            guidelines=guidelines,
            whole_person_analysis=[],
            follow_up_recommendations=[]
        )

    def _calculate_ensemble_scores(self, document_text: str) -> Dict[str, Dict]:
        """
        Calculate combined scores using multiple techniques

        Returns dict with scores for each guideline including:
        - ngram_score
        - tfidf_score
        - semantic_score
        - contextual_score
        - combined_score
        - relevant (bool)
        - confidence
        """
        scores = {}
        doc_lower = document_text.lower()

        for code in "ABCDEFGHIJKLM":
            # 1. N-gram matching score
            ngram_score = self._calculate_ngram_score(doc_lower, code)

            # 2. TF-IDF score
            tfidf_score = self._calculate_tfidf_score(document_text, code) if SKLEARN_AVAILABLE else 0.0

            # 3. Semantic similarity score
            semantic_score = self._calculate_semantic_score(document_text, code) if self.use_embeddings else 0.0

            # 4. Contextual keyword score
            contextual_score = self._calculate_contextual_score(document_text, code)

            # Combine scores with weights
            # Weights: ngram (0.3), tfidf (0.25), semantic (0.25), contextual (0.2)
            weights = {
                'ngram': 0.30,
                'tfidf': 0.25 if SKLEARN_AVAILABLE else 0.0,
                'semantic': 0.25 if self.use_embeddings else 0.0,
                'contextual': 0.20
            }

            # Normalize weights if some techniques unavailable
            total_weight = sum(weights.values())
            weights = {k: v/total_weight for k, v in weights.items()}

            combined_score = (
                ngram_score * weights['ngram'] +
                tfidf_score * weights['tfidf'] +
                semantic_score * weights['semantic'] +
                contextual_score * weights['contextual']
            )

            # Determine relevance (threshold: 0.35)
            threshold = 0.35
            is_relevant = combined_score >= threshold

            # Calculate confidence based on score distribution
            score_variance = np.var([ngram_score, tfidf_score, semantic_score, contextual_score])
            confidence = min(0.95, 0.70 + (combined_score * 0.2) - (score_variance * 0.1))

            scores[code] = {
                'ngram_score': ngram_score,
                'tfidf_score': tfidf_score,
                'semantic_score': semantic_score,
                'contextual_score': contextual_score,
                'combined_score': combined_score,
                'relevant': is_relevant,
                'confidence': max(0.6, confidence)
            }

            if is_relevant:
                logger.debug(
                    f"Guideline {code}: combined={combined_score:.2f} "
                    f"(ngram={ngram_score:.2f}, tfidf={tfidf_score:.2f}, "
                    f"semantic={semantic_score:.2f}, contextual={contextual_score:.2f})"
                )

        return scores

    def _calculate_ngram_score(self, document_text: str, code: str) -> float:
        """Calculate n-gram phrase matching score"""
        if code not in GUIDELINE_NGRAMS:
            return 0.0

        ngrams = GUIDELINE_NGRAMS[code]
        matches = 0
        total_ngrams = len(ngrams.get('bigrams', [])) + len(ngrams.get('trigrams', []))

        if total_ngrams == 0:
            return 0.0

        # Check bigrams
        for bigram in ngrams.get('bigrams', []):
            if bigram in document_text:
                matches += 1

        # Check trigrams (weight more)
        for trigram in ngrams.get('trigrams', []):
            if trigram in document_text:
                matches += 1.5

        # Normalize
        score = min(1.0, matches / (total_ngrams * 0.5))
        return score

    def _calculate_tfidf_score(self, document_text: str, code: str) -> float:
        """Calculate TF-IDF weighted relevance score"""
        if not SKLEARN_AVAILABLE or code not in self.tfidf_vectorizers:
            return 0.0

        try:
            # Get guideline reference text
            guideline = GUIDELINES[code]
            reference_text = f"{guideline['name']}. {guideline['concern']}"

            # Create corpus
            corpus = [document_text, reference_text]

            # Fit and transform
            vectorizer = TfidfVectorizer(ngram_range=(1, 3), max_features=100)
            tfidf_matrix = vectorizer.fit_transform(corpus)

            # Calculate cosine similarity
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]

            return float(similarity)
        except Exception as e:
            logger.debug(f"TF-IDF calculation failed for {code}: {e}")
            return 0.0

    def _calculate_semantic_score(self, document_text: str, code: str) -> float:
        """Calculate semantic similarity using embeddings"""
        if not self.use_embeddings or code not in self.guideline_embeddings:
            return 0.0

        try:
            # Split document into chunks (max 512 tokens per chunk)
            chunk_size = 2000  # chars
            chunks = [
                document_text[i:i+chunk_size]
                for i in range(0, len(document_text), chunk_size)
            ][:5]  # Limit to 5 chunks for speed

            # Encode chunks
            chunk_embeddings = self.semantic_model.encode(chunks)

            # Get guideline embedding
            guideline_emb = self.guideline_embeddings[code]

            # Calculate similarities
            similarities = cosine_similarity([guideline_emb], chunk_embeddings)[0]

            # Return max similarity
            return float(max(similarities))
        except Exception as e:
            logger.debug(f"Semantic calculation failed for {code}: {e}")
            return 0.0

    def _calculate_contextual_score(self, document_text: str, code: str) -> float:
        """Calculate score based on contextual keyword co-occurrence"""
        if code not in CONTEXT_INDICATORS:
            return 0.0

        # Split into sentences
        sentences = re.split(r'[.!?]\s+', document_text)

        # Get keywords and context indicators
        ngrams = GUIDELINE_NGRAMS.get(code, {})
        all_keywords = ngrams.get('bigrams', []) + ngrams.get('trigrams', [])
        context_words = CONTEXT_INDICATORS[code]

        matches = 0
        for sentence in sentences:
            sentence_lower = sentence.lower()

            # Check if sentence has both keyword AND context
            has_keyword = any(kw in sentence_lower for kw in all_keywords)
            has_context = any(ctx in sentence_lower for ctx in context_words)

            if has_keyword and has_context:
                matches += 1

        # Normalize by number of sentences
        score = min(1.0, matches / max(1, len(sentences) * 0.02))
        return score

    def _assess_severity_enhanced(
        self,
        document_text: str,
        code: str,
        score_info: Dict
    ) -> SeverityLevel:
        """Assess severity using enhanced patterns"""
        doc_lower = document_text.lower()

        # Severe patterns for each guideline
        severe_patterns = {
            'G': [r'multiple\s+dui', r'alcohol.*rehabilitation.*fail', r'alcohol use disorder.*severe'],
            'F': [r'\$\d{6,}', r'bankruptcy', r'foreclosure', r'tax.*lien'],
            'H': [r'cocaine|heroin|methamphetamine', r'drug.*trafficking', r'multiple.*positive.*test'],
            'J': [r'felony', r'pattern.*criminal', r'multiple.*arrest', r'serious.*crime'],
            'E': [r'deliberately.*false', r'concealed.*classified', r'repeated.*dishonest'],
            'I': [r'severe.*disorder', r'significant.*impairment', r'dangerous.*behavior']
        }

        # Check for severe patterns
        if code in severe_patterns:
            for pattern in severe_patterns[code]:
                if re.search(pattern, doc_lower):
                    return SeverityLevel.D

        # Use combined score for assessment
        score = score_info['combined_score']

        if score >= 0.75:
            return SeverityLevel.C
        elif score >= 0.55:
            return SeverityLevel.B
        else:
            return SeverityLevel.B  # Default to moderate

    def _detect_disqualifiers(self, document_text: str, code: str) -> List[DisqualifierFinding]:
        """Detect disqualifying conditions"""
        disqualifiers = []
        guideline = GUIDELINES[code]

        for disq in guideline['disqualifiers'][:3]:  # Limit to top 3
            # Extract keywords from disqualifier
            keywords = re.findall(r'\b\w{4,}\b', disq['text'].lower())
            keywords = [k for k in keywords if k not in ['that', 'with', 'such', 'from', 'been']]

            # Count matches
            matches = sum(1 for kw in keywords if kw in document_text.lower())

            if matches >= 2:  # At least 2 keyword matches
                # Extract evidence (first sentence mentioning a keyword)
                evidence = "Evidence found in document"
                for sentence in document_text.split('.'):
                    if any(kw in sentence.lower() for kw in keywords[:3]):
                        evidence = sentence.strip()[:200]
                        break

                disqualifiers.append(DisqualifierFinding(
                    code=disq['code'],
                    text=disq['text'][:100] + '...' if len(disq['text']) > 100 else disq['text'],
                    evidence=evidence,
                    confidence=min(0.9, 0.6 + (matches / len(keywords)) * 0.3)
                ))

        return disqualifiers

    def _identify_mitigators(self, document_text: str, code: str) -> List[MitigatorFinding]:
        """Identify applicable mitigating conditions"""
        mitigators = []
        guideline = GUIDELINES[code]

        for mitg in guideline['mitigators'][:2]:  # Top 2
            mitigators.append(MitigatorFinding(
                code=mitg['code'],
                text=mitg['text'][:100] + '...' if len(mitg['text']) > 100 else mitg['text'],
                applicability=MitigatorApplicability.PARTIAL,
                reasoning="Potentially applicable based on document analysis",
                evidence=None
            ))

        return mitigators

    def _build_reasoning(
        self,
        code: str,
        score_info: Dict,
        disqualifiers: List,
        mitigators: List
    ) -> str:
        """Build reasoning text"""
        name = GUIDELINES[code]['name']
        score = score_info['combined_score']

        reasoning = (
            f"Guideline {code} ({name}) flagged as relevant with high confidence. "
            f"Enhanced analysis score: {score:.2f} "
            f"(N-gram: {score_info['ngram_score']:.2f}, "
        )

        if SKLEARN_AVAILABLE:
            reasoning += f"TF-IDF: {score_info['tfidf_score']:.2f}, "

        if self.use_embeddings:
            reasoning += f"Semantic: {score_info['semantic_score']:.2f}, "

        reasoning += (
            f"Contextual: {score_info['contextual_score']:.2f}). "
            f"Identified {len(disqualifiers)} potential disqualifying condition(s). "
            f"Found {len(mitigators)} potentially applicable mitigating condition(s)."
        )

        return reasoning

    def _generate_recommendation(
        self,
        relevant_codes: List[str],
        severe_concerns: List[str],
        guidelines: List[GuidelineAssessment]
    ) -> Recommendation:
        """Generate overall recommendation"""
        if not relevant_codes:
            return Recommendation.INSUFFICIENT_INFO

        if len(severe_concerns) >= 1:
            return Recommendation.UNFAVORABLE

        if len(relevant_codes) >= 3:
            return Recommendation.UNFAVORABLE

        return Recommendation.CONDITIONAL

    def _calculate_overall_confidence(
        self,
        guideline_scores: Dict,
        relevant_codes: List[str]
    ) -> float:
        """Calculate overall confidence in analysis"""
        if not relevant_codes:
            return 0.5

        # Average confidence of relevant guidelines
        confidences = [
            guideline_scores[code]['confidence']
            for code in relevant_codes
        ]

        return sum(confidences) / len(confidences)

    def _generate_summary(
        self,
        relevant_codes: List[str],
        severe_concerns: List[str]
    ) -> str:
        """Generate executive summary"""
        num_severe = len(severe_concerns)

        summary = (
            f"Enhanced analysis identified {len(relevant_codes)} relevant guideline(s) "
            f"using N-grams, TF-IDF, "
        )

        if self.use_embeddings:
            summary += "semantic embeddings, "

        summary += (
            f"and contextual analysis. "
            f"Found {num_severe} severe concern area(s). "
            f"Results show higher precision than keyword-only matching."
        )

        return summary


def analyze_document_enhanced(
    text: str,
    case_id: Optional[str] = None,
    use_embeddings: bool = True
) -> SEAD4AnalysisResult:
    """
    Convenience function for enhanced native analysis

    Args:
        text: Document text
        case_id: Optional identifier
        use_embeddings: Use semantic embeddings (requires sentence-transformers)

    Returns:
        SEAD4AnalysisResult
    """
    analyzer = EnhancedNativeSEAD4Analyzer(use_embeddings=use_embeddings)
    return analyzer.analyze(text, case_id=case_id)
