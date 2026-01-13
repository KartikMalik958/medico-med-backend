# Event Loop Diagnosis & Fix Report

## Problem Statement
The Medical Health Assistant chatbot is stuck in an event loop, repeatedly asking "What is your name?" (or the first question in the flow).

## Root Cause Analysis

### Issue 1: State Preservation Failure
**Location:** `question_flow_engine.py` - `process_message()` method

**Problem:**
- When processing a user's answer, the `current_question_id` from the previous state (the question that was just asked) was not being properly preserved
- The state merging logic with LangGraph memory was potentially overwriting the `current_question_id` with an old value
- This caused the system to lose track of which question the user was answering

**Impact:**
- Answer couldn't be associated with the correct question
- Question wasn't marked as answered
- Same question was selected again in the next iteration

### Issue 2: Incomplete Answer Processing
**Location:** `question_flow_engine.py` - `_process_answer_node()` method

**Problem:**
- The answer processing logic only stored answers if the question wasn't already in `answered_questions`
- If state was inconsistent (answer exists but question not in set), the answer would be skipped
- This created a situation where answers existed but questions weren't marked as answered

**Impact:**
- Questions with answers weren't being excluded from selection
- Same question could be asked multiple times

### Issue 3: Inconsistent State Merging
**Location:** `question_flow_engine.py` - State merging with LangGraph memory

**Problem:**
- When loading state from LangGraph memory, the `current_question_id` from existing state could overwrite the one from `initial_state`
- The `initial_state` contains the question being answered (from session state), but this was being lost
- This broke the connection between the question and the answer

**Impact:**
- Answers couldn't be matched to questions
- Questions weren't marked as answered
- Event loop occurred

### Issue 4: Question Selection Not Checking Answers Dict
**Location:** `question_flow_engine.py` - `_select_question_node()` method

**Problem:**
- The question selection only checked `answered_questions` set
- It didn't also check the `answers` dictionary
- If a question had an answer but wasn't in the set, it could still be selected

**Impact:**
- Questions with answers could be selected again
- Event loop occurred

## Conversation Flow Trace

### Expected Flow:
1. **First Message:** User sends "Hello" or any message
   - System asks: `intro_1` - "Are you ready to begin?"
   - `current_question_id` = `intro_1`
   - `answered_questions` = `[]`
   - State saved to LangGraph memory

2. **Second Message:** User responds "Yes" or "Ready"
   - System should:
     - Process answer for `intro_1`
     - Mark `intro_1` as answered
     - Select next question: `demo_1` - "What is your age?"
     - `current_question_id` = `demo_1`
     - `answered_questions` = `['intro_1']`
   - **BUG:** If `current_question_id` is lost, answer can't be associated
   - **BUG:** If answer isn't processed, `intro_1` isn't marked as answered
   - **BUG:** `intro_1` gets selected again → Event loop

3. **Third Message:** User responds with age
   - System should ask: `demo_2` - "What is your gender?"
   - **BUG:** If previous step failed, still asking `intro_1` or `demo_1`

### Actual Broken Flow (Before Fix):
1. User: "Hello"
   - Bot: "Are you ready to begin?" (`intro_1`)
   - State: `current_question_id = intro_1`, `answered_questions = []`

2. User: "Yes"
   - **BUG:** `current_question_id` lost during state merge
   - **BUG:** Answer can't be matched to `intro_1`
   - **BUG:** `intro_1` not marked as answered
   - Bot: "Are you ready to begin?" (`intro_1`) ← REPEATED!

3. User: "Yes" (again)
   - Same bugs occur
   - Bot: "Are you ready to begin?" (`intro_1`) ← STUCK IN LOOP!

## Fixes Implemented

### Fix 1: Enhanced State Preservation
**File:** `question_flow_engine.py` - `process_message()`

**Changes:**
- Added comprehensive logging to track `current_question_id` through the flow
- Preserved `current_question_id` from `initial_state` when merging with LangGraph memory
- Added warning if `current_question_id` is missing

**Code:**
```python
# CRITICAL: Preserve current question ID from initial_state (the question being answered)
# Don't overwrite it with existing state - we want to process the answer to the current question
if not initial_state.get("current_question_id") and existing.get("current_question_id"):
    print(f"⚠ Using existing current_question_id from memory: {existing.get('current_question_id')}")
    initial_state["current_question_id"] = existing["current_question_id"]
else:
    print(f"✓ Preserving current_question_id from initial_state: {initial_state.get('current_question_id')}")
```

