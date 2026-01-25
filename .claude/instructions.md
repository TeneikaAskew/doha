# DOHA SEAD-4 Analyzer Project Instructions

## Project Overview

This is an LLM-powered system for analyzing security clearance reports against SEAD-4 adjudicative guidelines. It includes:
- Browser-based scraping of ~36,700 DOHA cases using Playwright
- PDF download and parsing with bot protection bypass
- RAG-based precedent matching
- LLM analysis with Google Gemini (default) or Anthropic Claude

## Core Principles

### Testing Requirements
- **ALWAYS test code before marking tasks complete**
- Run the script with test parameters first (e.g., `--max-cases 10`)
- Verify output files are created correctly
- Check logs for errors or warnings
- Test resume logic by running twice
- Only mark a task done after successful execution

### Git Commit Guidelines
- **DO NOT include "Co-Authored-By: Claude Sonnet 4.5" in commit messages**
- Use clear, descriptive commit messages in imperative mood
- Reference file paths and line numbers when relevant
- Keep commits focused on a single logical change
- Follow existing commit style from `git log`

### Code Quality Standards
- Never create files unless necessary - prefer editing existing files
- Avoid over-engineering - keep solutions simple and focused
- Don't add features beyond what was requested
- Only add error handling for scenarios that can actually occur
- Remove unused code completely rather than commenting it out
- Use specialized tools (Read, Edit, Grep) instead of bash for file operations

### Security Awareness
- This project handles web scraping with bot protection bypass
- All scraping respects rate limits (2-3 seconds between requests)
- DOHA cases are public government records
- Educational purpose only - not for production use
- Be mindful of Akamai CDN protection mechanisms

## Project-Specific Guidelines

### Browser Scraping (Playwright)
- Individual PDF URLs are protected by Akamai bot protection
- NEVER use standard HTTP requests (requests library) for PDFs - they return 403
- ALWAYS use Playwright's browser automation with `page.context.request.get()`
- Default rate limit: 2.0 seconds between requests
- Scraper runs in headless mode by default

### Resume Logic
- Check both: PDF file exists AND case is in `all_cases.json`
- Merge new results with existing cases, never overwrite
- Save checkpoints every 50 cases
- Log skipped cases at INFO level, not DEBUG (reduces clutter)

### Link Format Compatibility
- Old format: `[year, case_number, url]` (3-tuple) - assumes "hearing" type
- New format: `[case_type, year, case_number, url]` (4-tuple)
- Always handle both formats for backward compatibility
- Convert old format to new format internally

### PDF Organization
- Hearings: `doha_parsed_cases/hearing_pdfs/`
- Appeals: `doha_parsed_cases/appeal_pdfs/`
- Parsed data: `doha_parsed_cases/all_cases.json`
- Checkpoints: `doha_parsed_cases/checkpoint_N.json`

### Performance Expectations
- Link collection: ~11 minutes for ~36,700 cases
- PDF download: ~200 cases/minute (4 workers), ~3 hours total
- Index building: ~5-10 minutes for ~36,700 cases
- Parallel downloads supported via `--workers N` flag

## File Structure

```
/workspaces/doha/
├── run_full_scrape.py          # Link collection (hearings + appeals)
├── download_pdfs.py            # PDF download with browser automation
├── doha_full_scrape/           # Collected links by year and type
│   ├── all_case_links.json     # Combined links file
│   ├── hearing_links_YYYY.json # Per-year hearing links
│   └── appeal_links_YYYY.json  # Per-year appeal links
├── doha_parsed_cases/          # Downloaded PDFs and parsed data
│   ├── all_cases.json          # All parsed cases
│   ├── hearing_pdfs/           # Hearing PDFs
│   └── appeal_pdfs/            # Appeal PDFs
└── sead4_llm/                  # LLM analysis code
    ├── analyze.py              # Main entry point
    ├── build_index.py          # RAG index builder
    ├── analyzers/              # LLM provider implementations
    ├── rag/                    # Scraping and retrieval
    │   ├── browser_scraper.py  # Playwright scraper
    │   └── scraper.py          # HTTP scraper (blocked)
    └── config/                 # SEAD-4 guidelines
```

## Common Commands

### Testing Downloads
```bash
python download_pdfs.py --max-cases 10          # Test with 10 cases
python download_pdfs.py --max-cases 100         # Test with 100 cases
python download_pdfs.py --case-type appeals     # Only appeals
```

### Link Collection
```bash
python run_full_scrape.py                       # All cases
python run_full_scrape.py --case-type hearings  # Only hearings
python run_full_scrape.py --case-type appeals   # Only appeals
```

### Index Building
```bash
cd sead4_llm
python build_index.py --from-cases ../doha_parsed_cases/all_cases.parquet --output ../doha_index
python build_index.py --test --index ../doha_index
```

## Error Handling

### Common Issues
1. **Import errors**: Check `sys.path.insert(0, str(Path(__file__).parent / "sead4_llm"))`
2. **403 errors**: Use browser automation, not HTTP requests
3. **Link format errors**: Handle both 3-tuple and 4-tuple formats
4. **Resume not working**: Check both PDF existence AND parsed JSON entry

### Debugging
- Check logs in `/tmp/claude/-workspaces-doha/tasks/` for background tasks
- Verify checkpoint files are being created every 50 cases
- Test resume logic by running same command twice
- Use `--force` to re-download everything if needed

## LLM Provider Configuration

### Default: Google Gemini
```bash
export GOOGLE_API_KEY=your_key_here
python analyze.py --input report.pdf
```

### Alternative: Anthropic Claude
```bash
export ANTHROPIC_API_KEY=your_key_here
python analyze.py --input report.pdf --provider claude
```

## Task Completion Checklist

Before marking any task as complete:
- [ ] Code runs without errors
- [ ] Tested with small dataset (10-100 cases)
- [ ] Output files created in correct locations
- [ ] Resume logic works (run twice, second time skips)
- [ ] Logs are clear and informative (not too verbose)
- [ ] No hardcoded paths or assumptions
- [ ] Backward compatible with existing data
- [ ] Git commit created with clean message (NO Co-Authored-By line)

## Remember
- Test first, commit later
- Simple is better than complex
- Resume logic is critical for long-running downloads
- Browser automation is mandatory for PDFs
- Keep terminal output clean and actionable
