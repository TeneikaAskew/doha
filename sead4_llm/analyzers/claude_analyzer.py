"""
Claude-based SEAD-4 Analyzer

Uses Claude API with structured prompting for security clearance analysis.
"""
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Union
from anthropic import Anthropic
from loguru import logger

import sys
sys.path.append(str(Path(__file__).parent.parent))
from schemas.models import (
    SEAD4AnalysisResult, 
    GuidelineAssessment,
    OverallAssessment,
    DisqualifierFinding,
    MitigatorFinding,
    WholePersonFactor,
    FollowUpRecommendation,
    SimilarPrecedent,
    SeverityLevel,
    Recommendation,
    MitigatorApplicability,
    SimpleAnalysisResult
)
from prompts.templates import (
    SYSTEM_PROMPT,
    build_analysis_prompt,
    get_specialized_system_prompt
)
from config.guidelines import GUIDELINES


class SEAD4Analyzer:
    """
    Claude-powered SEAD-4 Adjudicative Guidelines Analyzer
    
    Provides explainable, citation-backed security clearance assessments.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 8000
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
            
        self.client = Anthropic(api_key=self.api_key)
        self.model = model
        self.max_tokens = max_tokens
        
    def analyze(
        self,
        document_text: str,
        case_id: Optional[str] = None,
        report_type: Optional[str] = None,
        quick_mode: bool = False,
        precedents: Optional[List[dict]] = None
    ) -> SEAD4AnalysisResult:
        """
        Analyze a document against SEAD-4 guidelines
        
        Args:
            document_text: The text content to analyze
            case_id: Optional identifier for this analysis
            report_type: Type of report (financial, criminal, foreign) for specialized analysis
            quick_mode: If True, return a simplified quick assessment
            precedents: Optional list of similar DOHA cases for RAG-augmented analysis
            
        Returns:
            SEAD4AnalysisResult with complete analysis
        """
        case_id = case_id or f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Select appropriate system prompt
        system_prompt = (
            get_specialized_system_prompt(report_type) 
            if report_type 
            else SYSTEM_PROMPT
        )
        
        # Build analysis prompt
        user_prompt = build_analysis_prompt(
            document_text=document_text,
            quick_mode=quick_mode,
            precedents=precedents
        )
        
        logger.info(f"Analyzing document: {case_id}")
        logger.debug(f"Document length: {len(document_text)} chars")
        
        # Call Claude API
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            response_text = response.content[0].text
            logger.debug(f"Response length: {len(response_text)} chars")
            
        except Exception as e:
            logger.error(f"API call failed: {e}")
            raise
            
        # Parse response
        result = self._parse_response(response_text, case_id, document_text)
        
        # Add precedents if provided
        if precedents:
            result.similar_precedents = [
                SimilarPrecedent(
                    case_number=p['case_number'],
                    outcome=p['outcome'],
                    guidelines=p.get('guidelines', []),
                    relevance_score=p.get('relevance_score', 0.5),
                    key_similarities=p.get('summary', ''),
                    key_differences=p.get('differences'),
                    citation=p.get('citation')
                )
                for p in precedents[:5]
            ]
            
        return result
        
    def _parse_response(
        self, 
        response_text: str, 
        case_id: str,
        document_text: str
    ) -> SEAD4AnalysisResult:
        """Parse LLM response into structured result"""
        
        # Extract JSON from response
        try:
            # Try to find JSON in response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                data = json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")
                
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON, attempting repair: {e}")
            data = self._repair_json(response_text)
            
        # Convert to structured result
        try:
            result = self._build_result(data, case_id, document_text)
        except Exception as e:
            logger.error(f"Failed to build result: {e}")
            # Return a minimal result
            result = self._build_minimal_result(case_id, document_text, str(e))
            
        return result
        
    def _build_result(
        self, 
        data: dict, 
        case_id: str,
        document_text: str
    ) -> SEAD4AnalysisResult:
        """Build SEAD4AnalysisResult from parsed data"""
        
        # Build overall assessment
        oa_data = data.get('overall_assessment', {})
        overall_assessment = OverallAssessment(
            recommendation=Recommendation(oa_data.get('recommendation', 'INSUFFICIENT_INFO')),
            confidence=float(oa_data.get('confidence', 0.5)),
            summary=oa_data.get('summary', 'Analysis completed'),
            key_concerns=oa_data.get('key_concerns', []),
            key_mitigations=oa_data.get('key_mitigations', []),
            bond_amendment_applies=oa_data.get('bond_amendment_applies', False),
            bond_amendment_details=oa_data.get('bond_amendment_details')
        )
        
        # Build guideline assessments
        guidelines = []
        guidelines_data = data.get('guidelines', [])
        
        # Create a map of provided guidelines
        provided_guidelines = {g.get('code'): g for g in guidelines_data}
        
        # Ensure all 13 guidelines are present
        for code in "ABCDEFGHIJKLM":
            if code in provided_guidelines:
                g_data = provided_guidelines[code]
            else:
                # Create placeholder for missing guideline
                g_data = {
                    'code': code,
                    'name': GUIDELINES[code]['name'],
                    'relevant': False,
                    'reasoning': 'No information provided',
                    'confidence': 0.5
                }
                
            # Build disqualifiers
            disqualifiers = [
                DisqualifierFinding(
                    code=d.get('code', 'AG ¶ Unknown'),
                    text=d.get('text', ''),
                    evidence=d.get('evidence', ''),
                    confidence=float(d.get('confidence', 0.5))
                )
                for d in g_data.get('disqualifiers', [])
            ]
            
            # Build mitigators
            mitigators = [
                MitigatorFinding(
                    code=m.get('code', 'AG ¶ Unknown'),
                    text=m.get('text', ''),
                    applicability=MitigatorApplicability(m.get('applicability', 'NONE')),
                    reasoning=m.get('reasoning', ''),
                    evidence=m.get('evidence')
                )
                for m in g_data.get('mitigators', [])
            ]
            
            # Determine severity
            severity = None
            if g_data.get('relevant') and g_data.get('severity'):
                try:
                    severity = SeverityLevel(g_data['severity'])
                except (ValueError, KeyError) as e:
                    logger.warning(f"Invalid severity level '{g_data['severity']}' for guideline {code}: {e}, defaulting to B")
                    severity = SeverityLevel.B  # Default to moderate
                    
            guidelines.append(GuidelineAssessment(
                code=code,
                name=g_data.get('name', GUIDELINES[code]['name']),
                relevant=g_data.get('relevant', False),
                severity=severity,
                disqualifiers=disqualifiers,
                mitigators=mitigators,
                reasoning=g_data.get('reasoning', ''),
                confidence=float(g_data.get('confidence', 0.5))
            ))
            
        # Build whole-person factors
        whole_person = [
            WholePersonFactor(
                factor=wp.get('factor', ''),
                assessment=wp.get('assessment', ''),
                impact=wp.get('impact', 'NEUTRAL')
            )
            for wp in data.get('whole_person_analysis', [])
        ]
        
        # Build follow-up recommendations
        follow_ups = [
            FollowUpRecommendation(
                action=fu.get('action', ''),
                priority=fu.get('priority', 'MEDIUM'),
                guideline=fu.get('guideline'),
                rationale=fu.get('rationale', '')
            )
            for fu in data.get('follow_up_recommendations', [])
        ]
        
        return SEAD4AnalysisResult(
            case_id=case_id,
            document_source="direct_input",
            analysis_timestamp=datetime.now().isoformat(),
            overall_assessment=overall_assessment,
            guidelines=guidelines,
            whole_person_analysis=whole_person,
            follow_up_recommendations=follow_ups,
            similar_precedents=[],
            raw_text_excerpt=document_text[:500] if document_text else None
        )
        
    def _repair_json(self, text: str) -> dict:
        """Attempt to repair malformed JSON"""
        # Try common fixes
        text = text.strip()
        
        # Remove markdown code blocks
        if text.startswith('```'):
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1] if lines[-1] == '```' else lines[1:])
            
        # Try parsing again
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Could not repair JSON after removing code fence: {e}")
            pass

        # Return empty structure
        logger.warning("Could not repair JSON, returning empty structure")
        return {}
        
    def _build_minimal_result(
        self, 
        case_id: str, 
        document_text: str,
        error: str
    ) -> SEAD4AnalysisResult:
        """Build a minimal result when parsing fails"""
        
        # Create placeholder guidelines
        guidelines = [
            GuidelineAssessment(
                code=code,
                name=GUIDELINES[code]['name'],
                relevant=False,
                severity=None,
                disqualifiers=[],
                mitigators=[],
                reasoning=f"Analysis error: {error}",
                confidence=0.0
            )
            for code in "ABCDEFGHIJKLM"
        ]
        
        return SEAD4AnalysisResult(
            case_id=case_id,
            document_source="direct_input",
            analysis_timestamp=datetime.now().isoformat(),
            overall_assessment=OverallAssessment(
                recommendation=Recommendation.INSUFFICIENT_INFO,
                confidence=0.0,
                summary=f"Analysis could not be completed: {error}",
                key_concerns=["Analysis error"],
                key_mitigations=[],
                bond_amendment_applies=False
            ),
            guidelines=guidelines,
            whole_person_analysis=[],
            follow_up_recommendations=[
                FollowUpRecommendation(
                    action="Re-run analysis with corrected input",
                    priority="HIGH",
                    rationale=f"Previous analysis failed: {error}"
                )
            ],
            similar_precedents=[],
            raw_text_excerpt=document_text[:500] if document_text else None
        )
        
    def analyze_batch(
        self,
        documents: List[dict],
        quick_mode: bool = True
    ) -> List[SEAD4AnalysisResult]:
        """
        Analyze multiple documents
        
        Args:
            documents: List of dicts with 'text' and optional 'case_id', 'report_type'
            quick_mode: Use quick analysis for batch processing
            
        Returns:
            List of SEAD4AnalysisResult
        """
        results = []
        
        for i, doc in enumerate(documents):
            logger.info(f"Processing document {i+1}/{len(documents)}")
            
            try:
                result = self.analyze(
                    document_text=doc['text'],
                    case_id=doc.get('case_id', f'batch_{i}'),
                    report_type=doc.get('report_type'),
                    quick_mode=quick_mode
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to analyze document {i}: {e}")
                results.append(self._build_minimal_result(
                    f'batch_{i}', doc.get('text', ''), str(e)
                ))
                
        return results


def analyze_document(
    text: str,
    case_id: Optional[str] = None,
    report_type: Optional[str] = None,
    api_key: Optional[str] = None
) -> SEAD4AnalysisResult:
    """
    Convenience function for single document analysis
    
    Args:
        text: Document text to analyze
        case_id: Optional identifier
        report_type: Type of report (financial, criminal, foreign)
        api_key: Anthropic API key (or set ANTHROPIC_API_KEY env var)
        
    Returns:
        SEAD4AnalysisResult
    """
    analyzer = SEAD4Analyzer(api_key=api_key)
    return analyzer.analyze(text, case_id=case_id, report_type=report_type)


if __name__ == "__main__":
    # Test with a sample document
    sample_text = """
    BACKGROUND INVESTIGATION SUMMARY
    Subject: John Doe
    Date: January 2025
    
    FINANCIAL REVIEW:
    Credit report shows total delinquent debt of $47,000 including:
    - Credit card: $12,000 (120 days past due)
    - Auto loan: $15,000 (repossessed 2023)
    - Medical bills: $8,000 (in collections)
    - Student loans: $12,000 (in forbearance)
    
    Subject filed Chapter 7 bankruptcy in 2019, discharged 2020.
    Subject reports job loss in March 2022 due to company downsizing.
    Currently employed since September 2023.
    No evidence of financial counseling.
    
    CRIMINAL HISTORY:
    2018 - DUI, sentenced to 12 months probation, completed
    2021 - Domestic disturbance, charges dropped
    
    FOREIGN CONTACTS:
    None reported.
    
    DRUG USE:
    Subject admits to marijuana use 2015-2018, states no use since.
    """
    
    print("Testing SEAD-4 Analyzer...")
    print("=" * 60)
    
    # Check for API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set. Set it to run the test.")
        print("\nExample output structure:")
        from schemas.models import SEAD4AnalysisResult
        print(SEAD4AnalysisResult.model_json_schema())
    else:
        result = analyze_document(sample_text, case_id="test_001")
        print(result.overall_assessment.summary)
        print(f"\nRecommendation: {result.overall_assessment.recommendation}")
        print(f"Confidence: {result.overall_assessment.confidence:.0%}")
        print("\nRelevant Guidelines:")
        for g in result.get_relevant_guidelines():
            print(f"  - {g.code} ({g.name}): Severity {g.severity}")