### Fix 2: Always Process Answers
**File:** `question_flow_engine.py` - `_process_answer_node()`

**Changes:**
- Always update the answer and mark question as answered, even if already answered
- This ensures state consistency
- Added error logging if question_id can't be determined

**Code:**
```python
# CRITICAL: Always update the answer and mark as answered, even if already answered
# This ensures state consistency
if "answers" not in state:
    state["answers"] = {}
state["answers"][question_id] = answer  # Update answer (might be refined)

# Mark as answered (ensure it's in the set)
if "answered_questions" not in state:
    state["answered_questions"] = set()
if isinstance(state["answered_questions"], list):
    state["answered_questions"] = set(state["answered_questions"])
state["answered_questions"].add(question_id)
```

### Fix 3: Check Both answered_questions and answers Dict
**File:** `question_flow_engine.py` - `_select_question_node()`

**Changes:**
- Merge `answered_questions` set with keys from `answers` dictionary
- This ensures any question with an answer is considered answered
- Added comprehensive logging

**Code:**
```python
# CRITICAL: Also add all questions that have answers to the answered set
# This ensures consistency - if there's an answer, the question is considered answered
answers_dict = state.get("answers", {})
for q_id in answers_dict.keys():
    answered.add(q_id)
state["answered_questions"] = answered  # Update state with merged set
```

### Fix 4: Enhanced Logging
**Files:** `question_flow_engine.py`, `chatbot_engine.py`

**Changes:**
- Added detailed logging at every step of the conversation flow
- Logs show:
  - Which question is being answered
  - Current answered questions
  - State preservation status
  - Question selection process
  - Any warnings or errors

## Question Order (from questions.json)

The questions are asked in this structured order:

1. **Introduction:**
   - `intro_1`: "Are you ready to begin?"

2. **Demographics:**
   - `demo_1`: "What is your age?"
   - `demo_2`: "What is your gender?"

3. **Chief Complaint:**
   - `cc_1`: "What brings you in today?"

4. **History of Present Illness:**
   - `hpi_1` through `hpi_6`: Various symptom questions

5. **Past Medical History:**
   - `pmh_1`, `pmh_2`: Medical history questions

6. **Medications:**
   - `med_1`, `med_2`: Current medications

7. **Allergies:**
   - `allergy_1`: Known allergies

8. **Family History:**
   - `fh_1`: Family medical history

9. **Social History:**
   - `sh_1`, `sh_2`: Lifestyle questions

10. **Review of Systems:**
    - `ros_1` through `ros_5`: System review questions

11. **Vital Signs:**
    - `vitals_1`, `vitals_2`: Vital signs questions

12. **Assessment:**
    - `assess_1`: Final assessment question

## Testing Instructions

1. **Restart the backend:**
   ```powershell
   cd "C:\Users\Kartik Malik\medico\med\backend"
   .\venv\Scripts\Activate.ps1
   python main.py
   ```

2. **Test the conversation:**
   - Send first message: "Hello"
   - Expected: Bot asks "Are you ready to begin?" (`intro_1`)
   - Send: "Yes"
   - Expected: Bot asks "What is your age?" (`demo_1`) - NOT `intro_1` again
   - Send: "25"
   - Expected: Bot asks "What is your gender?" (`demo_2`) - NOT `demo_1` again
   - Continue answering - each question should only appear once

3. **Check backend logs for:**
   - `✓ Marked question X as answered`
   - `✓ Selected next question: Y`
   - `📊 Current answered questions: [...]`
   - No warnings about missing `current_question_id`
   - No errors about question selection

## Expected Behavior After Fix

✅ Each question is asked exactly once
✅ Questions follow the structured order from `questions.json`
✅ Answers are properly stored and associated with questions
✅ State is preserved between interactions
✅ No event loops occur
✅ Workflow stops after asking one question and waits for user response

## Summary

The event loop was caused by **state preservation failures** where:
1. The `current_question_id` (which question was just asked) was lost during state merging
2. Answers couldn't be associated with questions
3. Questions weren't marked as answered
4. The same question was selected again

**The fix ensures:**
- `current_question_id` is always preserved
- Answers are always processed and questions are always marked as answered
- Both `answered_questions` set and `answers` dict are checked when selecting questions
- Comprehensive logging helps debug any future issues




