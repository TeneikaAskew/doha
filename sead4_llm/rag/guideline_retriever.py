"""
Guideline RAG Retriever

Retrieves only relevant SEAD-4 guidelines based on document analysis,
reducing token usage and improving LLM focus.
"""
from typing import List, Dict, Set
from config.guidelines import GUIDELINES


class GuidelineRetriever:
    """
    Retrieves relevant SEAD-4 guidelines for focused LLM prompts

    Instead of sending all 13 guidelines to the LLM, this retriever:
    1. Uses native analysis to identify candidate guidelines
    2. Retrieves only those specific guidelines
    3. Optionally adds closely related guidelines
    4. Returns focused guideline context for the LLM
    """

    # Related guidelines that should be checked together
    RELATED_GUIDELINES = {
        'G': ['H', 'I'],  # Alcohol often relates to drugs and psych
        'H': ['G', 'I'],  # Drugs often relate to alcohol and psych
        'I': ['G', 'H'],  # Psychological often relates to substance abuse
        'J': ['G', 'H'],  # Criminal often relates to DUI/drugs
        'F': [],          # Financial is usually standalone
        'B': ['C'],       # Foreign influence often relates to foreign preference
        'C': ['B'],       # Foreign preference often relates to foreign influence
        'E': [],          # Personal conduct is usually standalone
    }

    def __init__(self):
        """Initialize guideline retriever"""
        pass

    def retrieve_guidelines(
        self,
        relevant_codes: List[str],
        include_related: bool = True,
        always_include: Set[str] = None
    ) -> Dict[str, dict]:
        """
        Retrieve specific guidelines for LLM analysis

        Args:
            relevant_codes: List of guideline codes (e.g., ['F', 'G', 'H'])
            include_related: If True, also include related guidelines
            always_include: Set of guideline codes to always include (e.g., {'E', 'K'})

        Returns:
            Dict mapping guideline codes to their full specifications
        """
        codes_to_retrieve = set(relevant_codes)

        # Add related guidelines
        if include_related:
            for code in relevant_codes:
                related = self.RELATED_GUIDELINES.get(code, [])
                codes_to_retrieve.update(related)

        # Add always-include guidelines
        if always_include:
            codes_to_retrieve.update(always_include)

        # Retrieve guidelines
        retrieved = {}
        for code in codes_to_retrieve:
            if code in GUIDELINES:
                retrieved[code] = GUIDELINES[code]

        return retrieved

    def build_focused_prompt(
        self,
        document_text: str,
        relevant_codes: List[str],
        include_related: bool = True
    ) -> tuple[str, List[str]]:
        """
        Build a focused prompt with only relevant guidelines

        Args:
            document_text: The document to analyze
            relevant_codes: Potentially relevant guideline codes
            include_related: Whether to include related guidelines

        Returns:
            Tuple of (focused_system_prompt, list_of_included_guideline_codes)
        """
        # Retrieve guidelines
        guidelines = self.retrieve_guidelines(relevant_codes, include_related)

        # Build focused guidelines reference
        guideline_text = self._build_guidelines_section(guidelines)

        # Build focused system prompt
        system_prompt = f"""You are an expert security clearance adjudication analyst with deep knowledge of
SEAD-4 (Security Executive Agent Directive 4) National Security Adjudicative Guidelines.

Based on initial analysis, the following guidelines appear potentially relevant to this case:
{', '.join(sorted(guidelines.keys()))}

# RELEVANT SEAD-4 GUIDELINES

{guideline_text}

# ANALYSIS INSTRUCTIONS

1. **Primary focus**: Analyze the guidelines listed above in detail
2. **Also consider**: Briefly check if any OTHER guidelines (not listed above) might be relevant
3. **Be thorough**: For each relevant guideline:
   - Cite specific disqualifying conditions (AG ¶ numbers) with evidence
   - Evaluate applicable mitigating conditions
   - Assess severity (A/B/C/D)
4. **Output ALL 13 guidelines**: Even if not relevant, include with "relevant": false

# ANALYSIS PRINCIPLES

1. **Be thorough**: Analyze ALL 13 guidelines, even if not in the focus set
2. **Cite specifically**: Always reference AG ¶ numbers
3. **Be balanced**: Consider both disqualifying AND mitigating conditions
4. **Be fair**: Apply the "clearly consistent with national interest" standard
5. **Explain reasoning**: Provide clear rationale for each conclusion
"""

        return system_prompt, list(sorted(guidelines.keys()))

    def _build_guidelines_section(self, guidelines: Dict[str, dict]) -> str:
        """Build the guidelines reference section"""
        sections = []

        for code in sorted(guidelines.keys()):
            g = guidelines[code]
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

    def calculate_token_savings(
        self,
        relevant_codes: List[str],
        include_related: bool = True
    ) -> Dict[str, int]:
        """
        Calculate token savings from focused retrieval

        Returns:
            Dict with 'full_prompt', 'focused_prompt', 'savings_tokens', 'savings_percent'
        """
        # Full prompt with all 13 guidelines
        all_guidelines_text = self._build_guidelines_section(GUIDELINES)
        full_tokens = len(all_guidelines_text) // 4  # Rough estimate

        # Focused prompt with only relevant guidelines
        guidelines = self.retrieve_guidelines(relevant_codes, include_related)
        focused_text = self._build_guidelines_section(guidelines)
        focused_tokens = len(focused_text) // 4

        savings = full_tokens - focused_tokens
        savings_pct = (savings / full_tokens * 100) if full_tokens > 0 else 0

        return {
            'full_prompt_tokens': full_tokens,
            'focused_prompt_tokens': focused_tokens,
            'savings_tokens': savings,
            'savings_percent': savings_pct,
            'guidelines_included': len(guidelines),
            'guidelines_excluded': 13 - len(guidelines)
        }


def demo():
    """Demo the guideline retriever"""
    retriever = GuidelineRetriever()

    # Example: Document about financial and alcohol issues
    relevant = ['F', 'G']

    print("=" * 70)
    print("GUIDELINE RAG RETRIEVAL DEMO")
    print("=" * 70)

    print(f"\nRelevant guidelines identified: {relevant}")

    # Calculate savings
    savings = retriever.calculate_token_savings(relevant, include_related=True)

    print(f"\nToken Usage Comparison:")
    print(f"  Full prompt (all 13 guidelines): ~{savings['full_prompt_tokens']:,} tokens")
    print(f"  Focused prompt ({savings['guidelines_included']} guidelines): ~{savings['focused_prompt_tokens']:,} tokens")
    print(f"  Savings: ~{savings['savings_tokens']:,} tokens ({savings['savings_percent']:.1f}%)")

    # Build focused prompt
    sample_doc = "Subject has $50,000 in delinquent debt and two DUI convictions..."
    system_prompt, included = retriever.build_focused_prompt(
        sample_doc,
        relevant,
        include_related=True
    )

    print(f"\nGuidelines included in focused prompt: {included}")
    print(f"\nFocused system prompt length: {len(system_prompt):,} characters")
    print(f"\nFirst 500 chars of focused prompt:")
    print(system_prompt[:500])


if __name__ == "__main__":
    demo()
