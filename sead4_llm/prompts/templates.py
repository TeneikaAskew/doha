"""
Prompt Templates for SEAD-4 Analysis

Structured prompts that embed the full guidelines and guide the LLM
to produce consistent, citation-backed assessments.
"""
from typing import Optional, List
from config.guidelines import GUIDELINES, SEVERITY_CRITERIA, WHOLE_PERSON_FACTORS, BOND_AMENDMENT


def build_guidelines_reference() -> str:
    """Build the complete guidelines reference section"""
    sections = []
    
    for code in "ABCDEFGHIJKLM":
        g = GUIDELINES[code]
        section = f"""
## Guideline {code}: {g['name']}

**Concern:** {g['concern'].strip()}

**Disqualifying Conditions:**
"""
        for d in g['disqualifiers']:
            section += f"- {d['code']}: {d['text']}\n"
            
        section += "\n**Mitigating Conditions:**\n"
        for m in g['mitigators']:
            section += f"- {m['code']}: {m['text']}\n"
            
        sections.append(section)
        
    return "\n".join(sections)


def build_severity_reference() -> str:
    """Build severity assessment criteria reference"""
    lines = ["## Severity Assessment Scale\n"]
    
    for level, info in SEVERITY_CRITERIA.items():
        lines.append(f"**Level {level} - {info['level']}**: {info['description']}")
        lines.append("Indicators:")
        for ind in info['indicators']:
            lines.append(f"  - {ind}")
        lines.append("")
        
    return "\n".join(lines)


SYSTEM_PROMPT = f"""You are an expert security clearance adjudication analyst with deep knowledge of 
SEAD-4 (Security Executive Agent Directive 4) National Security Adjudicative Guidelines.

Your role is to analyze reports and documents to:
1. Identify which of the 13 adjudicative guidelines (A-M) are relevant
2. Cite specific disqualifying conditions (AG paragraphs) with evidence
3. Evaluate applicable mitigating conditions
4. Assess severity on a scale of A-D
5. Apply whole-person analysis
6. Provide a recommendation with clear reasoning

You must cite specific AG paragraphs (e.g., "AG ¶ 19(a)") for all findings.
Your analysis must be thorough, fair, and consistent with adjudicative standards.

# SEAD-4 ADJUDICATIVE GUIDELINES REFERENCE

{build_guidelines_reference()}

# SEVERITY ASSESSMENT CRITERIA

{build_severity_reference()}

# WHOLE-PERSON CONCEPT

{WHOLE_PERSON_FACTORS}

# BOND AMENDMENT

{BOND_AMENDMENT}

# ANALYSIS PRINCIPLES

1. **Be thorough**: Analyze ALL 13 guidelines, even if not relevant
2. **Cite specifically**: Always reference AG ¶ numbers with quotes
3. **Be balanced**: Consider both disqualifying AND mitigating conditions
4. **Be fair**: Apply the "clearly consistent with national interest" standard
5. **Explain reasoning**: Provide clear rationale for each conclusion
6. **Consider recency**: More recent conduct weighs more heavily
7. **Look for patterns**: Multiple incidents are more concerning than isolated ones
8. **Consider rehabilitation**: Genuine change mitigates past concerns
"""


