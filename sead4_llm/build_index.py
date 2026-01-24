#!/usr/bin/env python3
"""
DOHA Case Index Builder

Build a precedent index from DOHA case decisions for RAG-augmented analysis.

Usage:
    # Scrape from DOHA website and build index
    python build_index.py --scrape --start-year 2020 --end-year 2024 --output ./doha_index

    # Build index from local case files
    python build_index.py --local-dir ./my_cases --output ./doha_index

    # Build index from pre-extracted cases (Parquet or JSON)
    python build_index.py --from-cases ./cases.parquet --output ./doha_index
"""
import argparse
import json
import sys
from pathlib import Path
from loguru import logger


def scrape_and_build(
    output_path: Path,
    start_year: int,
    end_year: int,
    max_cases: int = None,
    rate_limit: float = 1.0
):
    """Scrape DOHA cases from the web and build index"""
    from rag.scraper import DOHAScraper, ScrapedCase
    from rag.indexer import DOHAIndexer, IndexedCase

    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    # Create scraper
    scraper = DOHAScraper(
        output_dir=output_path / "raw_cases",
        rate_limit=rate_limit
    )

    # Calculate per-year limit if total max specified
    max_per_year = None
    if max_cases:
        years = end_year - start_year + 1
        max_per_year = max(1, max_cases // years)
        logger.info(f"Limiting to ~{max_per_year} cases per year")

    # Scrape cases
    logger.info(f"Scraping DOHA cases from {start_year} to {end_year}...")
    cases = scraper.scrape_years(start_year, end_year, max_per_year)

    if not cases:
        logger.error("No cases scraped. Check your internet connection and the DOHA website availability.")
        return None

    # Convert to indexed cases
    logger.info(f"Converting {len(cases)} cases for indexing...")
    indexed_cases = convert_scraped_to_indexed(cases)

    # Build and save index
    return build_index(indexed_cases, output_path)


def build_from_local(local_dir: Path, output_path: Path):
    """Build index from local case files"""
    from rag.scraper import DOHALocalParser
    from rag.indexer import DOHAIndexer, IndexedCase

    local_dir = Path(local_dir)
    output_path = Path(output_path)

    if not local_dir.exists():
        logger.error(f"Local directory not found: {local_dir}")
        return None

    # Parse local files
    parser = DOHALocalParser()
    logger.info(f"Parsing case files from {local_dir}...")
    cases = parser.parse_directory(local_dir)

    if not cases:
        logger.error("No cases found in the directory")
        return None

    # Convert to indexed cases
    logger.info(f"Converting {len(cases)} cases for indexing...")
    indexed_cases = convert_scraped_to_indexed(cases)

    # Build and save index
    return build_index(indexed_cases, output_path)


def build_from_cases(cases_path: Path, output_path: Path, update: bool = False):
    """Build index from pre-extracted Parquet or JSON file (prefers Parquet)

    Args:
        cases_path: Path to parquet/json file with case data
        output_path: Where to save the index
        update: If True, load existing index and only add new cases
    """
    from rag.indexer import create_index_from_extracted_cases

    cases_path = Path(cases_path)
    output_path = Path(output_path)

    # PREFER parquet files (more consistent, always under size limit)
    parquet_files = list(cases_path.parent.glob(f"{cases_path.stem}*.parquet"))

    if parquet_files:
        logger.info(f"Found {len(parquet_files)} parquet file(s) - using parquet (most consistent format)")
        logger.info(f"Loading from: {', '.join(f.name for f in parquet_files)}")

        try:
            import pandas as pd

            # Load all parquet files and combine
            dfs = [pd.read_parquet(f) for f in sorted(parquet_files)]
            df = pd.concat(dfs, ignore_index=True)
            cases_data = df.to_dict('records')

            # Convert numpy arrays to lists for JSON serialization (recursive)
            import numpy as np

            def convert_to_serializable(obj):
                """Recursively convert numpy arrays and pandas NA to JSON-serializable types"""
                if isinstance(obj, np.ndarray):
                    return [convert_to_serializable(item) for item in obj.tolist()]
                elif isinstance(obj, dict):
                    return {k: convert_to_serializable(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_to_serializable(item) for item in obj]
                elif pd.isna(obj):
                    return None
                else:
                    return obj

            for case in cases_data:
                for key in list(case.keys()):
                    case[key] = convert_to_serializable(case[key])

            # Filter for new cases if updating
            if update and output_path.exists():
                from rag.indexer import DOHAIndexer

                logger.info(f"Update mode: loading existing index from {output_path}")
                existing_indexer = DOHAIndexer(index_path=output_path)
                existing_indexer.load()

                existing_case_numbers = {case.case_number for case in existing_indexer.cases}
                logger.info(f"Existing index has {len(existing_case_numbers)} cases")

                # Filter out cases already in index
                new_cases_data = [
                    case for case in cases_data
                    if case.get('case_number', 'Unknown') not in existing_case_numbers
                ]

                logger.info(f"Found {len(new_cases_data)} new cases to add (skipping {len(cases_data) - len(new_cases_data)} existing)")

                if not new_cases_data:
                    logger.success("No new cases to add - index is up to date")
                    return output_path

                cases_data = new_cases_data

            # Create temporary JSON in memory for the indexer
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
                import json
                json.dump(cases_data, tmp, indent=2)
                tmp_path = Path(tmp.name)

            try:
                if update and output_path.exists():
                    # Load existing index and add new cases
                    from rag.indexer import DOHAIndexer
                    indexer = DOHAIndexer(index_path=output_path)
                    indexer.load()

                    logger.info(f"Adding {len(cases_data)} new cases to existing index")

                    # Parse new cases and add them
                    with open(tmp_path) as f:
                        new_cases_json = json.load(f)

                    from rag.indexer import IndexedCase
                    indexed_cases = []
                    for c in new_cases_json:
                        # Same parsing logic as create_index_from_extracted_cases
                        outcome = c.get('outcome', c.get('overall_decision', 'UNKNOWN'))
                        if outcome not in ['GRANTED', 'DENIED', 'REVOKED', 'REMANDED']:
                            outcome = 'UNKNOWN'

                        guidelines = []
                        if 'guideline_labels' in c:
                            codes = list("ABCDEFGHIJKLM")
                            guidelines = [codes[i] for i, v in enumerate(c['guideline_labels']) if v]
                        elif 'guidelines' in c:
                            if isinstance(c['guidelines'], list):
                                guidelines = c['guidelines']
                            else:
                                guidelines = [g for g, data in c['guidelines'].items() if data.get('relevant')]

                        case_type = c.get('case_type', 'hearing')
                        if case_type == 'appeal':
                            discussion = c.get('discussion', '')
                            key_facts = [discussion[:500]] if discussion else []
                        else:
                            key_facts = c.get('sor_allegations', [])[:5]

                        summary = c.get('summary', '')
                        if not summary:
                            summary = c.get('text', c.get('full_text', ''))[:500]

                        judge = c.get('judge', '')
                        if not judge:
                            judge = c.get('metadata', {}).get('judge', '')

                        case_number = c.get('case_number', 'Unknown')
                        try:
                            if case_number.startswith('appeal-'):
                                year = int(case_number.split('-')[1])
                            else:
                                year_str = case_number[:2]
                                year = int(year_str) + (2000 if int(year_str) < 50 else 1900)
                        except (ValueError, IndexError):
                            year = 2020

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
                    logger.info(f"Index updated - now contains {len(indexer.cases)} total cases")
                else:
                    # Create new index from scratch
                    indexer = create_index_from_extracted_cases(tmp_path, output_path)
                    logger.info(f"Index created with {len(indexer.cases)} cases from parquet")
                return output_path
            finally:
                tmp_path.unlink()

        except ImportError:
            logger.error("pandas not installed - cannot read parquet files")
            logger.error("Install with: pip install pandas pyarrow")
            logger.info("Falling back to JSON if available...")
            # Fall through to JSON check below

    # Fallback to JSON if parquet not available or pandas missing
    if cases_path.exists():
        if update and output_path.exists():
            # Update mode with JSON
            from rag.indexer import DOHAIndexer
            import json

            logger.info(f"Update mode: loading existing index from {output_path}")
            indexer = DOHAIndexer(index_path=output_path)
            indexer.load()

            existing_case_numbers = {case.case_number for case in indexer.cases}
            logger.info(f"Existing index has {len(existing_case_numbers)} cases")

            # Load all cases from JSON
            with open(cases_path) as f:
                all_cases = json.load(f)

            # Filter for new cases
            new_cases = [
                case for case in all_cases
                if case.get('case_number', 'Unknown') not in existing_case_numbers
            ]

            logger.info(f"Found {len(new_cases)} new cases to add (skipping {len(all_cases) - len(new_cases)} existing)")

            if not new_cases:
                logger.success("No new cases to add - index is up to date")
                return output_path

            # Create temp file with only new cases
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
                json.dump(new_cases, tmp, indent=2)
                tmp_path = Path(tmp.name)

            try:
                # Parse and add new cases (reuse logic from parquet section)
                from rag.indexer import IndexedCase
                indexed_cases = []
                for c in new_cases:
                    outcome = c.get('outcome', c.get('overall_decision', 'UNKNOWN'))
                    if outcome not in ['GRANTED', 'DENIED', 'REVOKED', 'REMANDED']:
                        outcome = 'UNKNOWN'

                    guidelines = []
                    if 'guideline_labels' in c:
                        codes = list("ABCDEFGHIJKLM")
                        guidelines = [codes[i] for i, v in enumerate(c['guideline_labels']) if v]
                    elif 'guidelines' in c:
                        if isinstance(c['guidelines'], list):
                            guidelines = c['guidelines']
                        else:
                            guidelines = [g for g, data in c['guidelines'].items() if data.get('relevant')]

                    case_type = c.get('case_type', 'hearing')
                    if case_type == 'appeal':
                        discussion = c.get('discussion', '')
                        key_facts = [discussion[:500]] if discussion else []
                    else:
                        key_facts = c.get('sor_allegations', [])[:5]

                    summary = c.get('summary', '')
                    if not summary:
                        summary = c.get('text', c.get('full_text', ''))[:500]

                    judge = c.get('judge', '')
                    if not judge:
                        judge = c.get('metadata', {}).get('judge', '')

                    case_number = c.get('case_number', 'Unknown')
                    try:
                        if case_number.startswith('appeal-'):
                            year = int(case_number.split('-')[1])
                        else:
                            year_str = case_number[:2]
                            year = int(year_str) + (2000 if int(year_str) < 50 else 1900)
                    except (ValueError, IndexError):
                        year = 2020

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
                logger.info(f"Index updated - now contains {len(indexer.cases)} total cases")
                return output_path
            finally:
                tmp_path.unlink()
        else:
            # Build new index from JSON
            logger.info(f"Building index from JSON: {cases_path}...")
            indexer = create_index_from_extracted_cases(cases_path, output_path)
            logger.info(f"Index created with {len(indexer.cases)} cases from JSON")
            return output_path
    else:
        logger.error(f"Neither parquet nor JSON files found at {cases_path}")
        return None


def convert_scraped_to_indexed(cases):
    """Convert ScrapedCase objects to IndexedCase objects"""
    from rag.indexer import IndexedCase

    indexed_cases = []
    for case in cases:
        # Parse year from case number
        try:
            year_str = case.case_number[:2]
            year = int(year_str)
            year = year + 2000 if year < 50 else year + 1900
        except:
            year = 2020

        indexed_cases.append(IndexedCase(
            case_number=case.case_number,
            year=year,
            outcome=case.outcome if case.outcome != "UNKNOWN" else "DENIED",
            guidelines=case.guidelines,
            summary=case.summary,
            key_facts=case.sor_allegations,
            judge=case.judge
        ))

    return indexed_cases


def build_index(indexed_cases, output_path: Path):
    """Build and save the index"""
    from rag.indexer import DOHAIndexer

    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"Building vector index for {len(indexed_cases)} cases...")
    indexer = DOHAIndexer(index_path=output_path)
    indexer.add_cases_batch(indexed_cases)
    indexer.save()

    # Print statistics
    print_index_stats(indexer)

    logger.info(f"Index saved to {output_path}")
    return output_path


def print_index_stats(indexer):
    """Print statistics about the index"""
    from collections import Counter

    print("\n" + "=" * 60)
    print("INDEX STATISTICS")
    print("=" * 60)

    print(f"\nTotal cases: {len(indexer.cases)}")

    # Outcome distribution
    outcomes = Counter(c.outcome for c in indexer.cases)
    print("\nOutcome distribution:")
    for outcome, count in outcomes.most_common():
        pct = count / len(indexer.cases) * 100
        print(f"  {outcome}: {count} ({pct:.1f}%)")

    # Guideline distribution
    guideline_counts = Counter()
    for case in indexer.cases:
        for g in case.guidelines:
            guideline_counts[g] += 1

    print("\nTop guidelines:")
    for guideline, count in guideline_counts.most_common(5):
        print(f"  Guideline {guideline}: {count} cases")

    # Year distribution
    years = Counter(c.year for c in indexer.cases)
    print("\nCases by year:")
    for year in sorted(years.keys()):
        print(f"  {year}: {years[year]}")

    print("=" * 60 + "\n")


def test_index(index_path: Path):
    """Test the index with a sample query"""
    from rag.retriever import PrecedentRetriever

    index_path = Path(index_path)

    if not index_path.exists():
        logger.error(f"Index not found at {index_path}")
        return

    retriever = PrecedentRetriever(index_path=index_path)
    retriever.load()

    # Test query
    test_query = """
    The applicant has approximately $50,000 in delinquent debt including credit cards,
    medical bills, and a defaulted auto loan. The applicant filed for Chapter 7 bankruptcy
    in 2022. The financial problems began after a job loss in 2020.
    """

    print("\n" + "=" * 60)
    print("TEST SEARCH")
    print("=" * 60)
    print("\nQuery: Financial difficulties with $50k debt and bankruptcy")

    results = retriever.retrieve(test_query, guidelines=['F'], num_precedents=3)

    if results:
        print(f"\nFound {len(results)} similar cases:\n")
        for p in results:
            print(f"  Case: {p['case_number']}")
            print(f"  Outcome: {p['outcome']}")
            print(f"  Guidelines: {', '.join(p['guidelines'])}")
            print(f"  Relevance: {p['relevance_score']:.3f}")
            print(f"  Summary: {p['summary'][:150]}...")
            print()
    else:
        print("\nNo matching cases found")

    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description='Build DOHA case precedent index for RAG analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Scrape from DOHA website:
    %(prog)s --scrape --start-year 2020 --end-year 2024 --output ./doha_index

  Build from local PDF/HTML files:
    %(prog)s --local-dir ./downloaded_cases --output ./doha_index

  Build from pre-extracted cases (Parquet or JSON):
    %(prog)s --from-cases ./extracted_cases.parquet --output ./doha_index

  Update existing index with new cases only:
    %(prog)s --from-cases ./extracted_cases.parquet --output ./doha_index --update

  Test an existing index:
    %(prog)s --test --index ./doha_index
        """
    )

    # Source options (mutually exclusive)
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument('--scrape', action='store_true',
                              help='Scrape cases from DOHA website')
    source_group.add_argument('--local-dir',
                              help='Build from local case files (PDF/HTML/TXT)')
    source_group.add_argument('--from-cases',
                              help='Build from pre-extracted cases (prefers Parquet, falls back to JSON)')
    source_group.add_argument('--test', action='store_true',
                              help='Test an existing index')

    # Scraping options
    parser.add_argument('--start-year', type=int, default=2020,
                        help='Start year for scraping (default: 2020)')
    parser.add_argument('--end-year', type=int, default=2024,
                        help='End year for scraping (default: 2024)')
    parser.add_argument('--max-cases', type=int,
                        help='Maximum total cases to scrape')
    parser.add_argument('--rate-limit', type=float, default=1.0,
                        help='Seconds between requests (default: 1.0)')

    # Output options
    parser.add_argument('--output', '-o', default='./doha_index',
                        help='Output directory for index (default: ./doha_index)')
    parser.add_argument('--index', help='Path to existing index (for --test)')

    # Update options
    parser.add_argument('--update', action='store_true',
                        help='Update existing index with new cases only (much faster for daily updates)')

    # Other options
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    logger.remove()
    logger.add(sys.stderr, level=log_level)
    logger.add("build_index.log", rotation="10 MB", level="DEBUG")

    # Validate arguments
    if args.test:
        if not args.index and not Path(args.output).exists():
            parser.error("--test requires --index or an existing index at --output path")
        test_index(Path(args.index or args.output))
        return 0

    if not (args.scrape or args.local_dir or args.from_cases):
        parser.print_help()
        print("\nError: Specify one of --scrape, --local-dir, or --from-cases")
        return 1

    # Run appropriate mode
    output_path = Path(args.output)

    try:
        if args.scrape:
            result = scrape_and_build(
                output_path=output_path,
                start_year=args.start_year,
                end_year=args.end_year,
                max_cases=args.max_cases,
                rate_limit=args.rate_limit
            )
        elif args.local_dir:
            result = build_from_local(
                local_dir=Path(args.local_dir),
                output_path=output_path
            )
        elif args.from_cases:
            result = build_from_cases(
                cases_path=Path(args.from_cases),
                output_path=output_path,
                update=args.update
            )

        if result:
            if args.update:
                print(f"\nSuccess! Index updated at: {result}")
            else:
                print(f"\nSuccess! Index created at: {result}")
            print(f"\nTo use with analyzer:")
            print(f"  python analyze.py --input report.pdf --use-rag --index {result}")
            return 0
        else:
            if args.update:
                print("\nFailed to update index")
            else:
                print("\nFailed to create index")
            return 1

    except ImportError as e:
        print(f"\nMissing dependency: {e}")
        print("Install required packages: pip install -r requirements.txt")
        return 1
    except Exception as e:
        logger.exception(f"Error building index: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
