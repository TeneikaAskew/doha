# LLM Analysis Troubleshooting Guide

## Issue: LLM Returns "No Guidelines Relevant"

### Problem Description
When running comparison mode, the LLM analysis returns:
- Recommendation: `INSUFFICIENT_INFO`
- Confidence: 50%
- No relevant guidelines identified
- Empty or minimal analysis

Meanwhile, the native analyzer correctly identifies relevant guidelines (e.g., G, I, K).

### Root Causes

There are several possible causes:

#### 1. LLM Returns Incomplete JSON
The LLM may be returning JSON without the `guidelines` array, or with an empty array.

**How to check:**
```bash
# Run with verbose logging
python analyze.py --input test.pdf --provider gemini --verbose
```

This will create a file `llm_response_<case_id>.txt` with the raw LLM response.

#### 2. JSON Parsing Fails
The response might not be valid JSON or might be wrapped in markdown code blocks.

**Check logs for:**
```
WARNING - Failed to parse JSON, attempting repair
ERROR - Failed to build result: ...
```

#### 3. LLM Not Following Format
The LLM might be responding with explanatory text instead of pure JSON.

#### 4. Prompt Ambiguity
The prompt might not be clear enough about the expected format.

### Solutions

#### Solution 1: Check Raw LLM Response

1. Run with verbose mode to save the raw response:
```bash
python analyze.py --input test.pdf --provider gemini --verbose 2>&1 | grep "Saved raw"
```

2. Examine the saved file:
```bash
cat llm_response_*.txt
```

3. Check if:
   - Response is valid JSON
   - Response includes "guidelines" array
   - Guidelines array has all 13 guidelines (A-M)
   - Each guideline has required fields

#### Solution 2: Improve the Prompt

The prompt has been updated to be more explicit:
- **Now states**: "You MUST analyze ALL 13 guidelines (A through M)"
- **Now requires**: "Respond with ONLY a valid JSON object (no markdown, no explanation)"

But you might need to make it even more explicit:

```python
# In prompts/templates.py, add to ANALYSIS_PROMPT_TEMPLATE:

**CRITICAL REQUIREMENTS**:
1. Your response MUST be ONLY valid JSON - no markdown, no code blocks, no explanations
2. You MUST include ALL 13 guidelines (A, B, C, D, E, F, G, H, I, J, K, L, M)
3. Each guideline MUST have: code, name, relevant, reasoning, confidence
4. Start your response with { and end with }
```

#### Solution 3: Add Response Validation

Add a validation check before parsing:

```python
# In gemini_analyzer.py, after getting response_text:

# Strip markdown code blocks if present
if response_text.startswith('```'):
    lines = response_text.split('\n')
    if lines[0].strip() in ['```json', '```']:
        response_text = '\n'.join(lines[1:-1])
```

#### Solution 4: Use a More Reliable Model

Try using a different Gemini model:

```python
# In analyze.py or when creating the analyzer:
analyzer = GeminiSEAD4Analyzer(model="gemini-1.5-pro")  # More reliable but slower
```

#### Solution 5: Add Examples to Prompt

Add few-shot examples to the prompt showing the exact JSON format expected.

### Debugging Workflow

1. **Enable verbose logging:**
   ```bash
   python analyze.py --input test.pdf --provider gemini --verbose
   ```

2. **Check for warning messages:**
   Look for:
   - "LLM response contained no guidelines data"
   - "Failed to parse JSON"
   - "Failed to build result"

3. **Examine raw response:**
   ```bash
   cat llm_response_*.txt
   ```

4. **Validate JSON:**
   ```bash
   cat llm_response_*.txt | jq .
   ```
   If this fails, the JSON is malformed.

5. **Check guidelines array:**
   ```bash
   cat llm_response_*.txt | jq '.guidelines | length'
   ```
   Should return 13.

6. **Check relevant guidelines:**
   ```bash
   cat llm_response_*.txt | jq '.guidelines[] | select(.relevant == true) | .code'
   ```

### Common Patterns

#### Pattern 1: Empty Guidelines Array
```json
{
  "overall_assessment": {...},
  "guidelines": [],  // PROBLEM: Empty array
  "whole_person_analysis": [...]
}
```

**Fix:** Improve prompt to require all 13 guidelines.

#### Pattern 2: Markdown-Wrapped Response
```
```json
{
  "overall_assessment": {...}
}
```
```

**Fix:** Strip markdown code blocks in parsing.

#### Pattern 3: Incomplete Guidelines
```json
{
  "guidelines": [
    {"code": "F", "relevant": true, ...},
    {"code": "G", "relevant": true, ...}
    // Missing H-M
  ]
}
```

**Fix:** The code already handles this by filling in missing guidelines.

### Alternative: Using Native Analysis to Guide LLM

You can enhance the LLM by providing the native analysis as context:

```python
# In comparison mode, pass native results to LLM
llm_result = llm_analyzer.analyze(
    document_text=document_text,
    case_id=case_id,
    precedents=precedents,
    native_analysis=native_result.model_dump()  # NEW
)
```

Then update the prompt to include:
```
# INITIAL RULE-BASED ANALYSIS

A rule-based analyzer identified the following potentially relevant guidelines:
{native_analysis_summary}

Please conduct your own independent analysis and compare/contrast with these findings.
```

This gives the LLM a baseline to work from while still allowing independent judgment.

## Current vs. Desired Behavior

### Current Behavior
1. Native analyzer runs independently → identifies G, I, K
2. LLM analyzer runs independently → returns empty/incomplete result
3. Results don't match, no explanation why

### Improved Behavior (Option 1: Independent)
1. Native analyzer runs → identifies G, I, K
2. LLM analyzer runs with improved prompt → identifies correct guidelines
3. Results can be compared to validate consistency

### Improved Behavior (Option 2: LLM Validates Native)
1. Native analyzer runs → identifies G, I, K
2. LLM receives native results + document
3. LLM validates/refines native analysis with deeper reasoning
4. Output shows: Native findings + LLM refinements + agreement/disagreement

## Recommended Next Steps

1. **Immediate**: Run with `--verbose` to capture raw LLM response
   ```bash
   python analyze.py --input test_reports/PSH-25-0137.pdf --provider gemini --verbose
   cat llm_response_*.txt | jq .
   ```

2. **Short-term**: Update prompt to be more explicit (already done)

3. **Medium-term**: Add native analysis as context to LLM

4. **Long-term**:
   - Build response validator that checks for all required fields
   - Add retry logic if response is incomplete
   - Consider using structured output API if available

## Testing

After making changes, test with:

```bash
# Test single file
python analyze.py --input test_reports/PSH-25-0137.pdf --compare --verbose

# Test folder
python analyze.py --input test_reports/ --compare --verbose

# Check for consistency across multiple runs
for i in {1..3}; do
  python analyze.py --input test_reports/PSH-25-0137.pdf --provider gemini
done
```

Look for:
- All 13 guidelines present in output
- Relevant guidelines correctly identified
- Confidence scores > 50%
- Specific disqualifiers cited
- Consistent results across runs
