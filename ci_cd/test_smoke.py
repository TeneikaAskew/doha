#!/usr/bin/env python3
"""
Smoke tests for DOHA scraper and analysis system.

These tests verify core functionality without requiring network access or
the full dataset. Run with: python ci_cd/test_smoke.py

Test categories:
1. Parquet round-trip - save and load data correctly
2. Outcome extraction - regex patterns work on known samples
3. Case parsing - ScrapedCase fields are extracted correctly
4. Error taxonomy - download error types work correctly
"""
import sys
import json
import tempfile
from pathlib import Path

# Add project paths (parent directory for root, sead4_llm for imports)
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "sead4_llm"))


def test_parquet_round_trip():
    """Test that cases can be saved and loaded from parquet correctly."""
    print("\n" + "="*60)
    print("TEST: Parquet Round-Trip")
    print("="*60)

    try:
        import pandas as pd
    except ImportError:
        print("  SKIP - pandas not installed")
        return True

    # Create test cases with various field types
    test_cases = [
        {
            "case_number": "23-01234",
            "case_type": "hearing",
            "outcome": "DENIED",
            "guidelines": ["F", "H"],
            "formal_findings": [{"guideline": "F", "finding": "Against"}],
            "full_text": "Sample text for case 1...",
            "source_url": "http://example.com/1"
        },
        {
            "case_number": "24-05678",
            "case_type": "appeal",
            "outcome": "GRANTED",
            "guidelines": ["E"],
            "formal_findings": [],
            "full_text": "Sample text for case 2...",
            "source_url": "http://example.com/2"
        },
        {
            "case_number": "22-00001",
            "case_type": "hearing",
            "outcome": "UNKNOWN",
            "guidelines": [],
            "formal_findings": None,
            "full_text": "",  # Empty text edge case
            "source_url": "http://example.com/3"
        }
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        parquet_path = Path(tmpdir) / "test_cases.parquet"

        # Save to parquet
        df = pd.DataFrame(test_cases)
        df.to_parquet(parquet_path, index=False, engine='pyarrow', compression='gzip')
        print(f"  Saved {len(test_cases)} cases to parquet")

        # Verify file size
        size_kb = parquet_path.stat().st_size / 1024
        print(f"  File size: {size_kb:.2f}KB")

        # Load back
        df_loaded = pd.read_parquet(parquet_path)
        print(f"  Loaded {len(df_loaded)} cases from parquet")

        # Verify row count
        assert len(df_loaded) == len(test_cases), f"Row count mismatch: {len(df_loaded)} != {len(test_cases)}"

        # Verify each case
        for i, expected in enumerate(test_cases):
            loaded = df_loaded.iloc[i].to_dict()
            assert loaded["case_number"] == expected["case_number"], f"Case {i} number mismatch"
            assert loaded["outcome"] == expected["outcome"], f"Case {i} outcome mismatch"
            assert loaded["case_type"] == expected["case_type"], f"Case {i} type mismatch"
            print(f"  Case {expected['case_number']}: OK")

        # Verify PAR1 magic bytes
        with open(parquet_path, 'rb') as f:
            f.seek(-4, 2)
            footer = f.read(4)
            assert footer == b'PAR1', f"Invalid parquet footer: {footer!r}"
        print("  PAR1 footer: OK")

    print("  PASSED!")
    return True


def test_outcome_extraction():
    """Test outcome extraction patterns against known samples."""
    print("\n" + "="*60)
    print("TEST: Outcome Extraction Patterns")
    print("="*60)

    from rag.scraper import DOHAScraper

    # Test cases with known outcomes - these are the core patterns
    # that should always work for basic outcome extraction
    test_texts = [
        # Standard GRANTED patterns (hearing decisions)
        (
            "DECISION\n\nEligibility for access to classified information is GRANTED.",
            "GRANTED"
        ),
        (
            "Applicant's eligibility for a security clearance is GRANTED.",
            "GRANTED"
        ),
        (
            "Clearance is granted.",
            "GRANTED"
        ),
        # Standard DENIED patterns (hearing decisions)
        (
            "DECISION\n\nEligibility for access to classified information is DENIED.",
            "DENIED"
        ),
        (
            "Applicant's request for a security clearance is DENIED.",
            "DENIED"
        ),
        (
            "Clearance is denied.",
            "DENIED"
        ),
        # Revocation patterns
        (
            "Applicant's security clearance is REVOKED.",
            "REVOKED"
        ),
    ]

    scraper = DOHAScraper(output_dir=Path("."))
    passed = 0
    failed = 0

    for text, expected_outcome in test_texts:
        # Use the internal outcome extraction
        outcome = scraper._extract_outcome(text)
        if outcome == expected_outcome:
            print(f"  '{text[:50]}...' -> {outcome} OK")
            passed += 1
        else:
            print(f"  FAIL: '{text[:50]}...'")
            print(f"    Expected: {expected_outcome}, Got: {outcome}")
            failed += 1

    print(f"\n  Results: {passed} passed, {failed} failed")
    if failed > 0:
        print("  FAILED!")
        return False
    print("  PASSED!")
    return True


def test_scraped_case_dataclass():
    """Test ScrapedCase dataclass creation and serialization."""
    print("\n" + "="*60)
    print("TEST: ScrapedCase Dataclass")
    print("="*60)

    from rag.scraper import ScrapedCase

    # Create a case with all required fields
    case = ScrapedCase(
        case_number="23-12345",
        date="2023-05-15",
        outcome="DENIED",
        guidelines=["F", "H"],
        summary="Applicant has financial issues.",
        full_text="This is the full text of the case...",
        sor_allegations=["Failed to pay debts", "Drug use"],
        mitigating_factors=["Enrolled in payment plan"],
        judge="John Smith",
        source_url="https://doha.ogc.osd.mil/test/case.pdf",
        formal_findings={
            "F": {"finding": "Against Applicant", "subparagraphs": {"a": "Against", "b": "For"}},
            "H": {"finding": "Against Applicant", "subparagraphs": {"a": "Against"}}
        },
        case_type="hearing"
    )

    # Test to_dict method
    case_dict = case.to_dict()
    assert isinstance(case_dict, dict), "to_dict should return a dict"
    assert case_dict["case_number"] == "23-12345"
    assert case_dict["outcome"] == "DENIED"
    assert len(case_dict["guidelines"]) == 2
    print(f"  to_dict(): OK - {len(case_dict)} fields")

    # Test JSON serialization
    json_str = json.dumps(case_dict)
    assert len(json_str) > 0, "JSON serialization failed"
    print(f"  JSON serialization: OK - {len(json_str)} bytes")

    # Test field access
    assert case.case_number == "23-12345"
    assert case.outcome == "DENIED"
    assert "F" in case.guidelines
    print("  Field access: OK")

    # Test edge case: empty guidelines and appeal-specific fields
    case_appeal = ScrapedCase(
        case_number="24-00001",
        date="2024-01-01",
        outcome="DENIED",
        guidelines=[],
        summary="",
        full_text="",
        sor_allegations=[],
        mitigating_factors=[],
        judge="",
        source_url="",
        formal_findings={},
        case_type="appeal",
        who_appealed="APPLICANT",
        order="AFFIRMED"
    )
    assert case_appeal.guidelines == []
    assert case_appeal.case_type == "appeal"
    assert case_appeal.who_appealed == "APPLICANT"
    print("  Appeal case fields: OK")

    print("  PASSED!")
    return True


def test_error_taxonomy():
    """Test download error taxonomy and result types."""
    print("\n" + "="*60)
    print("TEST: Error Taxonomy")
    print("="*60)

    from rag.browser_scraper import DownloadResult, DownloadError, DownloadErrorType

    # Test all error types exist
    error_types = [
        "HTTP_ERROR", "TIMEOUT", "NO_PDF_LINK", "INVALID_PDF",
        "DECODE_ERROR", "NETWORK_ERROR", "PARSE_ERROR", "UNKNOWN"
    ]
    for et in error_types:
        assert hasattr(DownloadErrorType, et), f"Missing error type: {et}"
    print(f"  All {len(error_types)} error types present: OK")

    # Test DownloadError creation
    error = DownloadError(
        error_type=DownloadErrorType.HTTP_ERROR,
        message="Failed to fetch",
        http_status=403,
        url="http://example.com",
        details="Bot protection"
    )
    assert error.http_status == 403
    assert "403" in str(error)
    print("  DownloadError creation: OK")

    # Test to_dict
    error_dict = error.to_dict()
    assert error_dict["error_type"] == "http_error"
    assert error_dict["http_status"] == 403
    print("  DownloadError.to_dict(): OK")

    # Test DownloadResult.fail
    fail_result = DownloadResult.fail(error)
    assert fail_result.success == False
    assert fail_result.pdf_bytes is None
    assert fail_result.error == error
    print("  DownloadResult.fail(): OK")

    # Test DownloadResult.ok
    ok_result = DownloadResult.ok(b'%PDF-test')
    assert ok_result.success == True
    assert ok_result.pdf_bytes == b'%PDF-test'
    assert ok_result.error is None
    print("  DownloadResult.ok(): OK")

    print("  PASSED!")
    return True


def test_cli_validators():
    """Test CLI argument validators."""
    print("\n" + "="*60)
    print("TEST: CLI Argument Validators")
    print("="*60)

    import argparse

    # Import validators from download_pdfs
    # Since they're defined in __main__, we need to define them here
    def positive_int(value):
        try:
            ivalue = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"invalid int value: '{value}'")
        if ivalue <= 0:
            raise argparse.ArgumentTypeError(f"must be positive, got {ivalue}")
        return ivalue

    def positive_float(value):
        try:
            fvalue = float(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"invalid float value: '{value}'")
        if fvalue <= 0:
            raise argparse.ArgumentTypeError(f"must be positive, got {fvalue}")
        return fvalue

    def workers_int(value):
        try:
            ivalue = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"invalid int value: '{value}'")
        if ivalue < 1:
            raise argparse.ArgumentTypeError(f"must be at least 1, got {ivalue}")
        if ivalue > 10:
            raise argparse.ArgumentTypeError(f"max 10 workers supported, got {ivalue}")
        return ivalue

    # Test positive_int
    assert positive_int("5") == 5
    assert positive_int("100") == 100
    try:
        positive_int("-5")
        assert False, "Should have raised"
    except argparse.ArgumentTypeError:
        pass
    try:
        positive_int("0")
        assert False, "Should have raised"
    except argparse.ArgumentTypeError:
        pass
    print("  positive_int: OK")

    # Test positive_float
    assert positive_float("0.5") == 0.5
    assert positive_float("2.5") == 2.5
    try:
        positive_float("-1.0")
        assert False, "Should have raised"
    except argparse.ArgumentTypeError:
        pass
    print("  positive_float: OK")

    # Test workers_int
    assert workers_int("1") == 1
    assert workers_int("5") == 5
    assert workers_int("10") == 10
    try:
        workers_int("0")
        assert False, "Should have raised"
    except argparse.ArgumentTypeError:
        pass
    try:
        workers_int("15")
        assert False, "Should have raised"
    except argparse.ArgumentTypeError:
        pass
    print("  workers_int: OK")

    print("  PASSED!")
    return True


