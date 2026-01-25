#!/usr/bin/env python3
"""
Comprehensive Regex Pattern Tests for DOHA Scraper

This file tests EVERY regex pattern in DOHAScraper.OUTCOME_PATTERNS and
DOHAScraper.GUIDELINE_PATTERNS with documented test cases.

Each pattern is tested with:
- What it's designed to match (documentation)
- Example text that should match
- Verification that the pattern works correctly

Run with: python ci_cd/test_regex_patterns.py
"""
import sys
import re
from pathlib import Path

# Add project paths (parent directory for root, sead4_llm for imports)
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "sead4_llm"))


# =============================================================================
# OUTCOME PATTERN DOCUMENTATION AND TEST CASES
# =============================================================================
# Each entry: (pattern_index, pattern_description, test_text, should_match)

GRANTED_PATTERN_TESTS = [
    # Pattern 0: r'clearance\s+is\s+granted'
    # Matches: Standard "clearance is granted" phrase
    (0, "Standard clearance granted", "Applicant's security clearance is granted.", True),
    (0, "Clearance granted with extra words", "The clearance is granted to the applicant.", True),

    # Pattern 1: r'eligibility\s+for\s+access\s+to\s+classified\s+information\s+is\s+granted'
    # Matches: Full formal phrase for classified information access
    (1, "Full classified access phrase", "Eligibility for access to classified information is granted.", True),

    # Pattern 2: r'eligibility\s+[^.]{0,50}\s+is\s+granted'
    # Matches: "eligibility ... is granted" with up to 50 chars between
    # Note: This pattern requires at least one char between "eligibility" and "is"
    (2, "Eligibility with middle text", "Eligibility for a security clearance is granted.", True),
    (2, "Eligibility for access granted", "Eligibility for access is granted.", True),

    # Pattern 3: r'access\s+to\s+classified\s+information\s+is\s+granted'
    # Matches: Access to classified information granted
    (3, "Access to classified granted", "Access to classified information is granted.", True),

    # Pattern 4: r'favorable\s+determination'
    # Matches: "favorable determination" anywhere
    (4, "Favorable determination", "I make a favorable determination for Applicant.", True),

    # Pattern 5: r'security\s+clearance\s+is\s+granted'
    # Matches: "security clearance is granted"
    (5, "Security clearance granted", "Applicant's security clearance is granted.", True),

    # Pattern 6: r'eligibility\s+is\s+granted'
    # Matches: Direct "eligibility is granted"
    (6, "Direct eligibility granted", "Eligibility is granted.", True),

    # Pattern 7: r'eligibility\s+granted'
    # Matches: "eligibility granted" without "is"
    (7, "Eligibility granted no is", "Applicant eligibility granted.", True),

    # Pattern 8: r'clearance\s+granted'
    # Matches: "clearance granted" without "is"
    (8, "Clearance granted no is", "Security clearance granted.", True),

    # Pattern 9: r'clearance\s+eligibility\s+is\s+granted'
    # Matches: "clearance eligibility is granted"
    (9, "Clearance eligibility granted", "Clearance eligibility is granted.", True),

    # Pattern 10: r'cac\s+eligibility\s+is\s+granted'
    # Matches: Common Access Card eligibility
    (10, "CAC eligibility granted", "CAC eligibility is granted.", True),

    # Pattern 11: r'trustworthiness\s+(?:designation\s+)?(?:is\s+)?granted'
    # Matches: Trustworthiness designation granted (ADP cases)
    (11, "Trustworthiness granted", "Trustworthiness is granted.", True),
    (11, "Trustworthiness designation granted", "Trustworthiness designation is granted.", True),
    (11, "Trustworthiness granted no is", "Trustworthiness granted.", True),

    # Pattern 12: r'adp.{0,20}eligibility\s+(?:is\s+)?granted'
    # Matches: ADP eligibility granted
    (12, "ADP eligibility granted", "ADP eligibility is granted.", True),
    (12, "ADP I/II/III eligibility", "ADP-I/II/III eligibility is granted.", True),

    # Pattern 13: r'eligibility\s+for\s+(?:a\s+)?(?:adp|public\s+trust)\s+position\s+(?:is\s+)?granted'
    # Matches: Eligibility for ADP/public trust position
    (13, "Public trust position granted", "Eligibility for a public trust position is granted.", True),
    (13, "ADP position granted", "Eligibility for ADP position is granted.", True),

    # Pattern 14: r'(?:adp|public\s+trust)\s+position\s+(?:is\s+)?granted'
    # Matches: ADP/public trust position granted directly
    (14, "Public trust position direct", "Public trust position is granted.", True),

    # Pattern 15: r'request\s+for\s+(?:a\s+)?position\s+of\s+trust\s+is\s+granted'
    # Matches: Request for position of trust granted
    (15, "Position of trust request granted", "Request for a position of trust is granted.", True),

    # Pattern 16: r'eligibility\s+for\s+access\s+to\s+sensitive\s+information.*?(?:is\s+)?granted'
    # Matches: Eligibility for access to sensitive information granted
    (16, "Sensitive information access granted", "Eligibility for access to sensitive information is granted.", True),

    # Pattern 17: r'eligibility\s+for\s+(?:assignment\s+to\s+)?sensitive\s+(?:positions?|duties)\s+is\s+granted'
    # Matches: Eligibility for sensitive positions/duties
    (17, "Sensitive positions eligibility", "Eligibility for sensitive positions is granted.", True),
    (17, "Assignment to sensitive duties", "Eligibility for assignment to sensitive duties is granted.", True),

    # Pattern 18: r'assignment\s+to\s+sensitive\s+(?:positions?|duties)\s+is\s+granted'
    # Matches: Assignment to sensitive positions/duties granted
    (18, "Assignment to sensitive positions", "Assignment to sensitive positions is granted.", True),

    # Pattern 19: r'it\s+is\s+clearly\s+consistent[\s\d]*with\s+the\s+national\s+interests?\s+to\s+grant'
    # Matches: "It is clearly consistent with the national interest to grant"
    (19, "Clearly consistent to grant", "It is clearly consistent with the national interest to grant Applicant eligibility.", True),
    (19, "With page number interruption", "It is clearly consistent\n5\nwith the national interest to grant.", True),

    # Pattern 20: r'clearly\s+consistent[\s\d]*with\s+the\s+national\s+interests?\s+to\s+grant'
    # Matches: "clearly consistent with the national interest to grant" (without "it is")
    (20, "Clearly consistent no it is", "I conclude that it would be clearly consistent with the national interest to grant.", True),

    # Pattern 21: r'clearly\s+consistent[\s\d]*with\s+the\s+interests\s+of\s+national\s+security'
    # Matches: "clearly consistent with the interests of national security"
    (21, "Interests of national security", "It is clearly consistent with the interests of national security.", True),

    # Pattern 22: r'clearly\s+consistent[\s\d]*with\s+the\s+security\s+interests'
    # Matches: "clearly consistent with the security interests"
    (22, "Security interests", "It is clearly consistent with the security interests of the United States.", True),

    # Pattern 23: r'clearly\s+consistent[\s\n]*with\s+national\s+security\s+to\s+(?:approve|grant|continue)'
    # Matches: "clearly consistent with national security to approve/grant/continue"
    (23, "With national security to grant", "It is clearly consistent with national security to grant.", True),
    (23, "With national security to continue", "It is clearly consistent with national security to continue.", True),

    # Pattern 24: r'(?:it\s+is\s+)?clearly[\s\n]+consistent[\s\n]+to[\s\n]+grant'
    # Matches: "clearly consistent to grant" (simplified)
    (24, "Simplified clearly consistent", "I conclude it is clearly consistent to grant Applicant's clearance.", True),

    # Pattern 25: r'clearly\s+consistent[\s\n]*with\s+the\s+national\s+interests?\s+to[\s\n]+(?:make|continue)'
    # Matches: "clearly consistent to make/continue" (trustworthiness cases)
    (25, "Clearly consistent to make", "It is clearly consistent with the national interest to make a favorable decision.", True),
    (25, "Clearly consistent to continue", "It is clearly consistent with the national interests to continue.", True),

    # Pattern 26: r'national\s+security\s+eligibility\s+is\s+granted'
    # Matches: "national security eligibility is granted"
    (26, "National security eligibility", "Applicant's national security eligibility is granted.", True),

    # Pattern 27: r'favorable\s+decision\s+(?:is\s+)?affirmed'
    # Matches: Appeal Board affirming a favorable decision
    (27, "Favorable decision affirmed", "The favorable decision is affirmed.", True),
    (27, "Favorable decision affirmed no is", "The favorable decision affirmed.", True),

    # Pattern 28: r'adverse\s+decision\s+(?:is\s+)?reversed'
    # Matches: Appeal Board reversing an adverse decision (denial overturned)
    (28, "Adverse decision reversed", "The adverse decision is reversed.", True),

    # Pattern 29: r'adverse\s+findings\s+are\s+not\s+sustainable'
    # Matches: Appeal Board finding adverse findings unsustainable
    (29, "Adverse findings not sustainable", "The Administrative Judge's adverse findings are not sustainable.", True),
]