ANALYSIS_PROMPT_TEMPLATE = """Analyze the following document against SEAD-4 adjudicative guidelines.

# DOCUMENT TO ANALYZE

```
{document_text}
```

# ANALYSIS INSTRUCTIONS

Provide a comprehensive analysis following this structure:

1. **Initial Assessment**: Briefly summarize what type of report this is and key facts

2. **Guideline Analysis**: For EACH of the 13 guidelines (A through M):
   - State whether it is RELEVANT or NOT RELEVANT
   - If relevant:
     - List specific disqualifying conditions triggered (cite AG ¶ numbers)
     - Quote evidence from the document
     - Evaluate each potential mitigating condition
     - Assign severity (A/B/C/D) with reasoning
   - If not relevant, briefly explain why

3. **Whole-Person Analysis**: Consider the 9 whole-person factors

4. **Overall Assessment**:
   - Recommendation: FAVORABLE, UNFAVORABLE, or CONDITIONAL
   - Confidence level (0.0-1.0)
   - Key concerns summary
   - Key mitigating factors summary

5. **Follow-Up Recommendations**: What additional information would strengthen the assessment?

# OUTPUT FORMAT

**IMPORTANT**: You MUST analyze ALL 13 guidelines (A through M), even if they are not relevant.
For non-relevant guidelines, set "relevant": false and provide brief reasoning.

**CRITICAL**: Respond with ONLY a valid JSON object (no markdown, no explanation) matching this exact schema.
Do NOT use different key names like "adjudicative_guideline_analyses" - use "guidelines" exactly as shown:

{{
  "case_id": "string - document identifier",
  "overall_assessment": {{
    "recommendation": "FAVORABLE|UNFAVORABLE|CONDITIONAL|INSUFFICIENT_INFO",
    "confidence": 0.0-1.0,
    "summary": "2-3 sentence executive summary",
    "key_concerns": ["list of primary concerns"],
    "key_mitigations": ["list of key mitigating factors"],
    "bond_amendment_applies": true/false,
    "bond_amendment_details": "string if applicable"
  }},
  "guidelines": [
    {{
      "code": "A-M",
      "name": "guideline name",
      "relevant": true/false,
      "severity": "A|B|C|D" or null,
      "disqualifiers": [
        {{
          "code": "AG ¶ XX(x)",
          "text": "disqualifier text",
          "evidence": "quoted evidence from document",
          "confidence": 0.0-1.0
        }}
      ],
      "mitigators": [
        {{
          "code": "AG ¶ XX(x)",
          "text": "mitigator text",
          "applicability": "FULL|PARTIAL|MINIMAL|NONE",
          "reasoning": "explanation",
          "evidence": "quoted evidence if any"
        }}
      ],
      "reasoning": "overall reasoning for this guideline",
      "confidence": 0.0-1.0
    }}
    // ... for all 13 guidelines A-M
  ],
  "whole_person_analysis": [
    {{
      "factor": "factor name",
      "assessment": "how it applies",
      "impact": "FAVORABLE|UNFAVORABLE|NEUTRAL"
    }}
  ],
  "follow_up_recommendations": [
    {{
      "action": "recommended action",
      "priority": "HIGH|MEDIUM|LOW",
      "guideline": "related guideline code or null",
      "rationale": "why recommended"
    }}
  ]
}}

Begin your analysis:"""


QUICK_ANALYSIS_PROMPT = """Quickly analyze this document for SEAD-4 security concerns.

Document:
```
{document_text}
```

Identify:
1. Which guidelines (A-M) appear relevant
2. The most significant concern
3. Any obvious mitigating factors
4. Quick recommendation

Respond concisely in JSON:
{{
  "relevant_guidelines": ["list of codes"],
  "primary_concern": "brief description",
  "key_mitigator": "if any",
  "recommendation": "FAVORABLE|UNFAVORABLE|NEEDS_REVIEW",
  "confidence": 0.0-1.0,
  "summary": "1-2 sentences"
}}
"""


RAG_AUGMENTED_PROMPT_TEMPLATE = """Analyze the following document against SEAD-4 guidelines.

# DOCUMENT TO ANALYZE

```
{document_text}
```

# SIMILAR PRECEDENT CASES

The following DOHA cases have similar fact patterns. Use them to inform your analysis:

{precedents}

# ANALYSIS INSTRUCTIONS

1. Analyze the document against all 13 guidelines
2. Reference precedent cases where applicable
3. Note how precedents support or differ from this case
4. Provide recommendation with precedent-backed reasoning

{standard_instructions}
"""


