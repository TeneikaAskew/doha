#!/usr/bin/env python3
"""
Test script for DOE OHA scraper

Tests the parsing methods with sample DOE case text.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Mock loguru before importing doe_scraper
sys.modules['loguru'] = MagicMock()

sys.path.insert(0, str(Path(__file__).parent / "sead4_llm"))

# Test imports first
print("=" * 60)
print("Testing DOE Scraper")
print("=" * 60)

print("\n1. Testing imports...")
try:
    from rag.doe_scraper import (
        DOECase, DOECaseLink, DOEBrowserScraper,
        HAS_PLAYWRIGHT, HAS_BS4, HAS_REQUESTS
    )
    print("   [OK] Core imports successful")
except ImportError as e:
    print(f"   [FAIL] Import error: {e}")
    sys.exit(1)

print(f"   - Playwright available: {HAS_PLAYWRIGHT}")
print(f"   - BeautifulSoup available: {HAS_BS4}")
print(f"   - Requests available: {HAS_REQUESTS}")

# Sample DOE case text for testing
SAMPLE_DOE_CASE_TEXT = """
DEPARTMENT OF ENERGY
OFFICE OF HEARINGS AND APPEALS

Personnel Security Hearing

Case Number: PSH-25-0181                                    January 10, 2026

In the Matter of: PERSONNEL SECURITY HEARING

APPEARANCES:
For the Individual: Pro Se
For DOE: Jane Smith, Esq.

Hearing Officer: Robert M. Johnson

I. BACKGROUND

The Individual is employed by a DOE contractor and holds an access authorization
(security clearance) granted under 10 C.F.R. Part 710. In October 2025, the Local
Security Office (LSO) sent the Individual a letter notifying him of information that
created a substantial doubt as to his eligibility for access authorization.

NOTIFICATION LETTER

The Notification Letter cited the following security concerns under Criterion G
(Alcohol Consumption) and Criterion I (Psychological Conditions):

1. The Individual was arrested for Driving Under the Influence (DUI) on March 15, 2024.
   His blood alcohol content was measured at 0.15%.

2. The Individual has a history of alcohol-related incidents dating back to 2019.

3. A DOE psychologist diagnosed the Individual with Alcohol Use Disorder, moderate,
   and recommended treatment.

II. FINDINGS OF FACT

The Individual is a 45-year-old engineer who has worked for a DOE contractor for
15 years. He has held a Q clearance since 2010. The Individual admits to the March
2024 DUI arrest and acknowledges that he has struggled with alcohol consumption.

The Individual testified that following his arrest, he immediately enrolled in an
outpatient alcohol treatment program. He completed 16 weeks of counseling and has
been attending Alcoholics Anonymous meetings three times per week since April 2024.

The Individual's supervisor testified that the Individual is an excellent employee
with no work-related performance issues. The supervisor was unaware of the
Individual's alcohol issues until the DUI arrest.

A DOE psychiatrist who evaluated the Individual in November 2025 testified that the
Individual has shown significant progress in his recovery. The psychiatrist noted
that the Individual has been sober for 10 months and has demonstrated commitment to
his treatment program.

III. ANALYSIS

Criterion G concerns arise when an individual's alcohol consumption raises questions
about his judgment, reliability, or trustworthiness. The Individual's DUI arrest and
history of alcohol-related incidents clearly raise such concerns.

However, the Individual has presented substantial evidence of mitigation. Mitigating
Condition 1 applies because the Individual has acknowledged his alcohol problem and
taken concrete steps to address it. He completed an outpatient treatment program,
maintains regular AA attendance, and has been sober for 10 months.

Mitigating Condition 2 also applies because the Individual has established a pattern
of responsible behavior following his DUI arrest. His supervisor's testimony confirms
that the Individual continues to perform his duties reliably.

Regarding Criterion I, the DOE psychiatrist's testimony establishes that the
Individual's Alcohol Use Disorder is in sustained remission. The psychiatrist
provided a favorable prognosis, noting that the Individual has developed effective
coping strategies and has a strong support system.