DENIED_PATTERN_TESTS = [
    # Pattern 0: r'clearance\s+is\s+denied'
    # Matches: Standard "clearance is denied"
    (0, "Standard clearance denied", "Applicant's security clearance is denied.", True),

    # Pattern 1: r'eligibility\s+for\s+access\s+to\s+classified\s+information\s+is\s+denied'
    # Matches: Full formal phrase for classified information access denied
    (1, "Full classified access denied", "Eligibility for access to classified information is denied.", True),

    # Pattern 2: r'eligibility\s+[^.]{0,50}\s+is\s+denied'
    # Matches: "eligibility ... is denied" with up to 50 chars between
    (2, "Eligibility with middle text denied", "Eligibility for a security clearance is denied.", True),

    # Pattern 3: r'access\s+to\s+classified\s+information\s+is\s+denied'
    # Matches: Access to classified information denied
    (3, "Access to classified denied", "Access to classified information is denied.", True),

    # Pattern 4: r'unfavorable\s+determination'
    # Matches: "unfavorable determination" anywhere
    (4, "Unfavorable determination", "I make an unfavorable determination.", True),

    # Pattern 5: r'security\s+clearance\s+is\s+denied'
    # Matches: "security clearance is denied"
    (5, "Security clearance denied", "Applicant's security clearance is denied.", True),

    # Pattern 6: r'eligibility\s+is\s+denied'
    # Matches: Direct "eligibility is denied"
    (6, "Direct eligibility denied", "Eligibility is denied.", True),

    # Pattern 7: r'eligibility\s+denied'
    # Matches: "eligibility denied" without "is"
    (7, "Eligibility denied no is", "Applicant eligibility denied.", True),

    # Pattern 8: r'clearance\s+denied'
    # Matches: "clearance denied" without "is"
    (8, "Clearance denied no is", "Security clearance denied.", True),

    # Pattern 9: r'clearance\s+eligibility\s+is\s+denied'
    # Matches: "clearance eligibility is denied"
    (9, "Clearance eligibility denied", "Clearance eligibility is denied.", True),

    # Pattern 10: r'cac\s+eligibility\s+is\s+denied'
    # Matches: Common Access Card eligibility denied
    (10, "CAC eligibility denied", "CAC eligibility is denied.", True),

    # Pattern 11: r'trustworthiness\s+(?:designation\s+)?is\s+denied'
    # Matches: Trustworthiness designation denied
    (11, "Trustworthiness denied", "Trustworthiness is denied.", True),
    (11, "Trustworthiness designation denied", "Trustworthiness designation is denied.", True),

    # Pattern 12: r'adp.{0,20}eligibility\s+is\s+denied'
    # Matches: ADP eligibility denied
    (12, "ADP eligibility denied", "ADP eligibility is denied.", True),

    # Pattern 13: r'eligibility\s+for\s+a\s+public\s+trust\s+position\s+is\s+denied'
    # Matches: Eligibility for public trust position denied
    (13, "Public trust position denied", "Eligibility for a public trust position is denied.", True),

    # Pattern 14: r'public\s+trust\s+position\s+is\s+denied'
    # Matches: Public trust position denied directly
    (14, "Public trust position direct denied", "Public trust position is denied.", True),

    # Pattern 15: r'eligibility\s+for\s+(?:assignment\s+to\s+)?sensitive\s+(?:positions?|duties)\s+is\s+denied'
    # Matches: Eligibility for sensitive positions/duties denied
    (15, "Sensitive positions denied", "Eligibility for sensitive positions is denied.", True),

    # Pattern 16: r'assignment\s+to\s+sensitive\s+(?:positions?|duties)\s+is\s+denied'
    # Matches: Assignment to sensitive positions/duties denied
    (16, "Assignment to sensitive positions denied", "Assignment to sensitive positions is denied.", True),

    # Pattern 17: r'it\s+is\s+not\s+clearly\s+consistent[\s\d]*with\s+the\s+national\s+interest'
    # Matches: "It is not clearly consistent with the national interest"
    (17, "Not clearly consistent", "It is not clearly consistent with the national interest to grant.", True),
    (17, "Not clearly consistent with page number", "It is not clearly consistent\n6\nwith the national interest.", True),

    # Pattern 18: r'not\s+clearly\s+consistent[\s\d]*with\s+the\s+national\s+interest'
    # Matches: "not clearly consistent with the national interest" (without "it is")
    (18, "Not clearly consistent no it is", "I conclude that granting is not clearly consistent with the national interest.", True),

    # Pattern 19: r'not\s+clearly\s+consistent[\s\d]*with\s+the\s+interests\s+of\s+national\s+security'
    # Matches: "not clearly consistent with the interests of national security"
    (19, "Not consistent interests of national security", "It is not clearly consistent with the interests of national security.", True),

    # Pattern 20: r'not\s+clearly\s+consistent[\s\d]*with\s+the\s+security\s+interests'
    # Matches: "not clearly consistent with the security interests"
    (20, "Not consistent security interests", "It is not clearly consistent with the security interests.", True),

    # Pattern 21: r'not[\s\n]+clearly\s+consistent\s+with\s+national\s+security'
    # Matches: "not clearly consistent with national security"
    (21, "Not consistent with national security", "It is not clearly consistent with national security.", True),

    # Pattern 22: r'it\s+is\s+clearly\s+not\s+consistent[\s\d]*with\s+the\s+national\s+interest'
    # Matches: "It is clearly not consistent" (alternative phrasing)
    (22, "Clearly not consistent", "It is clearly not consistent with the national interest.", True),

    # Pattern 23: r'clearly\s+not\s+consistent[\s\d]*with\s+the\s+national\s+interest'
    # Matches: "clearly not consistent" without "it is"
    (23, "Clearly not consistent no it is", "I find clearly not consistent with the national interest.", True),

    # Pattern 24: r'national\s+security\s+eligibility\s+is\s+denied'
    # Matches: "national security eligibility is denied"
    (24, "National security eligibility denied", "Applicant's national security eligibility is denied.", True),

    # Pattern 25: r'eligibility\s+for\s+(?:a\s+)?(?:adp|public\s+trust)\s+position\s+(?:is\s+)?denied'
    # Matches: ADP/public trust position eligibility denied
    (25, "ADP position eligibility denied", "Eligibility for a ADP position is denied.", True),
    (25, "Public trust eligibility denied", "Eligibility for public trust position denied.", True),

    # Pattern 26: r'(?:adp|public\s+trust)\s+position\s+(?:is\s+)?denied'
    # Matches: ADP/public trust position denied directly
    (26, "ADP position direct denied", "ADP position is denied.", True),

    # Pattern 27: r'request\s+for\s+(?:a\s+)?position\s+of\s+trust\s+is\s+denied'
    # Matches: Request for position of trust denied
    (27, "Position of trust request denied", "Request for a position of trust is denied.", True),

    # Pattern 28: r'eligibility\s+for\s+access\s+to\s+sensitive\s+information.*?(?:is\s+)?denied'
    # Matches: Eligibility for access to sensitive information denied
    (28, "Sensitive information access denied", "Eligibility for access to sensitive information is denied.", True),

    # Pattern 29: r'clearly\s+consistent[\s\n]*with\s+the\s+national\s+interests?\s+to[\s\n]+deny'
    # Matches: "clearly consistent to deny" (unusual phrasing)
    (29, "Clearly consistent to deny", "It is clearly consistent with the national interest to deny.", True),

    # Pattern 30: r'adverse\s+decision\s+(?:is\s+)?affirmed'
    # Matches: Appeal Board affirming an adverse decision (denial upheld)
    (30, "Adverse decision affirmed", "The adverse decision is affirmed.", True),

    # Pattern 31: r'favorable\s+decision\s+(?:is\s+)?reversed'
    # Matches: Appeal Board reversing a favorable decision (grant overturned)
    (31, "Favorable decision reversed", "The favorable decision is reversed.", True),

    # Pattern 32: r'favorable\s+(?:security\s+)?(?:clearance\s+)?determination\s+cannot\s+be\s+sustained'
    # Matches: Favorable determination cannot be sustained
    (32, "Favorable determination not sustainable", "The favorable security clearance determination cannot be sustained.", True),

    # Pattern 33: r'decision\s+(?:is\s+)?not\s+sustainable[^.]*reversed'
    # Matches: Decision not sustainable and reversed
    (33, "Decision not sustainable reversed", "The decision is not sustainable and is reversed.", True),

    # Pattern 34: r'record\s+(?:evidence\s+)?(?:is\s+)?not\s+sufficient\s+to\s+mitigate'
    # Matches: Record evidence not sufficient to mitigate
    (34, "Record not sufficient to mitigate", "The record evidence is not sufficient to mitigate.", True),

    # Pattern 35: r'runs\s+contrary\s+to\s+the\s+(?:weight\s+of\s+the\s+)?record\s+evidence[^.]*not\s+sustainable'
    # Matches: Runs contrary to record evidence, not sustainable
    (35, "Runs contrary to record evidence", "The decision runs contrary to the weight of the record evidence and is not sustainable.", True),
]