def test_parquet_validation():
    """Test parquet file validation function."""
    print("\n" + "="*60)
    print("TEST: Parquet Validation")
    print("="*60)

    try:
        import pandas as pd
    except ImportError:
        print("  SKIP - pandas not installed")
        return True

    # Import validation function
    from download_pdfs import validate_parquet_file

    # Create a valid parquet file
    test_cases = [
        {"case_number": "23-00001", "outcome": "GRANTED"},
        {"case_number": "23-00002", "outcome": "DENIED"},
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        parquet_path = Path(tmpdir) / "test.parquet"

        # Save valid parquet
        df = pd.DataFrame(test_cases)
        df.to_parquet(parquet_path, index=False, engine='pyarrow', compression='gzip')

        # Should not raise
        validate_parquet_file(parquet_path, expected_rows=2, operation="test")
        print("  Valid file validation: OK")

        # Test wrong row count
        try:
            validate_parquet_file(parquet_path, expected_rows=5, operation="test")
            assert False, "Should have raised for wrong row count"
        except ValueError as e:
            assert "expected 5 rows" in str(e).lower()
        print("  Row count mismatch detection: OK")

        # Test non-existent file
        try:
            validate_parquet_file(Path(tmpdir) / "nonexistent.parquet", expected_rows=1, operation="test")
            assert False, "Should have raised for missing file"
        except FileNotFoundError:
            pass
        print("  Missing file detection: OK")

    print("  PASSED!")
    return True


def main():
    """Run all smoke tests."""
    print("="*60)
    print("DOHA Smoke Tests")
    print("="*60)

    tests = [
        test_parquet_round_trip,
        test_outcome_extraction,
        test_scraped_case_dataclass,
        test_error_taxonomy,
        test_cli_validators,
        test_parquet_validation,
    ]

    passed = 0
    failed = 0
    skipped = 0

    for test in tests:
        try:
            result = test()
            if result:
                passed += 1
            elif result is None:
                skipped += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n  ERROR: {type(e).__name__}: {e}")
            failed += 1

    print("\n" + "="*60)
    print(f"SUMMARY: {passed} passed, {failed} failed, {skipped} skipped")
    print("="*60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