def build_analysis_prompt(
    document_text: str,
    quick_mode: bool = False,
    precedents: Optional[List[dict]] = None,
    native_analysis: Optional[dict] = None
) -> str:
    """Build the appropriate analysis prompt"""

    if quick_mode:
        return QUICK_ANALYSIS_PROMPT.format(document_text=document_text[:10000])

    # If native analysis is provided, include it as guidance
    if native_analysis:
        native_guidance_text = f"""
# INITIAL RULE-BASED ANALYSIS (For Your Reference)

A keyword-based analyzer has performed initial triage and identified the following:

**Potentially Relevant Guidelines**: {', '.join(native_analysis.get('relevant_guidelines', []))}
**Severe Concerns**: {', '.join(native_analysis.get('severe_concerns', []))}
**Initial Recommendation**: {native_analysis.get('recommendation', 'N/A')}
**Confidence**: {native_analysis.get('confidence', 0.0):.0%}

**Key Concerns Identified**:
{chr(10).join(f'  - {concern}' for concern in native_analysis.get('key_concerns', [])[:3])}

**IMPORTANT**: This is preliminary guidance from pattern matching. You should:
1. Conduct your own independent deep analysis of ALL 13 guidelines
2. Pay special attention to the guidelines flagged above
3. Either confirm these findings with detailed legal reasoning, OR
4. Explain what the rule-based analyzer missed or got wrong
5. Provide much more nuanced analysis than simple keyword matching can achieve

**CRITICAL - OUTPUT FORMAT**: You MUST respond with the EXACT JSON schema specified below.
Do NOT change the schema structure. Do NOT use different key names like "adjudicative_guideline_analyses".
The JSON must use "guidelines" as the array key, exactly as shown in the schema below.
"""

        precedent_section = ""
        if precedents:
            precedent_text = "\n\n".join([
                f"**Case {p['case_number']}** (Outcome: {p['outcome']})\n"
                f"Guidelines: {', '.join(p['guidelines'])}\n"
                f"Summary: {p['summary']}\n"
                f"Key Finding: {p.get('key_finding', 'N/A')}"
                for p in precedents[:5]
            ])
            precedent_section = f"\n\n# SIMILAR PRECEDENT CASES\n\n{precedent_text}\n"

        full_instructions = f"""{native_guidance_text}{precedent_section}

# DOCUMENT TO ANALYZE

```
{document_text[:15000]}
```

# ANALYSIS INSTRUCTIONS

Conduct a comprehensive analysis of this document against all SEAD-4 guidelines, using the native analysis as a starting point but applying your superior semantic understanding and legal reasoning.

**CRITICAL**: You MUST respond with ONLY valid JSON matching the EXACT schema structure below.
Do NOT modify the schema. Do NOT use different key names. Use "guidelines" not "adjudicative_guideline_analyses".

**REQUIRED JSON SCHEMA** (respond with this structure ONLY):

{{
  "case_id": "string - document identifier",
  "overall_assessment": {{
    "recommendation": "FAVORABLE|UNFAVORABLE|CONDITIONAL|INSUFFICIENT_INFO",
    "confidence": 0.0-1.0,
    "summary": "2-3 sentence executive summary",
    "key_concerns": ["list of primary concerns"],
    "key_mitigations": ["list of key mitigating factors"],
    "bond_amendment_applies": true/false,
    "bond_amendment_details": "string if applicable"
  }},
  "guidelines": [
    {{
      "code": "A-M",
      "name": "guideline name",
      "relevant": true/false,
      "severity": "A|B|C|D" or null,
      "disqualifiers": [
        {{
          "code": "AG ¶ XX(x)",
          "text": "disqualifier text",
          "evidence": "quoted evidence from document",
          "confidence": 0.0-1.0
        }}
      ],
      "mitigators": [
        {{
          "code": "AG ¶ XX(x)",
          "text": "mitigator text",
          "applicability": "FULL|PARTIAL|MINIMAL|NONE",
          "reasoning": "explanation",
          "evidence": "quoted evidence if any"
        }}
      ],
      "reasoning": "overall reasoning for this guideline",
      "confidence": 0.0-1.0
    }}
    // ... for all 13 guidelines A-M
  ],
  "whole_person_analysis": [
    {{
      "factor": "factor name",
      "assessment": "how it applies",
      "impact": "FAVORABLE|UNFAVORABLE|NEUTRAL"
    }}
  ],
  "follow_up_recommendations": [
    {{
      "action": "recommended action",
      "priority": "HIGH|MEDIUM|LOW",
      "guideline": "related guideline code or null",
      "rationale": "why recommended"
    }}
  ]
}}

Begin your analysis with ONLY the JSON response above. Do not include markdown code blocks or any other formatting.
"""
        return full_instructions

    if precedents:
        precedent_text = "\n\n".join([
            f"**Case {p['case_number']}** (Outcome: {p['outcome']})\n"
            f"Guidelines: {', '.join(p['guidelines'])}\n"
            f"Summary: {p['summary']}\n"
            f"Key Finding: {p.get('key_finding', 'N/A')}"
            for p in precedents[:5]  # Limit to 5 precedents
        ])

        return RAG_AUGMENTED_PROMPT_TEMPLATE.format(
            document_text=document_text[:15000],
            precedents=precedent_text,
            standard_instructions="""
**CRITICAL**: You MUST respond with ONLY valid JSON matching this EXACT schema.
Use "guidelines" as the array key, not "adjudicative_guideline_analyses" or any other variation.

The response must be a JSON object with these exact top-level keys:
- case_id
- overall_assessment
- guidelines (array of 13 guideline objects)
- whole_person_analysis (array)
- follow_up_recommendations (array)

Respond with ONLY the JSON object, no markdown blocks, no explanation.
"""
        )

    return ANALYSIS_PROMPT_TEMPLATE.format(document_text=document_text[:20000])


