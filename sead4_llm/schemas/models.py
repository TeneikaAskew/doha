"""
Pydantic Output Schemas for SEAD-4 Analyzer

Provides structured, validated output formats for LLM responses.
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from enum import Enum


class SeverityLevel(str, Enum):
    """Severity levels for adjudicative concerns"""
    A = "A"  # Minor/Mitigated
    B = "B"  # Moderate
    C = "C"  # Serious
    D = "D"  # Severe/Disqualifying


class Recommendation(str, Enum):
    """Overall recommendation outcomes"""
    FAVORABLE = "FAVORABLE"
    UNFAVORABLE = "UNFAVORABLE"
    CONDITIONAL = "CONDITIONAL"
    INSUFFICIENT_INFO = "INSUFFICIENT_INFO"


class MitigatorApplicability(str, Enum):
    """How well a mitigating condition applies"""
    FULL = "FULL"           # Completely applies
    PARTIAL = "PARTIAL"     # Partially applies
    MINIMAL = "MINIMAL"     # Barely applies
    NONE = "NONE"           # Does not apply


class DisqualifierFinding(BaseModel):
    """A specific disqualifying condition finding"""
    code: str = Field(
        description="AG paragraph reference, e.g., 'AG ¶ 19(a)'",
        examples=["AG ¶ 19(a)", "AG ¶ 31(b)", "AG ¶ 7(a)"]
    )
    text: str = Field(
        description="The disqualifying condition text"
    )
    evidence: str = Field(
        description="Specific evidence from the report that triggers this disqualifier"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence this disqualifier applies (0.0-1.0)"
    )


class MitigatorFinding(BaseModel):
    """A specific mitigating condition finding"""
    code: str = Field(
        description="AG paragraph reference, e.g., 'AG ¶ 20(b)'",
        examples=["AG ¶ 20(b)", "AG ¶ 32(d)", "AG ¶ 8(b)"]
    )
    text: str = Field(
        description="The mitigating condition text"
    )
    applicability: MitigatorApplicability = Field(
        description="How well this mitigator applies to the case"
    )
    reasoning: str = Field(
        description="Explanation of why/how this mitigator applies or doesn't"
    )
    evidence: Optional[str] = Field(
        default=None,
        description="Evidence supporting this mitigator, if any"
    )


class GuidelineAssessment(BaseModel):
    """Assessment for a single SEAD-4 guideline"""
    code: Literal["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M"] = Field(
        description="Guideline letter code"
    )
    name: str = Field(
        description="Full guideline name"
    )
    relevant: bool = Field(
        description="Whether this guideline is relevant to the case"
    )
    severity: Optional[SeverityLevel] = Field(
        default=None,
        description="Severity level if relevant (A=Minor, B=Moderate, C=Serious, D=Severe)"
    )
    disqualifiers: List[DisqualifierFinding] = Field(
        default_factory=list,
        description="Disqualifying conditions that apply"
    )
    mitigators: List[MitigatorFinding] = Field(
        default_factory=list,
        description="Mitigating conditions analyzed"
    )
    reasoning: str = Field(
        description="Overall reasoning for this guideline assessment"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in this assessment (0.0-1.0)"
    )


class WholePersonFactor(BaseModel):
    """A whole-person consideration"""
    factor: str = Field(
        description="The whole-person factor being considered"
    )
    assessment: str = Field(
        description="How this factor applies to the individual"
    )
    impact: Literal["FAVORABLE", "UNFAVORABLE", "NEUTRAL"] = Field(
        description="Whether this factor weighs for or against the individual"
    )


class FollowUpRecommendation(BaseModel):
    """A recommended follow-up action"""
    action: str = Field(
        description="The recommended action"
    )
    priority: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description="Priority level of this follow-up"
    )
    guideline: Optional[str] = Field(
        default=None,
        description="Related guideline code, if applicable"
    )
    rationale: str = Field(
        description="Why this follow-up is recommended"
    )


class SimilarPrecedent(BaseModel):
    """A similar DOHA case precedent"""
    case_number: str = Field(
        description="DOHA case number, e.g., 'ISCR 22-01234'"
    )
    outcome: Literal["GRANTED", "DENIED", "REVOKED"] = Field(
        description="Case outcome"
    )
    guidelines: List[str] = Field(
        description="Guidelines involved in the case"
    )
    relevance_score: float = Field(
        ge=0.0, le=1.0,
        description="How relevant this precedent is (0.0-1.0)"
    )
    key_similarities: str = Field(
        description="Key similarities to current case"
    )
    key_differences: Optional[str] = Field(
        default=None,
        description="Notable differences from current case"
    )
    citation: Optional[str] = Field(
        default=None,
        description="Key quote or citation from the case"
    )


class OverallAssessment(BaseModel):
    """Overall case assessment summary"""
    recommendation: Recommendation = Field(
        description="Overall recommendation"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in the recommendation (0.0-1.0)"
    )
    summary: str = Field(
        description="Executive summary of the assessment (2-3 sentences)"
    )
    key_concerns: List[str] = Field(
        description="List of primary security concerns"
    )
    key_mitigations: List[str] = Field(
        description="List of key mitigating factors"
    )
    bond_amendment_applies: bool = Field(
        default=False,
        description="Whether Bond Amendment disqualifiers apply"
    )
    bond_amendment_details: Optional[str] = Field(
        default=None,
        description="Details if Bond Amendment applies"
    )


class SEAD4AnalysisResult(BaseModel):
    """Complete SEAD-4 analysis result"""
    case_id: str = Field(
        description="Identifier for this analysis"
    )
    document_source: str = Field(
        description="Source document path or description"
    )
    analysis_timestamp: str = Field(
        description="ISO timestamp of analysis"
    )
    overall_assessment: OverallAssessment = Field(
        description="Overall assessment summary"
    )
    guidelines: List[GuidelineAssessment] = Field(
        description="Assessment for each of the 13 guidelines"
    )
    whole_person_analysis: List[WholePersonFactor] = Field(
        default_factory=list,
        description="Whole-person factors considered"
    )
    follow_up_recommendations: List[FollowUpRecommendation] = Field(
        default_factory=list,
        description="Recommended follow-up actions"
    )
    similar_precedents: List[SimilarPrecedent] = Field(
        default_factory=list,
        description="Similar DOHA case precedents (if RAG enabled)"
    )
    raw_text_excerpt: Optional[str] = Field(
        default=None,
        description="Excerpt from analyzed document"
    )
    
    @field_validator('guidelines')
    @classmethod
    def validate_all_guidelines(cls, v):
        """Ensure all 13 guidelines are present"""
        codes = {g.code for g in v}
        expected = set("ABCDEFGHIJKLM")
        if codes != expected:
            missing = expected - codes
            raise ValueError(f"Missing guidelines: {missing}")
        return v
    
    def get_relevant_guidelines(self) -> List[GuidelineAssessment]:
        """Return only guidelines marked as relevant"""
        return [g for g in self.guidelines if g.relevant]
    
    def get_severe_concerns(self) -> List[GuidelineAssessment]:
        """Return guidelines with severity C or D"""
        return [g for g in self.guidelines 
                if g.relevant and g.severity in [SeverityLevel.C, SeverityLevel.D]]
    
    def to_summary_dict(self) -> dict:
        """Return a condensed summary dictionary"""
        relevant = self.get_relevant_guidelines()
        return {
            "case_id": self.case_id,
            "recommendation": self.overall_assessment.recommendation.value,
            "confidence": self.overall_assessment.confidence,
            "summary": self.overall_assessment.summary,
            "relevant_guidelines": [
                {
                    "code": g.code,
                    "name": g.name,
                    "severity": g.severity.value if g.severity else None,
                    "num_disqualifiers": len(g.disqualifiers),
                    "num_mitigators": len([m for m in g.mitigators 
                                          if m.applicability in [MitigatorApplicability.FULL, 
                                                                  MitigatorApplicability.PARTIAL]])
                }
                for g in relevant
            ],
            "key_concerns": self.overall_assessment.key_concerns,
            "follow_ups": [f.action for f in self.follow_up_recommendations if f.priority == "HIGH"]
        }


# For simpler use cases - minimal output schema
class SimpleGuidelineResult(BaseModel):
    """Simplified guideline result for quick assessments"""
    code: str
    relevant: bool
    severity: Optional[str] = None
    summary: str


class SimpleAnalysisResult(BaseModel):
    """Simplified analysis result"""
    recommendation: str
    confidence: float
    guidelines: List[SimpleGuidelineResult]
    summary: str
    concerns: List[str]


class ComparisonAnalysisResult(BaseModel):
    """Comparison of native, LLM, and native-guided LLM analysis results"""
    case_id: str = Field(
        description="Identifier for this analysis"
    )
    analysis_timestamp: str = Field(
        description="ISO timestamp of analysis"
    )
    native_result: SEAD4AnalysisResult = Field(
        description="Result from native/rule-based analysis"
    )
    enhanced_native_result: Optional[SEAD4AnalysisResult] = Field(
        default=None,
        description="Result from enhanced native analysis (N-grams + TF-IDF + Embeddings)"
    )
    llm_result: SEAD4AnalysisResult = Field(
        description="Result from LLM-based analysis (no native guidance)"
    )
    native_rag_result: Optional[SEAD4AnalysisResult] = Field(
        default=None,
        description="Result from LLM with native guidance (RAG)"
    )

    def get_comparison_summary(self) -> dict:
        """Generate a summary comparing all approaches"""
        summary = {
            "case_id": self.case_id,
            "native": {
                "recommendation": self.native_result.overall_assessment.recommendation.value,
                "confidence": self.native_result.overall_assessment.confidence,
                "relevant_guidelines": len(self.native_result.get_relevant_guidelines())
            },
            "llm": {
                "recommendation": self.llm_result.overall_assessment.recommendation.value,
                "confidence": self.llm_result.overall_assessment.confidence,
                "relevant_guidelines": len(self.llm_result.get_relevant_guidelines())
            },
            "agreement_native_llm": self.native_result.overall_assessment.recommendation == self.llm_result.overall_assessment.recommendation
        }

        if self.enhanced_native_result:
            summary["enhanced_native"] = {
                "recommendation": self.enhanced_native_result.overall_assessment.recommendation.value,
                "confidence": self.enhanced_native_result.overall_assessment.confidence,
                "relevant_guidelines": len(self.enhanced_native_result.get_relevant_guidelines())
            }

        if self.native_rag_result:
            summary["native_rag"] = {
                "recommendation": self.native_rag_result.overall_assessment.recommendation.value,
                "confidence": self.native_rag_result.overall_assessment.confidence,
                "relevant_guidelines": len(self.native_rag_result.get_relevant_guidelines())
            }

            # Check agreement based on what's available
            if self.enhanced_native_result:
                summary["agreement_all_four"] = (
                    self.native_result.overall_assessment.recommendation ==
                    self.enhanced_native_result.overall_assessment.recommendation ==
                    self.llm_result.overall_assessment.recommendation ==
                    self.native_rag_result.overall_assessment.recommendation
                )
            else:
                summary["agreement_all_three"] = (
                    self.native_result.overall_assessment.recommendation ==
                    self.llm_result.overall_assessment.recommendation ==
                    self.native_rag_result.overall_assessment.recommendation
                )

        return summary