REVOKED_PATTERN_TESTS = [
    # Pattern 0: r'clearance\s+is\s+revoked'
    # Matches: "clearance is revoked"
    (0, "Clearance revoked", "Applicant's security clearance is revoked.", True),

    # Pattern 1: r'eligibility\s+[^.]{0,50}\s+is\s+revoked'
    # Matches: "eligibility ... is revoked"
    (1, "Eligibility revoked", "Eligibility for a security clearance is revoked.", True),

    # Pattern 2: r'access\s+to\s+classified\s+information\s+is\s+revoked'
    # Matches: Access to classified information revoked
    (2, "Access revoked", "Access to classified information is revoked.", True),

    # Pattern 3: r'security\s+clearance\s+is\s+revoked'
    # Matches: "security clearance is revoked"
    (3, "Security clearance revoked", "Applicant's security clearance is revoked.", True),

    # Pattern 4: r'eligibility\s+revoked'
    # Matches: "eligibility revoked" without "is"
    (4, "Eligibility revoked no is", "Eligibility revoked.", True),

    # Pattern 5: r'clearance\s+revoked'
    # Matches: "clearance revoked" without "is"
    (5, "Clearance revoked no is", "Security clearance revoked.", True),
]

REMANDED_PATTERN_TESTS = [
    # Pattern 0: r'case\s+(?:is\s+)?remanded'
    # Matches: "case is remanded" or "case remanded"
    (0, "Case remanded", "The case is remanded.", True),
    (0, "Case remanded no is", "The case remanded to the Administrative Judge.", True),

    # Pattern 1: r'decision\s+(?:is\s+)?remanded'
    # Matches: "decision is remanded" or "decision remanded"
    (1, "Decision remanded", "The decision is remanded.", True),

    # Pattern 2: r'remanded\s+to\s+the\s+administrative\s+judge'
    # Matches: Remanded to the Administrative Judge
    (2, "Remanded to AJ", "The case is remanded to the Administrative Judge.", True),

    # Pattern 3: r'remanded\s+for\s+(?:further|additional)\s+proceedings'
    # Matches: Remanded for further/additional proceedings
    (3, "Remanded for further proceedings", "The case is remanded for further proceedings.", True),
    (3, "Remanded for additional proceedings", "The case is remanded for additional proceedings.", True),
]

