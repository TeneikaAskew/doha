# Summary of Fixes and Improvements

## Your Questions Answered

### Q1: Does the LLM use outputs from the analysis or just the doc?

**Answer:** Currently, the LLM receives **only the document text** and precedents (if RAG is enabled). It does NOT receive the native analysis output.

**How it works:**
1. Native analyzer runs → analyzes document independently
2. LLM analyzer runs → receives same document + precedents
3. Both analyses are completely independent
4. Results are compared side-by-side

**This can be improved** by optionally passing the native analysis to the LLM to:
- Validate native findings
- Provide a baseline for comparison
- Catch errors in native pattern matching
- Add deeper reasoning to native findings

### Q2: Why are there no relevant guidelines found by LLM?

**Answer:** The LLM IS returning a response (8,872 characters), but likely one of these issues:

1. **LLM returns empty/incomplete guidelines array**
   - The prompt asks for all 13 guidelines
   - LLM might be returning an empty `"guidelines": []` array
   - Code then fills in all 13 as "not relevant"

2. **JSON parsing issues**
   - LLM might wrap response in markdown code blocks
   - JSON might be malformed
   - Response might contain explanatory text before/after JSON

3. **LLM being overly conservative**
   - Model might be uncertain and defaulting to "INSUFFICIENT_INFO"
   - Might need more explicit prompt instructions

## Changes Made

### 1. Added Debug Logging ✅

**File:** `analyzers/gemini_analyzer.py`

Added logging to capture:
- Preview of LLM response (first 500 chars)
- Warning if guidelines array is empty
- Raw LLM response saved to file when verbose mode enabled

**How to use:**
```bash
python analyze.py --input test.pdf --provider gemini --verbose
# Creates llm_response_<case_id>.txt with full response
```

### 2. Improved Prompt Clarity ✅

**File:** `prompts/templates.py`

Enhanced the OUTPUT FORMAT section to be more explicit:
```
**IMPORTANT**: You MUST analyze ALL 13 guidelines (A through M),
even if they are not relevant.

Respond with ONLY a valid JSON object (no markdown, no explanation)
matching this exact schema:
```

### 3. Added Response Validation ✅

**File:** `analyzers/gemini_analyzer.py`

Added warning when LLM returns no guidelines:
```python
if not guidelines_data:
    logger.warning("LLM response contained no guidelines data -
                   all guidelines will be marked as not relevant")
```

### 4. Enhanced Native Analyzer Parameter ✅

**File:** `analyzers/gemini_analyzer.py`

Added optional `native_analysis` parameter to `analyze()` method for future enhancement where LLM can validate native findings.

## Prompt Might Need More Work

Based on your results, the prompt likely needs improvement. The current prompt is good but might not be explicit enough for the model you're using.

### Recommended Prompt Improvements

Add to the beginning of `ANALYSIS_PROMPT_TEMPLATE`:

```python
**CRITICAL FORMAT REQUIREMENTS**:
- Start your response with { and end with }
- Do NOT use markdown code blocks (no ```)
- Do NOT add explanations before or after the JSON
- You MUST include exactly 13 items in the "guidelines" array (codes A through M)
- For non-relevant guidelines, use: {"code": "X", "relevant": false, "reasoning": "...", ...}
- Example of a non-relevant guideline:
  {
    "code": "A",
    "name": "Allegiance to the United States",
    "relevant": false,
    "severity": null,
    "disqualifiers": [],
    "mitigators": [],
    "reasoning": "No indicators of allegiance concerns in document",
    "confidence": 0.9
  }
```

## How to Debug

### Step 1: Check what the LLM is actually returning

With your valid API key:
```bash
python analyze.py --input test_reports/PSH-25-0137.pdf --provider gemini --verbose
```

This creates `llm_response_PSH-25-0137.txt`

### Step 2: Examine the response

```bash
# View the raw response
cat llm_response_PSH-25-0137.txt

# Check if it's valid JSON
cat llm_response_PSH-25-0137.txt | jq .

