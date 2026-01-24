# LLM Response Cache

This directory contains cached LLM API responses for the SEAD-4 Analyzer.

## Purpose

Caching LLM responses allows the demo UI to:
- Load previous analysis results instantly without making API calls
- Avoid redundant API costs when re-analyzing the same cases
- Provide consistent results for demonstration purposes

## File Naming Convention

Cache files follow this pattern:
```
llm_response_{CASE_ID}_{SUFFIX}.txt
```

Where:
- `{CASE_ID}`: The case identifier (e.g., "PSH-25-0214")
- `{SUFFIX}`: The analysis type:
  - `llm`: LLM analysis without native guidance
  - `native_rag`: LLM analysis guided by basic native results
  - `enhanced_native_rag`: LLM analysis guided by enhanced native results

## Examples

- `llm_response_PSH-25-0214_llm.txt` - Pure LLM analysis of case PSH-25-0214
- `llm_response_PSH-25-0137_enhanced_native_rag.txt` - RAG analysis of case PSH-25-0137

## Usage

### Automatic Caching

Cache files are automatically created when:
1. Debug logging is enabled (log level DEBUG or lower)
2. An LLM analysis completes successfully
3. The response is written to this directory

### Cache Loading

The demo UI automatically checks this directory before making API calls:
1. If a cache file exists, it's loaded and parsed instantly
2. If no cache exists, a new API call is made
3. New responses are cached for future use

## Security Note

These files may contain sensitive information from security clearance cases. Ensure:
- This directory is included in `.gitignore`
- Files are not committed to version control
- Proper access controls are maintained on the filesystem

## Maintenance

You can safely delete cache files to force fresh analysis:
```bash
# Delete all cache files
rm llm_cache/*.txt

# Delete cache for specific case
rm llm_cache/llm_response_PSH-25-0214_*.txt
```