# =============================================================================
# GUIDELINE PATTERN DOCUMENTATION AND TEST CASES
# =============================================================================

GUIDELINE_PATTERN_TESTS = {
    'A': [
        # Pattern: r'Guideline\s*A|Allegiance|AG\s*¶\s*2'
        ("Guideline A direct", "Guideline A (Allegiance to the United States)", True),
        ("Guideline A spaced", "Guideline  A", True),
        ("Allegiance keyword", "Allegiance to the United States", True),
        ("AG paragraph 2", "AG ¶ 2(a)", True),
    ],
    'B': [
        # Pattern: r'Guideline\s*B|Foreign\s*Influence|AG\s*¶\s*6|AG\s*¶\s*7'
        ("Guideline B direct", "Guideline B (Foreign Influence)", True),
        ("Foreign Influence keyword", "Foreign Influence concerns", True),
        ("AG paragraph 6", "AG ¶ 6", True),
        ("AG paragraph 7", "AG ¶ 7(a)", True),
    ],
    'C': [
        # Pattern: r'Guideline\s*C|Foreign\s*Preference|AG\s*¶\s*9|AG\s*¶\s*10'
        ("Guideline C direct", "Guideline C (Foreign Preference)", True),
        ("Foreign Preference keyword", "Foreign Preference issues", True),
        ("AG paragraph 9", "AG ¶ 9", True),
        ("AG paragraph 10", "AG ¶ 10(a)", True),
    ],
    'D': [
        # Pattern: r'Guideline\s*D|Sexual\s*Behavior|AG\s*¶\s*12|AG\s*¶\s*13'
        ("Guideline D direct", "Guideline D (Sexual Behavior)", True),
        ("Sexual Behavior keyword", "Sexual Behavior concerns", True),
        ("AG paragraph 12", "AG ¶ 12", True),
        ("AG paragraph 13", "AG ¶ 13(a)", True),
    ],
    'E': [
        # Pattern: r'Guideline\s*E|Personal\s*Conduct|AG\s*¶\s*15|AG\s*¶\s*16'
        ("Guideline E direct", "Guideline E (Personal Conduct)", True),
        ("Personal Conduct keyword", "Personal Conduct violations", True),
        ("AG paragraph 15", "AG ¶ 15", True),
        ("AG paragraph 16", "AG ¶ 16(a)", True),
    ],
    'F': [
        # Pattern: r'Guideline\s*F|Financial\s*Considerations|AG\s*¶\s*18|AG\s*¶\s*19|AG\s*¶\s*20'
        ("Guideline F direct", "Guideline F (Financial Considerations)", True),
        ("Financial Considerations keyword", "Financial Considerations apply", True),
        ("AG paragraph 18", "AG ¶ 18", True),
        ("AG paragraph 19", "AG ¶ 19(a)", True),
        ("AG paragraph 20", "AG ¶ 20(b)", True),
    ],
    'G': [
        # Pattern: r'Guideline\s*G|Alcohol\s*Consumption|AG\s*¶\s*21|AG\s*¶\s*22'
        ("Guideline G direct", "Guideline G (Alcohol Consumption)", True),
        ("Alcohol Consumption keyword", "Alcohol Consumption issues", True),
        ("AG paragraph 21", "AG ¶ 21", True),
        ("AG paragraph 22", "AG ¶ 22(a)", True),
    ],
    'H': [
        # Pattern: r'Guideline\s*H|Drug\s*Involvement|AG\s*¶\s*24|AG\s*¶\s*25|AG\s*¶\s*26'
        ("Guideline H direct", "Guideline H (Drug Involvement)", True),
        ("Drug Involvement keyword", "Drug Involvement concerns", True),
        ("AG paragraph 24", "AG ¶ 24", True),
        ("AG paragraph 25", "AG ¶ 25(a)", True),
        ("AG paragraph 26", "AG ¶ 26(b)", True),
    ],
    'I': [
        # Pattern: r'Guideline\s*I|Psychological\s*Conditions|AG\s*¶\s*27|AG\s*¶\s*28'
        ("Guideline I direct", "Guideline I (Psychological Conditions)", True),
        ("Psychological Conditions keyword", "Psychological Conditions evaluation", True),
        ("AG paragraph 27", "AG ¶ 27", True),
        ("AG paragraph 28", "AG ¶ 28(a)", True),
    ],
    'J': [
        # Pattern: r'Guideline\s*J|Criminal\s*Conduct|AG\s*¶\s*30|AG\s*¶\s*31|AG\s*¶\s*32'
        ("Guideline J direct", "Guideline J (Criminal Conduct)", True),
        ("Criminal Conduct keyword", "Criminal Conduct history", True),
        ("AG paragraph 30", "AG ¶ 30", True),
        ("AG paragraph 31", "AG ¶ 31(a)", True),
        ("AG paragraph 32", "AG ¶ 32(a)", True),
    ],
    'K': [
        # Pattern: r'Guideline\s*K|Handling\s*Protected\s*Information|AG\s*¶\s*33|AG\s*¶\s*34'
        ("Guideline K direct", "Guideline K (Handling Protected Information)", True),
        ("Handling Protected Information keyword", "Handling Protected Information violations", True),
        ("AG paragraph 33", "AG ¶ 33", True),
        ("AG paragraph 34", "AG ¶ 34(a)", True),
    ],
    'L': [
        # Pattern: r'Guideline\s*L|Outside\s*Activities|AG\s*¶\s*36|AG\s*¶\s*37'
        ("Guideline L direct", "Guideline L (Outside Activities)", True),
        ("Outside Activities keyword", "Outside Activities concerns", True),
        ("AG paragraph 36", "AG ¶ 36", True),
        ("AG paragraph 37", "AG ¶ 37(a)", True),
    ],
    'M': [
        # Pattern: r'Guideline\s*M|Use\s*of\s*Information\s*Technology|AG\s*¶\s*39|AG\s*¶\s*40'
        ("Guideline M direct", "Guideline M (Use of Information Technology)", True),
        ("Use of Information Technology keyword", "Use of Information Technology misuse", True),
        ("AG paragraph 39", "AG ¶ 39", True),
        ("AG paragraph 40", "AG ¶ 40(a)", True),
    ],
}


