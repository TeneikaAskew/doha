#!/usr/bin/env python3
"""
DOHA Case Index Builder

Build a precedent index from DOHA case decisions for RAG-augmented analysis.

Usage:
    # Scrape from DOHA website and build index
    python build_index.py --scrape --start-year 2020 --end-year 2024 --output ./doha_index

    # Build index from local case files
    python build_index.py --local-dir ./my_cases --output ./doha_index

    # Build index from pre-extracted JSON
    python build_index.py --from-json ./cases.json --output ./doha_index
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


def build_from_json(json_path: Path, output_path: Path):
    """Build index from pre-extracted JSON or Parquet file"""
    from rag.indexer import create_index_from_extracted_cases

    json_path = Path(json_path)
    output_path = Path(output_path)

    # Check if parquet files exist instead
    if not json_path.exists():
        # Look for parquet files
        parquet_base = json_path.parent / json_path.stem
        parquet_files = list(json_path.parent.glob(f"{json_path.stem}*.parquet"))

        if parquet_files:
            logger.info(f"JSON not found, but found {len(parquet_files)} parquet file(s)")
            logger.info(f"Loading from parquet: {', '.join(f.name for f in parquet_files)}")

            try:
                import pandas as pd

                # Load all parquet files and combine
                dfs = [pd.read_parquet(f) for f in sorted(parquet_files)]
                df = pd.concat(dfs, ignore_index=True)
                cases_data = df.to_dict('records')

                # Create temporary JSON in memory for the indexer
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
                    import json
                    json.dump(cases_data, tmp, indent=2)
                    tmp_path = Path(tmp.name)

                try:
                    indexer = create_index_from_extracted_cases(tmp_path, output_path)
                    logger.info(f"Index created with {len(indexer.cases)} cases from parquet")
                    return output_path
                finally:
                    tmp_path.unlink()

            except ImportError:
                logger.error("pandas not installed - cannot read parquet files")
                logger.error("Install with: pip install pandas pyarrow")
                return None
        else:
            logger.error(f"Neither JSON nor parquet files found at {json_path}")
            return None

    logger.info(f"Building index from {json_path}...")
    indexer = create_index_from_extracted_cases(json_path, output_path)

    logger.info(f"Index created with {len(indexer.cases)} cases")
    return output_path


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

  Build from pre-extracted JSON:
    %(prog)s --from-json ./extracted_cases.json --output ./doha_index

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
    source_group.add_argument('--from-json',
                              help='Build from pre-extracted JSON or Parquet file (auto-detects format)')
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

    if not (args.scrape or args.local_dir or args.from_json):
        parser.print_help()
        print("\nError: Specify one of --scrape, --local-dir, or --from-json")
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
        elif args.from_json:
            result = build_from_json(
                json_path=Path(args.from_json),
                output_path=output_path
            )

        if result:
            print(f"\nSuccess! Index created at: {result}")
            print(f"\nTo use with analyzer:")
            print(f"  python analyze.py --input report.pdf --use-rag --index {result}")
            return 0
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
