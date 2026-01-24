"""
Native SEAD-4 Analyzer

Rule-based and similarity-based analysis without LLM API calls.
Uses traditional NLP techniques, pattern matching, and precedent statistics
to provide security clearance assessments.
"""
import re
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Tuple
from collections import Counter
from loguru import logger

import sys
sys.path.append(str(Path(__file__).parent.parent))
from schemas.models import (
    SEAD4AnalysisResult,
    GuidelineAssessment,
    OverallAssessment,
    DisqualifierFinding,
    MitigatorFinding,
    SimilarPrecedent,
    SeverityLevel,
    Recommendation,
    MitigatorApplicability,
)
from config.guidelines import GUIDELINES


class NativeSEAD4Analyzer:
    """
    Native SEAD-4 analyzer using rule-based and statistical methods.

    This analyzer provides analysis without making LLM API calls by using:
    - Keyword and pattern matching for guideline identification
    - Statistical analysis of similar precedents
    - Rule-based recommendation generation
    - Template-based natural language generation
    """

    # Keyword patterns for each guideline
    GUIDELINE_KEYWORDS = {
        'A': ['allegiance', 'treason', 'espionage', 'sabotage', 'terrorism', 'sedition', 'overthrow'],
        'B': ['foreign', 'foreign contact', 'foreign national', 'dual citizenship', 'foreign property', 'foreign business'],
        'C': ['foreign preference', 'foreign passport', 'foreign voting', 'foreign military'],
        'D': ['sexual behavior', 'sexual conduct', 'pornography', 'sexual misconduct'],
        'E': ['personal conduct', 'dishonest', 'untrustworthy', 'rule violation', 'misconduct'],
        'F': ['financial', 'debt', 'bankruptcy', 'foreclosure', 'delinquent', 'credit', 'financial problem'],
        'G': ['alcohol', 'drinking', 'dui', 'dwi', 'intoxication', 'alcohol abuse'],
        'H': ['drug', 'marijuana', 'cocaine', 'heroin', 'illegal substance', 'prescription abuse', 'controlled substance'],
        'I': ['psychological', 'mental health', 'psychiatric', 'counseling', 'therapy', 'diagnosis'],
        'J': ['criminal', 'arrest', 'conviction', 'felony', 'misdemeanor', 'charge', 'probation'],
        'K': ['handling protected information', 'classified', 'security violation', 'spillage'],
        'L': ['outside activities', 'conflict of interest', 'outside employment'],
        'M': ['use of information technology', 'cyber', 'unauthorized access', 'computer']
    }

    # Severity patterns
    SEVERE_PATTERNS = {
        'F': [r'\$\s*\d{6,}', r'bankruptcy', r'foreclosure'],  # $100k+ debt, bankruptcy
        'G': [r'multiple\s+dui', r'dui.*dui', r'alcohol.*treatment', r'rehabilitation'],
        'H': [r'cocaine|heroin|methamphetamine', r'drug.*sale|sell.*drug', r'trafficking'],
        'J': [r'felony', r'prison', r'incarceration'],
    }

    def __init__(self):
        """Initialize the native analyzer"""
        pass

    def analyze(
        self,
        document_text: str,
        case_id: Optional[str] = None,
        report_type: Optional[str] = None,
        quick_mode: bool = False,
        precedents: Optional[List[dict]] = None
    ) -> SEAD4AnalysisResult:
        """
        Analyze a document using native/rule-based methods

        Args:
            document_text: The text content to analyze
            case_id: Optional identifier for this analysis
            report_type: Type of report (financial, criminal, foreign)
            quick_mode: If True, use simpler analysis
            precedents: Optional list of similar precedents

        Returns:
            SEAD4AnalysisResult with native analysis
        """
        case_id = case_id or f"native_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        logger.info(f"Running native analysis: {case_id}")

        # Convert to lowercase for matching
        doc_lower = document_text.lower()

        # Step 1: Identify relevant guidelines using keyword matching
        relevant_guidelines = self._identify_guidelines(doc_lower)

        # Step 2: Assess severity for each relevant guideline
        guideline_assessments = []
        for code in "ABCDEFGHIJKLM":
            if code in relevant_guidelines:
                assessment = self._assess_guideline(
                    code,
                    document_text,
                    doc_lower,
                    quick_mode
                )
            else:
                # Create non-relevant guideline
                assessment = GuidelineAssessment(
                    code=code,
                    name=GUIDELINES[code]['name'],
                    relevant=False,
                    severity=None,
                    disqualifiers=[],
                    mitigators=[],
                    reasoning="No relevant indicators found in document",
                    confidence=0.8
                )
            guideline_assessments.append(assessment)

        # Step 3: Analyze precedents if provided
        precedent_analysis = None
        similar_precedents = []
        if precedents:
            precedent_analysis = self._analyze_precedents(precedents, relevant_guidelines)
            similar_precedents = [
                SimilarPrecedent(
                    case_number=p['case_number'],
                    outcome=p['outcome'],
                    guidelines=p.get('guidelines', []),
                    relevance_score=p.get('relevance_score', 0.5),
                    key_similarities=p.get('summary', '')[:200],
                    key_differences=None,
                    citation=None
                )
                for p in precedents[:5]
            ]

        # Step 4: Generate overall recommendation
        overall = self._generate_recommendation(
            guideline_assessments,
            precedent_analysis,
            document_text
        )

        return SEAD4AnalysisResult(
            case_id=case_id,
            document_source="native_analysis",
            analysis_timestamp=datetime.now().isoformat(),
            overall_assessment=overall,
            guidelines=guideline_assessments,
            whole_person_analysis=[],
            follow_up_recommendations=[],
            similar_precedents=similar_precedents,
            raw_text_excerpt=document_text[:500] if document_text else None
        )

    def _identify_guidelines(self, doc_lower: str) -> Dict[str, float]:
        """
        Identify relevant guidelines using keyword matching

        Returns:
            Dict mapping guideline code to confidence score
        """
        relevant = {}

        for code, keywords in self.GUIDELINE_KEYWORDS.items():
            # Count keyword occurrences
            matches = sum(doc_lower.count(kw.lower()) for kw in keywords)

            if matches > 0:
                # Calculate confidence based on frequency
                # More matches = higher confidence
                confidence = min(0.5 + (matches * 0.1), 0.95)
                relevant[code] = confidence
                logger.debug(f"Guideline {code}: {matches} keyword matches, confidence {confidence:.2f}")

        return relevant

    def _assess_guideline(
        self,
        code: str,
        document_text: str,
        doc_lower: str,
        quick_mode: bool
    ) -> GuidelineAssessment:
        """
        Assess a specific guideline
        """
        guideline_info = GUIDELINES[code]

        # Find potential disqualifiers by keyword matching
        disqualifiers = []
        if not quick_mode:
            for disq in guideline_info.get('disqualifiers', [])[:3]:  # Top 3
                # Check if disqualifier text keywords appear in document
                disq_keywords = self._extract_keywords(disq['text'])
                matches = sum(1 for kw in disq_keywords if kw in doc_lower)

                if matches >= 2:  # At least 2 keyword matches
                    confidence = min(0.4 + (matches * 0.15), 0.9)
                    disqualifiers.append(DisqualifierFinding(
                        code=disq['code'],
                        text=disq['text'],
                        evidence=f"Pattern-based match: {matches} keywords found",
                        confidence=confidence
                    ))

        # Find potential mitigators
        mitigators = []
        if not quick_mode and disqualifiers:
            # Only look for mitigators if there are disqualifiers
            for mitg in guideline_info.get('mitigators', [])[:2]:  # Top 2
                mitig_keywords = self._extract_keywords(mitg['text'])
                matches = sum(1 for kw in mitig_keywords if kw in doc_lower)

                if matches >= 1:
                    applicability = MitigatorApplicability.PARTIAL if matches >= 2 else MitigatorApplicability.MINIMAL
                    mitigators.append(MitigatorFinding(
                        code=mitg['code'],
                        text=mitg['text'],
                        applicability=applicability,
                        reasoning=f"Pattern-based analysis suggests potential applicability (keyword matches: {matches})",
                        evidence=None
                    ))

        # Determine severity
        severity = self._assess_severity(code, document_text, doc_lower, len(disqualifiers))

        # Generate reasoning
        reasoning = self._generate_guideline_reasoning(
            code,
            guideline_info['name'],
            len(disqualifiers),
            len(mitigators),
            severity
        )

        # Calculate confidence mathematically based on evidence strength
        if disqualifiers:
            # Average confidence of disqualifiers found
            disq_confidences = [d.confidence for d in disqualifiers]
            avg_disq_confidence = sum(disq_confidences) / len(disq_confidences)

            # Boost based on severity (more severe = higher confidence in relevance)
            severity_boost = {
                SeverityLevel.D: 0.15,  # Severe
                SeverityLevel.C: 0.10,  # Serious
                SeverityLevel.B: 0.05,  # Moderate
                SeverityLevel.A: 0.0    # Minor
            }.get(severity, 0.0)

            # Combine: base disqualifier confidence + severity boost
            confidence = min(0.95, avg_disq_confidence + severity_boost)
        else:
            # No disqualifiers but guideline flagged - low confidence
            confidence = 0.45

        # Slightly reduce if mitigators present (indicates ambiguity)
        if mitigators:
            confidence = max(0.4, confidence - 0.05)

        return GuidelineAssessment(
            code=code,
            name=guideline_info['name'],
            relevant=True,
            severity=severity,
            disqualifiers=disqualifiers,
            mitigators=mitigators,
            reasoning=reasoning,
            confidence=confidence
        )

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract important keywords from text"""
        # Remove common words and keep significant terms
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'that', 'this', 'it', 'if', 'not'}

        words = re.findall(r'\b\w+\b', text.lower())
        return [w for w in words if len(w) > 3 and w not in stop_words]

    def _assess_severity(
        self,
        code: str,
        document_text: str,
        doc_lower: str,
        num_disqualifiers: int
    ) -> Optional[SeverityLevel]:
        """Assess severity level based on patterns and disqualifiers"""

        # Check for severe patterns
        if code in self.SEVERE_PATTERNS:
            for pattern in self.SEVERE_PATTERNS[code]:
                if re.search(pattern, doc_lower):
                    return SeverityLevel.D  # Severe

        # Based on number of disqualifiers
        if num_disqualifiers >= 3:
            return SeverityLevel.C  # Serious
        elif num_disqualifiers >= 2:
            return SeverityLevel.B  # Moderate
        elif num_disqualifiers >= 1:
            return SeverityLevel.B  # Moderate
        else:
            return SeverityLevel.A  # Minor

    def _generate_guideline_reasoning(
        self,
        code: str,
        name: str,
        num_disqualifiers: int,
        num_mitigators: int,
        severity: Optional[SeverityLevel]
    ) -> str:
        """Generate natural language reasoning for guideline assessment"""

        parts = [f"Guideline {code} ({name}) appears relevant based on keyword analysis."]

        if num_disqualifiers > 0:
            parts.append(f"Identified {num_disqualifiers} potential disqualifying condition(s).")
        else:
            parts.append("No specific disqualifying conditions identified through pattern matching.")

        if num_mitigators > 0:
            parts.append(f"Found {num_mitigators} potentially applicable mitigating condition(s).")

        if severity:
            severity_desc = {
                SeverityLevel.A: "minor or mitigated concerns",
                SeverityLevel.B: "moderate concerns",
                SeverityLevel.C: "serious concerns",
                SeverityLevel.D: "severe security concerns"
            }
            parts.append(f"Assessed severity: {severity_desc.get(severity, 'moderate concerns')}.")

        return " ".join(parts)

    def _analyze_precedents(
        self,
        precedents: List[dict],
        relevant_guidelines: Dict[str, float]
    ) -> Dict:
        """
        Analyze precedents statistically

        Returns summary statistics about similar cases
        """
        if not precedents:
            return None

        outcomes = [p['outcome'] for p in precedents]
        outcome_counts = Counter(outcomes)

        # Find most common outcome
        total = len(outcomes)
        denied_pct = (outcome_counts.get('DENIED', 0) + outcome_counts.get('REVOKED', 0)) / total
        granted_pct = outcome_counts.get('GRANTED', 0) / total

        # Analyze guideline overlap
        precedent_guidelines = []
        for p in precedents:
            precedent_guidelines.extend(p.get('guidelines', []))

        guideline_freq = Counter(precedent_guidelines)

        return {
            'total_precedents': total,
            'denied_percentage': denied_pct,
            'granted_percentage': granted_pct,
            'most_common_outcome': outcome_counts.most_common(1)[0][0] if outcome_counts else 'UNKNOWN',
            'common_guidelines': guideline_freq.most_common(3),
            'avg_relevance': sum(p.get('relevance_score', 0.5) for p in precedents) / len(precedents)
        }

    def _generate_recommendation(
        self,
        guidelines: List[GuidelineAssessment],
        precedent_analysis: Optional[Dict],
        document_text: str
    ) -> OverallAssessment:
        """
        Generate overall recommendation based on guideline assessments and precedents
        """
        relevant = [g for g in guidelines if g.relevant]
        severe = [g for g in relevant if g.severity in [SeverityLevel.C, SeverityLevel.D]]

        # Collect concerns
        concerns = []
        mitigations = []

        for g in relevant:
            if g.disqualifiers:
                concerns.append(f"{g.name}: {len(g.disqualifiers)} disqualifying condition(s) identified")
            if g.mitigators:
                applicable = [m for m in g.mitigators if m.applicability in [MitigatorApplicability.FULL, MitigatorApplicability.PARTIAL]]
                if applicable:
                    mitigations.append(f"{g.name}: {len(applicable)} potentially applicable mitigating condition(s)")

        # Calculate overall confidence mathematically
        def calculate_overall_confidence(
            relevant_guidelines: List[GuidelineAssessment],
            severe_count: int,
            precedent_info: Optional[Dict]
        ) -> float:
            """Calculate confidence based on evidence strength"""
            if not relevant_guidelines:
                return 0.35  # Very low confidence when nothing found

            # Base confidence: average of relevant guideline confidences
            guideline_confidences = [g.confidence for g in relevant_guidelines]
            base_confidence = sum(guideline_confidences) / len(guideline_confidences)

            # Boost for severe concerns (high severity = more confident in overall assessment)
            severity_boost = min(0.15, severe_count * 0.05)

            # Precedent alignment boost (if precedents support the conclusion)
            precedent_boost = 0.0
            if precedent_info:
                # If precedents strongly align with our conclusion, boost confidence
                if precedent_info.get('denied_percentage', 0) > 0.7:
                    precedent_boost = 0.10
                elif precedent_info.get('avg_relevance', 0) > 0.7:
                    precedent_boost = 0.05

            # Combine components
            total_confidence = base_confidence + severity_boost + precedent_boost

            # Cap at reasonable bounds
            return min(0.92, max(0.35, total_confidence))

        # Determine recommendation
        if not relevant:
            recommendation = Recommendation.INSUFFICIENT_INFO
            confidence = calculate_overall_confidence(relevant, len(severe), precedent_analysis)
            summary = "Native analysis using keyword matching found no clear security concerns. Limited information available for comprehensive assessment."

        elif severe:
            # Severe concerns found
            recommendation = Recommendation.UNFAVORABLE
            confidence = calculate_overall_confidence(relevant, len(severe), precedent_analysis)
            if precedent_analysis and precedent_analysis['denied_percentage'] > 0.7:
                summary = f"Analysis identified {len(severe)} severe concern area(s). Similar precedents show {precedent_analysis['denied_percentage']:.0%} denial rate. Significant security concerns identified through pattern matching."
            else:
                summary = f"Analysis identified {len(severe)} severe concern area(s) based on keyword and pattern matching. Further investigation recommended."

        elif len(relevant) >= 3:
            # Multiple moderate concerns
            if precedent_analysis and precedent_analysis['granted_percentage'] > 0.6:
                recommendation = Recommendation.CONDITIONAL
            else:
                recommendation = Recommendation.UNFAVORABLE

            confidence = calculate_overall_confidence(relevant, len(severe), precedent_analysis)

            if precedent_analysis:
                if precedent_analysis['granted_percentage'] > 0.6:
                    summary = f"Multiple security concern areas identified ({len(relevant)} guidelines). Similar cases show {precedent_analysis['granted_percentage']:.0%} approval rate with mitigation. Conditional recommendation pending mitigation verification."
                else:
                    summary = f"Multiple security concerns across {len(relevant)} guideline areas. Similar precedents suggest unfavorable outcomes without strong mitigation."
            else:
                summary = f"Pattern analysis identified concerns in {len(relevant)} guideline areas. Conditional recommendation pending further review."

        else:
            # Few concerns
            recommendation = Recommendation.CONDITIONAL
            confidence = calculate_overall_confidence(relevant, len(severe), precedent_analysis)

            if mitigations:
                if precedent_analysis and precedent_analysis['granted_percentage'] > 0.5:
                    summary = f"Limited security concerns identified with potential mitigating factors. Similar cases show {precedent_analysis['granted_percentage']:.0%} approval rate."
                else:
                    summary = "Security concerns identified but potential mitigating factors present. Conditional recommendation pending verification of mitigation."
            else:
                summary = f"Security concerns identified in {len(relevant)} area(s). Native analysis suggests conditional recommendation pending detailed review."

        return OverallAssessment(
            recommendation=recommendation,
            confidence=confidence,
            summary=summary,
            key_concerns=concerns[:5],  # Top 5
            key_mitigations=mitigations[:5],  # Top 5
            bond_amendment_applies=False,
            bond_amendment_details=None
        )


def analyze_document(
    text: str,
    case_id: Optional[str] = None,
    report_type: Optional[str] = None,
    precedents: Optional[List[dict]] = None
) -> SEAD4AnalysisResult:
    """
    Convenience function for native document analysis

    Args:
        text: Document text to analyze
        case_id: Optional identifier
        report_type: Type of report (not used in native analysis)
        precedents: Optional list of similar precedents

    Returns:
        SEAD4AnalysisResult
    """
    analyzer = NativeSEAD4Analyzer()
    return analyzer.analyze(text, case_id=case_id, precedents=precedents)