class PatternTestRunner:
    """Test runner for regex pattern validation."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def test_pattern(self, pattern: str, text: str, should_match: bool, description: str) -> bool:
        """Test a single pattern against text."""
        try:
            match = re.search(pattern, text, re.IGNORECASE)
            matched = match is not None

            if matched == should_match:
                self.passed += 1
                return True
            else:
                self.failed += 1
                expected = "match" if should_match else "no match"
                actual = "matched" if matched else "no match"
                self.errors.append(f"  {description}: Expected {expected}, got {actual}")
                self.errors.append(f"    Pattern: {pattern}")
                self.errors.append(f"    Text: {text[:80]}...")
                return False
        except re.error as e:
            self.failed += 1
            self.errors.append(f"  {description}: Regex error: {e}")
            return False

    def report(self):
        """Print error report."""
        if self.errors:
            for err in self.errors:
                print(err)
            self.errors = []


def test_outcome_patterns():
    """Test all OUTCOME_PATTERNS from DOHAScraper."""
    print("\n" + "="*70)
    print("COMPREHENSIVE OUTCOME PATTERN TESTS")
    print("="*70)

    from rag.scraper import DOHAScraper

    runner = PatternTestRunner()
    total_patterns = 0

    # Test GRANTED patterns
    print("\n--- GRANTED Patterns ---")
    patterns = DOHAScraper.OUTCOME_PATTERNS['GRANTED']
    print(f"Testing {len(patterns)} patterns with {len(GRANTED_PATTERN_TESTS)} test cases")

    for pattern_idx, description, text, should_match in GRANTED_PATTERN_TESTS:
        if pattern_idx < len(patterns):
            pattern = patterns[pattern_idx]
            result = runner.test_pattern(pattern, text, should_match, description)
            status = "OK" if result else "FAIL"
            if result:
                print(f"  [{pattern_idx:2d}] {description}: {status}")

    total_patterns += len(patterns)
    runner.report()

    # Test DENIED patterns
    print("\n--- DENIED Patterns ---")
    patterns = DOHAScraper.OUTCOME_PATTERNS['DENIED']
    print(f"Testing {len(patterns)} patterns with {len(DENIED_PATTERN_TESTS)} test cases")

    for pattern_idx, description, text, should_match in DENIED_PATTERN_TESTS:
        if pattern_idx < len(patterns):
            pattern = patterns[pattern_idx]
            result = runner.test_pattern(pattern, text, should_match, description)
            status = "OK" if result else "FAIL"
            if result:
                print(f"  [{pattern_idx:2d}] {description}: {status}")

    total_patterns += len(patterns)
    runner.report()

    # Test REVOKED patterns
    print("\n--- REVOKED Patterns ---")
    patterns = DOHAScraper.OUTCOME_PATTERNS['REVOKED']
    print(f"Testing {len(patterns)} patterns with {len(REVOKED_PATTERN_TESTS)} test cases")

    for pattern_idx, description, text, should_match in REVOKED_PATTERN_TESTS:
        if pattern_idx < len(patterns):
            pattern = patterns[pattern_idx]
            result = runner.test_pattern(pattern, text, should_match, description)
            status = "OK" if result else "FAIL"
            if result:
                print(f"  [{pattern_idx:2d}] {description}: {status}")

    total_patterns += len(patterns)
    runner.report()

    # Test REMANDED patterns
    print("\n--- REMANDED Patterns ---")
    patterns = DOHAScraper.OUTCOME_PATTERNS['REMANDED']
    print(f"Testing {len(patterns)} patterns with {len(REMANDED_PATTERN_TESTS)} test cases")

    for pattern_idx, description, text, should_match in REMANDED_PATTERN_TESTS:
        if pattern_idx < len(patterns):
            pattern = patterns[pattern_idx]
            result = runner.test_pattern(pattern, text, should_match, description)
            status = "OK" if result else "FAIL"
            if result:
                print(f"  [{pattern_idx:2d}] {description}: {status}")

    total_patterns += len(patterns)
    runner.report()

    print(f"\n  Total outcome patterns: {total_patterns}")
    print(f"  Results: {runner.passed} passed, {runner.failed} failed")

    return runner.failed == 0


def test_guideline_patterns():
    """Test all GUIDELINE_PATTERNS from DOHAScraper."""
    print("\n" + "="*70)
    print("COMPREHENSIVE GUIDELINE PATTERN TESTS")
    print("="*70)

    from rag.scraper import DOHAScraper

    runner = PatternTestRunner()

    for guideline_letter, test_cases in GUIDELINE_PATTERN_TESTS.items():
        print(f"\n--- Guideline {guideline_letter} ---")
        pattern = DOHAScraper.GUIDELINE_PATTERNS[guideline_letter]
        print(f"  Pattern: {pattern}")

        for description, text, should_match in test_cases:
            result = runner.test_pattern(pattern, text, should_match, description)
            status = "OK" if result else "FAIL"
            if result:
                print(f"    {description}: {status}")

        runner.report()

    print(f"\n  Total guideline patterns: {len(GUIDELINE_PATTERN_TESTS)}")
    print(f"  Results: {runner.passed} passed, {runner.failed} failed")

    return runner.failed == 0


def test_pattern_coverage():
    """Verify all patterns have at least one test case."""
    print("\n" + "="*70)
    print("PATTERN COVERAGE VERIFICATION")
    print("="*70)

    from rag.scraper import DOHAScraper

    issues = []

    # Check GRANTED coverage
    granted_tested = set(t[0] for t in GRANTED_PATTERN_TESTS)
    granted_total = len(DOHAScraper.OUTCOME_PATTERNS['GRANTED'])
    missing_granted = set(range(granted_total)) - granted_tested
    if missing_granted:
        issues.append(f"  GRANTED: Missing tests for patterns {sorted(missing_granted)}")
    print(f"  GRANTED: {len(granted_tested)}/{granted_total} patterns tested")

    # Check DENIED coverage
    denied_tested = set(t[0] for t in DENIED_PATTERN_TESTS)
    denied_total = len(DOHAScraper.OUTCOME_PATTERNS['DENIED'])
    missing_denied = set(range(denied_total)) - denied_tested
    if missing_denied:
        issues.append(f"  DENIED: Missing tests for patterns {sorted(missing_denied)}")
    print(f"  DENIED: {len(denied_tested)}/{denied_total} patterns tested")

    # Check REVOKED coverage
    revoked_tested = set(t[0] for t in REVOKED_PATTERN_TESTS)
    revoked_total = len(DOHAScraper.OUTCOME_PATTERNS['REVOKED'])
    missing_revoked = set(range(revoked_total)) - revoked_tested
    if missing_revoked:
        issues.append(f"  REVOKED: Missing tests for patterns {sorted(missing_revoked)}")
    print(f"  REVOKED: {len(revoked_tested)}/{revoked_total} patterns tested")

    # Check REMANDED coverage
    remanded_tested = set(t[0] for t in REMANDED_PATTERN_TESTS)
    remanded_total = len(DOHAScraper.OUTCOME_PATTERNS['REMANDED'])
    missing_remanded = set(range(remanded_total)) - remanded_tested
    if missing_remanded:
        issues.append(f"  REMANDED: Missing tests for patterns {sorted(missing_remanded)}")
    print(f"  REMANDED: {len(remanded_tested)}/{remanded_total} patterns tested")

    # Check GUIDELINE coverage
    guideline_letters = set(GUIDELINE_PATTERN_TESTS.keys())
    expected_letters = set(DOHAScraper.GUIDELINE_PATTERNS.keys())
    missing_guidelines = expected_letters - guideline_letters
    if missing_guidelines:
        issues.append(f"  GUIDELINES: Missing tests for {sorted(missing_guidelines)}")
    print(f"  GUIDELINES: {len(guideline_letters)}/{len(expected_letters)} guidelines tested")

    if issues:
        print("\n  Coverage Issues:")
        for issue in issues:
            print(issue)
        return False

    print("\n  All patterns have test coverage!")
    return True


def main():
    """Run all regex pattern tests."""
    print("="*70)
    print("DOHA Regex Pattern Tests")
    print("="*70)
    print("Testing every regex pattern in DOHAScraper with documented test cases.")

    tests = [
        ("Outcome Patterns", test_outcome_patterns),
        ("Guideline Patterns", test_guideline_patterns),
        ("Pattern Coverage", test_pattern_coverage),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            result = test_func()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n  ERROR in {name}: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "="*70)
    print(f"REGEX PATTERN TEST SUMMARY: {passed} passed, {failed} failed")
    print("="*70)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