# Specialized prompts for specific report types
FINANCIAL_REPORT_PROMPT = """You are analyzing a FINANCIAL report (credit report, bankruptcy filing, tax records).

Focus especially on Guideline F (Financial Considerations).

Key factors to evaluate:
- Total debt amount and types
- Payment history patterns
- Bankruptcies and their chapters
- Tax compliance
- Evidence of financial counseling
- Debt resolution efforts

{base_instructions}
"""

CRIMINAL_REPORT_PROMPT = """You are analyzing a CRIMINAL HISTORY report.

Focus especially on Guidelines J (Criminal Conduct) and potentially G (Alcohol) and H (Drugs).

Key factors to evaluate:
- Nature and seriousness of offenses
- Pattern vs. isolated incidents
- Recency of conduct
- Sentencing and compliance
- Evidence of rehabilitation
- Bond Amendment applicability

{base_instructions}
"""

FOREIGN_CONTACT_PROMPT = """You are analyzing a FOREIGN CONTACT or TRAVEL report.

Focus especially on Guidelines B (Foreign Influence) and C (Foreign Preference).

Key factors to evaluate:
- Countries involved and their risk level
- Nature of foreign contacts (family, business, etc.)
- Frequency and depth of contact
- Foreign financial interests
- Dual citizenship issues
- Reporting compliance

{base_instructions}
"""


def get_specialized_system_prompt(report_type: str) -> str:
    """Get a specialized system prompt based on report type"""
    base = SYSTEM_PROMPT
    
    type_prompts = {
        "financial": FINANCIAL_REPORT_PROMPT,
        "criminal": CRIMINAL_REPORT_PROMPT,
        "foreign": FOREIGN_CONTACT_PROMPT
    }
    
    if report_type.lower() in type_prompts:
        return base + "\n\n" + type_prompts[report_type.lower()].format(
            base_instructions="Apply these considerations in your analysis."
        )
    
    return base