# Count guidelines
cat llm_response_PSH-25-0137.txt | jq '.guidelines | length'
# Should be 13

# See which are relevant
cat llm_response_PSH-25-0137.txt | jq '.guidelines[] | select(.relevant == true) | .code'
```

### Step 3: Identify the issue

**If JSON is invalid:**
- LLM is wrapping in markdown or adding text
- Fix: Improve response parsing

**If guidelines array is empty or missing:**
- LLM isn't following instructions
- Fix: Make prompt more explicit (see above)

**If guidelines array has < 13 items:**
- LLM is only returning relevant ones
- Fix: Emphasize "ALL 13 guidelines required"

**If all 13 present but all marked not relevant:**
- LLM is being overly conservative
- Fix: Add examples to prompt, or use different model

## Recommended Next Steps

### Option 1: Quick Fix - More Explicit Prompt

Edit `prompts/templates.py` and add the CRITICAL FORMAT REQUIREMENTS section shown above.

### Option 2: Enhanced Comparison Mode

Make the LLM validate/enhance native findings:

```python
# In analyze.py, when running comparison mode:
llm_result = llm_analyzer.analyze(
    document_text=document_text,
    case_id=f"{case_id}_llm",
    precedents=precedents,
    native_analysis={
        'relevant_guidelines': [g.code for g in native_result.get_relevant_guidelines()],
        'concerns': native_result.overall_assessment.key_concerns,
        'recommendation': native_result.overall_assessment.recommendation.value
    }
)
```

Then update the prompt to include:
```
# INITIAL RULE-BASED ANALYSIS

A keyword-based analyzer identified the following as potentially relevant:
- Guidelines: {native_analysis['relevant_guidelines']}
- Primary concerns: {native_analysis['concerns']}

Please conduct your own independent deep analysis and either:
1. Confirm these findings with detailed reasoning, OR
2. Explain what the rule-based analyzer missed or got wrong
```

### Option 3: Try Different Model

```python
# Use a more reliable (but slower/costlier) model
analyzer = GeminiSEAD4Analyzer(model="gemini-1.5-pro")
```

## Testing After Changes

1. **Test single file:**
   ```bash
   python analyze.py --input test_reports/PSH-25-0137.pdf --compare --verbose
   ```

2. **Check logs for:**
   - ✓ "Retrieved 5 precedents" (RAG working)
   - ✓ "Response length: XXXX chars" (LLM responded)
   - ✗ "LLM response contained no guidelines data" (problem!)
   - ✓ "Saved raw LLM response to..." (debugging file created)

3. **Verify output shows:**
   - Native finds G, I, K as relevant ✓
   - LLM finds the same or provides explanation ✓
   - Both sections have actual analysis (not "No guidelines") ✓

## Files Created/Modified

### New Files:
- `analyzers/native_analyzer.py` - Rule-based analyzer
- `NATIVE_ANALYSIS_GUIDE.md` - Usage guide
- `TROUBLESHOOTING_LLM.md` - Detailed troubleshooting
- `analysis_results/FIXES_SUMMARY.md` - This file

### Modified Files:
- `analyzers/gemini_analyzer.py` - Added logging and debug output
- `prompts/templates.py` - Made prompt more explicit
- `schemas/models.py` - Added 'UNKNOWN' outcome, ComparisonAnalysisResult
- `analyze.py` - Added comparison mode, folder processing, native provider

## Quick Reference

```bash
# Native only (no API)
python analyze.py --input test.pdf --provider native

# LLM only
python analyze.py --input test.pdf --provider gemini

# Compare both
python analyze.py --input test.pdf --compare

# Compare with RAG
python analyze.py --input test.pdf --compare --use-rag --index ../doha_index

# Debug LLM output
python analyze.py --input test.pdf --provider gemini --verbose
cat llm_response_*.txt | jq .

# Process folder
python analyze.py --input test_reports/ --provider native
python analyze.py --input test_reports/ --compare
```