IV. CONCLUSION

After carefully considering all the evidence, I find that the Individual has
adequately mitigated the security concerns raised under Criteria G and I. The
Individual has demonstrated genuine rehabilitation and a commitment to sobriety.

OPINION OF THE HEARING OFFICER

It is my opinion that the Individual's access authorization should be restored.

/s/ Robert M. Johnson
Hearing Officer
Office of Hearings and Appeals
January 10, 2026
"""

# Test with unfavorable case
SAMPLE_DENIAL_CASE = """
DEPARTMENT OF ENERGY
OFFICE OF HEARINGS AND APPEALS

Case Number: PSH-25-0099                                    December 5, 2025

Personnel Security Hearing

Hearing Officer: Mary L. Williams

NOTIFICATION LETTER

The LSO cited concerns under Criterion F (Financial Considerations):

1. The Individual has over $85,000 in delinquent debts.
2. The Individual filed for bankruptcy in 2022 but failed to complete the process.
3. The Individual has multiple judgments entered against him for unpaid debts.

II. FINDINGS OF FACT

The Individual works as a technician at a DOE facility. He has accumulated
significant debt over the past five years due to medical expenses and poor
financial decisions.

The Individual failed to provide documentary evidence of any debt repayment plan.
He did not demonstrate that he has taken steps to resolve his financial issues.

III. ANALYSIS

The Individual's substantial delinquent debt raises serious concerns under Criterion F.
Financial problems can create vulnerability to coercion and indicate poor judgment.

The Individual has not presented sufficient mitigating evidence. He has not
established a track record of debt repayment or shown that his financial situation
is under control.

IV. CONCLUSION

The Individual has failed to mitigate the Criterion F security concerns.

It is therefore my opinion that the Individual's access authorization should not
be restored.

/s/ Mary L. Williams
Hearing Officer
December 5, 2025
"""


def test_parsing():
    """Test the parsing methods"""
    print("\n2. Testing parsing methods...")

    # Create a scraper instance without browser (just for parsing)
    # We'll test the parsing methods directly

    class MockScraper:
        """Mock scraper to test parsing without browser"""
        GUIDELINE_PATTERNS = DOEBrowserScraper.GUIDELINE_PATTERNS

        def __init__(self):
            pass

    # Import the methods we need to test
    scraper = DOEBrowserScraper.__new__(DOEBrowserScraper)
    scraper.GUIDELINE_PATTERNS = DOEBrowserScraper.GUIDELINE_PATTERNS

    # Test _extract_date
    print("\n   Testing _extract_date...")
    date = scraper._extract_date(SAMPLE_DOE_CASE_TEXT)
    print(f"   - Extracted date: {date}")
    assert date != "Unknown", f"Date extraction failed, got: {date}"
    assert "2026" in date or "January" in date, f"Expected date with 2026, got: {date}"
    print("   [OK] Date extraction passed")

    # Test _extract_outcome (favorable case)
    print("\n   Testing _extract_outcome (favorable case)...")
    outcome = scraper._extract_outcome(SAMPLE_DOE_CASE_TEXT)
    print(f"   - Extracted outcome: {outcome}")
    assert outcome == "GRANTED", f"Expected GRANTED, got: {outcome}"
    print("   [OK] Outcome extraction (favorable) passed")

    # Test _extract_outcome (unfavorable case)
    print("\n   Testing _extract_outcome (unfavorable case)...")
    outcome_denied = scraper._extract_outcome(SAMPLE_DENIAL_CASE)
    print(f"   - Extracted outcome: {outcome_denied}")
    assert outcome_denied == "DENIED", f"Expected DENIED, got: {outcome_denied}"
    print("   [OK] Outcome extraction (unfavorable) passed")

    # Test _extract_guidelines
    print("\n   Testing _extract_guidelines...")
    guidelines = scraper._extract_guidelines(SAMPLE_DOE_CASE_TEXT)
    print(f"   - Extracted guidelines: {guidelines}")
    assert "G" in guidelines, f"Expected G (Alcohol) in guidelines, got: {guidelines}"
    assert "I" in guidelines, f"Expected I (Psychological) in guidelines, got: {guidelines}"
    print("   [OK] Guidelines extraction passed")

    # Test _extract_guidelines (denial case)
    guidelines_denied = scraper._extract_guidelines(SAMPLE_DENIAL_CASE)
    print(f"   - Denial case guidelines: {guidelines_denied}")
    assert "F" in guidelines_denied, f"Expected F (Financial) in guidelines, got: {guidelines_denied}"
    print("   [OK] Guidelines extraction (denial case) passed")

    # Test _extract_judge
    print("\n   Testing _extract_judge...")
    judge = scraper._extract_judge(SAMPLE_DOE_CASE_TEXT)
    print(f"   - Extracted judge: {judge}")
    assert judge != "Unknown", f"Judge extraction failed, got: {judge}"
    assert "Johnson" in judge or "Robert" in judge, f"Expected Robert M. Johnson, got: {judge}"
    print("   [OK] Judge extraction passed")

    # Test _extract_judge (denial case)
    judge_denied = scraper._extract_judge(SAMPLE_DENIAL_CASE)
    print(f"   - Denial case judge: {judge_denied}")
    assert "Williams" in judge_denied or "Mary" in judge_denied, f"Expected Mary L. Williams, got: {judge_denied}"
    print("   [OK] Judge extraction (denial case) passed")

    # Test _extract_sor_allegations
    print("\n   Testing _extract_sor_allegations...")
    allegations = scraper._extract_sor_allegations(SAMPLE_DOE_CASE_TEXT)
    print(f"   - Extracted allegations count: {len(allegations)}")
    for i, a in enumerate(allegations[:3], 1):
        print(f"     {i}. {a[:80]}...")
    print("   [OK] SOR allegations extraction passed")

    # Test _extract_mitigating_factors
    print("\n   Testing _extract_mitigating_factors...")
    mitigating = scraper._extract_mitigating_factors(SAMPLE_DOE_CASE_TEXT)
    print(f"   - Extracted mitigating factors count: {len(mitigating)}")
    for i, m in enumerate(mitigating[:3], 1):
        print(f"     {i}. {m[:80]}...")
    print("   [OK] Mitigating factors extraction passed")

    # Test _create_summary
    print("\n   Testing _create_summary...")
    summary = scraper._create_summary(SAMPLE_DOE_CASE_TEXT)
    print(f"   - Summary length: {len(summary)} chars")
    print(f"   - Summary starts with: {summary[:100]}...")
    assert len(summary) > 100, f"Summary too short: {len(summary)} chars"
    assert "Findings of Fact" in summary or "engineer" in summary.lower(), f"Summary doesn't contain expected content"
    print("   [OK] Summary extraction passed")

    # Test full parse_case_text
    print("\n   Testing parse_case_text (full parsing)...")
    case = scraper.parse_case_text(
        case_number="PSH-25-0181",
        text=SAMPLE_DOE_CASE_TEXT,
        source_url="https://www.energy.gov/oha/articles/psh-25-0181",
        pdf_url="https://www.energy.gov/sites/default/files/2026-01/PSH-25-0181.pdf"
    )

    print(f"   - Case number: {case.case_number}")
    print(f"   - Date: {case.date}")
    print(f"   - Outcome: {case.outcome}")
    print(f"   - Guidelines: {case.guidelines}")
    print(f"   - Judge: {case.judge}")
    print(f"   - Allegations count: {len(case.sor_allegations)}")
    print(f"   - Mitigating factors count: {len(case.mitigating_factors)}")
    print(f"   - Summary length: {len(case.summary)}")
    print(f"   - Full text length: {len(case.full_text)}")

    assert case.case_number == "PSH-25-0181"
    assert case.outcome == "GRANTED"
    assert "G" in case.guidelines
    assert case.judge != "Unknown"
    print("   [OK] Full parsing passed")

    # Test to_dict
    print("\n   Testing to_dict serialization...")
    case_dict = case.to_dict()
    assert isinstance(case_dict, dict)
    assert "case_number" in case_dict
    assert "outcome" in case_dict
    assert "guidelines" in case_dict
    assert isinstance(case_dict["guidelines"], list)
    print("   [OK] Serialization passed")

    return True


def test_data_classes():
    """Test the data classes"""
    print("\n3. Testing data classes...")

    # Test DOECase
    case = DOECase(
        case_number="PSH-25-0001",
        date="January 1, 2026",
        outcome="GRANTED",
        guidelines=["G", "I"],
        summary="Test summary",
        full_text="Full text here",
        sor_allegations=["Allegation 1"],
        mitigating_factors=["Factor 1"],
        judge="John Doe",
        source_url="https://example.com",
        pdf_url="https://example.com/pdf"
    )

    case_dict = case.to_dict()
    assert case_dict["case_number"] == "PSH-25-0001"
    assert case_dict["outcome"] == "GRANTED"
    print("   [OK] DOECase works correctly")

    # Test DOECaseLink
    link = DOECaseLink(
        case_number="PSH-25-0001",
        date="January 1, 2026",
        title="Test Case",
        summary="G: Alcohol Consumption",
        article_url="https://example.com/article",
        pdf_url="https://example.com/pdf"
    )

    link_dict = link.to_dict()
    assert link_dict["case_number"] == "PSH-25-0001"
    assert link_dict["summary"] == "G: Alcohol Consumption"
    print("   [OK] DOECaseLink works correctly")

    return True


def test_edge_cases():
    """Test edge cases and error handling"""
    print("\n4. Testing edge cases...")

    scraper = DOEBrowserScraper.__new__(DOEBrowserScraper)
    scraper.GUIDELINE_PATTERNS = DOEBrowserScraper.GUIDELINE_PATTERNS

    # Test with empty text
    print("   Testing with empty text...")
    date = scraper._extract_date("")
    assert date == "Unknown", f"Empty text should return Unknown, got: {date}"

    outcome = scraper._extract_outcome("")
    assert outcome == "UNKNOWN", f"Empty text should return UNKNOWN, got: {outcome}"

    guidelines = scraper._extract_guidelines("")
    assert guidelines == [], f"Empty text should return empty list, got: {guidelines}"

    judge = scraper._extract_judge("")
    assert judge == "Unknown", f"Empty text should return Unknown, got: {judge}"
    print("   [OK] Empty text handled correctly")

    # Test with minimal text
    print("   Testing with minimal text...")
    minimal = "This is a short text without much content."
    summary = scraper._create_summary(minimal)
    assert len(summary) > 0, "Should return some summary even for minimal text"
    print("   [OK] Minimal text handled correctly")

    # Test with unusual formatting
    print("   Testing with unusual formatting...")
    unusual = """
    CONCLUSION

    access authorization should be granted

    Hearing Officer
    """
    outcome = scraper._extract_outcome(unusual)
    assert outcome == "GRANTED", f"Should detect GRANTED in unusual format, got: {outcome}"
    print("   [OK] Unusual formatting handled correctly")

    return True


def main():
    """Run all tests"""
    all_passed = True

    try:
        if not test_data_classes():
            all_passed = False
    except Exception as e:
        print(f"   [FAIL] Data classes test failed: {e}")
        all_passed = False

    try:
        if not test_parsing():
            all_passed = False
    except Exception as e:
        print(f"   [FAIL] Parsing test failed: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    try:
        if not test_edge_cases():
            all_passed = False
    except Exception as e:
        print(f"   [FAIL] Edge cases test failed: {e}")
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL TESTS PASSED!")
    else:
        print("SOME TESTS FAILED!")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
