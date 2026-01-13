# Medical Health Assistant - Navigation Guide

## 📁 Codebase Structure

```
med/backend/
├── main.py                    # FastAPI server - API endpoints
├── chatbot_engine.py          # Main chatbot logic - orchestrates question flow
├── question_flow_engine.py    # LangGraph workflow - processes questions/answers
├── questions.json             # All consultation questions (26 questions)
├── audio_processor.py         # Voice/audio processing
├── CONSULTATION_WORKFLOW.md   # Workflow documentation
└── requirements.txt           # Python dependencies
```

## 🔄 Conversation Flow Architecture

### 1. **Entry Point: `main.py`**
   - **Endpoint:** `POST /api/chat/text`
   - **Location:** Line 85-115
   - **What it does:**
     - Receives user message
     - Calls `chatbot_engine.get_response()`
     - Returns response to frontend

### 2. **Orchestrator: `chatbot_engine.py`**
   - **Main Method:** `get_response()` (line 165)
   - **Key Method:** `_get_response_with_question_flow()` (line 237)
   - **What it does:**
     - Manages session state
     - Decides if it's first message or answer
     - Calls `question_flow_engine.process_message()`
     - Preserves state between requests

### 3. **Question Processor: `question_flow_engine.py`**
   - **Main Method:** `process_message()` (line 418)
   - **What it does:**
     - Determines if first interaction or answer
     - Processes answer and stores it
     - Selects next question using LangGraph workflow
     - Returns next question to ask

### 4. **Question Data: `questions.json`**
   - **Structure:**
     - `flow_order`: Category order
     - `questions`: Array of 26 questions
   - **Each question has:**
     - `id`: Unique identifier (e.g., "intro_1", "demo_1")
     - `category`: Question category
     - `priority`: Order within category
     - `question`: The actual question text
     - `dependencies`: Which questions must be answered first

## 🗺️ Question Flow Map

### Category Order (from `flow_order`):
1. **introduction** → `intro_1`: "Are you ready to begin?"
2. **demographics** → `demo_1`: "What is your age?", `demo_2`: "What is your gender?"
3. **chief_complaint** → `cc_1`: "What brings you in today?"
4. **history_of_present_illness** → `hpi_1` through `hpi_6`
5. **past_medical_history** → `pmh_1`, `pmh_2`
6. **medications** → `med_1`, `med_2`
7. **allergies** → `allergy_1`
8. **family_history** → `fh_1`
9. **social_history** → `sh_1`, `sh_2`
10. **review_of_systems** → `ros_1` through `ros_5`
11. **vital_signs** → `vitals_1`, `vitals_2`
12. **assessment** → `assess_1`

## 🔍 Key Code Sections to Understand

### State Management (`chatbot_engine.py`)

**Session State Structure:**
```python
session_state = {
    "answered_questions": ["intro_1", "demo_1"],  # List of answered question IDs
    "answers": {"intro_1": "yes", "demo_1": "25"},  # Question ID → Answer mapping
    "current_question_id": "demo_2",  # Current question being asked
    "question_embeddings": {},  # Embeddings for semantic search
    "messages": []  # Conversation history
}
```

**Key Methods:**
- **Line 256-263:** Session state initialization
- **Line 271-280:** First message detection
- **Line 311-349:** State preservation after processing

### Question Selection (`question_flow_engine.py`)

**Key Methods:**
- **Line 449-495:** First interaction handling
- **Line 497-534:** Answer processing
- **Line 238-291:** `_select_question_node()` - Selects next question
- **Line 163-186:** `_judge_next_question()` - Determines which question to ask next
- **Line 138-161:** `_sort_questions_by_order()` - Sorts questions by category/priority

**Selection Logic:**
1. Get available questions (dependencies satisfied, not answered)
2. Sort by: category order → priority → question number
3. Return first question in sorted list

### Workflow Graph (`question_flow_engine.py`)

**LangGraph Workflow:**
```
process_answer → select_question → ask_question → check_completion → END
```

**Nodes:**
- `_process_answer_node()` (line 301): Stores answer, marks question as answered
- `_select_question_node()` (line 238): Selects next question
- `_ask_question_node()` (line 287): Adds question to messages
- `_check_completion_node()` (line 376): Checks if all questions answered

## 🐛 Debugging Guide

### 1. **Check if Question Flow is Active**
   Look for in logs:
   ```
   ✓ Using question flow for session: session_xxx
   ```

### 2. **Track State Changes**
   Look for in logs:
   ```
   📋 First message check: answered_count=0, current_q_id=None
   📝 Processing answer for question: intro_1
   ✓ Marked question intro_1 as answered
   ✓ Selected next question: demo_1
   ```

### 3. **Identify State Issues**
   Warning signs:
   ```
   ⚠ WARNING: No current_question_id found in session state!
   ⚠ ERROR: Selected question X is already answered!
   ```

### 4. **Check Question Selection**
   Look for:
   ```
   🔍 Selecting next question. Answered: ['intro_1']
   ✓ Selected question by strict order: demo_1
   ```

## 🧪 Testing Flow

### Manual Testing Steps:

1. **Start Backend:**
   ```powershell
   cd med/backend
   .\venv\Scripts\Activate.ps1
   python main.py
   ```

2. **Test First Message:**
   - Send: "hi"
   - Expected: "Are you ready to begin?" (`intro_1`)
   - Check logs: Should see `is_first=True`

3. **Test Answer Processing:**
   - Send: "yes"
   - Expected: "What is your age?" (`demo_1`)
   - Check logs: Should see `✓ Marked question intro_1 as answered`

4. **Test Progress:**
   - Send: "25"
   - Expected: "What is your gender?" (`demo_2`)
   - Check logs: Should see `answered_questions = ['intro_1', 'demo_1']`

## 📊 State Flow Diagram

```
User sends "hi"
    ↓
chatbot_engine.get_response()
    ↓
Check: is_first_message? (answered_count=0, current_q_id=None)
    ↓ YES
question_flow_engine.process_message()
    ↓
Check: is_first_interaction? (answered_count=0, current_q_id=None)
    ↓ YES
Return first question: "Are you ready to begin?" (intro_1)
    ↓
State: current_question_id = "intro_1", answered_questions = []

User sends "yes"
    ↓
chatbot_engine.get_response()
    ↓
Check: is_first_message? (answered_count=0, current_q_id="intro_1")
    ↓ NO (has current_q_id)
question_flow_engine.process_message()
    ↓
Check: is_first_interaction? (answered_count=0, current_q_id="intro_1")
    ↓ NO (has current_q_id)
Process answer: Store "yes" for intro_1
    ↓
Mark intro_1 as answered
    ↓
Select next question: demo_1
    ↓
Return: "What is your age?" (demo_1)
    ↓
State: current_question_id = "demo_1", answered_questions = ["intro_1"]
```

## 🔧 Common Issues & Solutions

### Issue 1: Same Question Repeated
**Symptom:** Bot keeps asking "Are you ready to begin?"
**Cause:** `current_question_id` not preserved
**Fix:** Check state preservation in `chatbot_engine.py` line 348-349

### Issue 2: Questions in Wrong Order
**Symptom:** Questions asked randomly
**Cause:** Sorting logic not working
**Fix:** Check `_sort_questions_by_order()` in `question_flow_engine.py` line 138

### Issue 3: Questions Skipped
**Symptom:** Some questions never asked
**Cause:** Dependencies not satisfied
**Fix:** Check `_get_available_questions()` in `question_flow_engine.py` line 118

### Issue 4: State Lost Between Requests
**Symptom:** Conversation resets
**Cause:** Session state not saved
**Fix:** Check `self.question_flow_sessions[session_id] = session_state` in `chatbot_engine.py` line 349

## 📝 Key Files to Edit

### To Add/Modify Questions:
- **File:** `questions.json`
- **Format:** JSON with `id`, `category`, `priority`, `question`, `dependencies`

### To Change Question Order:
- **File:** `questions.json`
- **Edit:** `flow_order` array and question `priority` values

### To Modify Conversation Logic:
- **File:** `chatbot_engine.py`
- **Key sections:** First message detection (line 271), state preservation (line 311)

### To Change Question Selection:
- **File:** `question_flow_engine.py`
- **Key methods:** `_judge_next_question()` (line 163), `_sort_questions_by_order()` (line 138)

## 🚀 Quick Reference

**Start Backend:**
```powershell
cd med/backend
.\venv\Scripts\Activate.ps1
python main.py
```

**Check Logs:**
- Look for `✓` (success) and `⚠` (warnings)
- Track `current_question_id` through the flow
- Monitor `answered_questions` list

**Test Endpoint:**
```bash
POST http://localhost:8001/api/chat/text
{
  "message": "hi",
  "session_id": "test_session",
  "language": "auto"
}
```

**View Questions:**
- Open `questions.json` to see all 26 questions
- Check `flow_order` for category sequence
- Check `dependencies` for question prerequisites

## 📚 Additional Resources

- `CONSULTATION_WORKFLOW.md` - Detailed workflow documentation
- `EVENT_LOOP_DIAGNOSIS.md` - Event loop debugging guide
- `STATE_PRESERVATION_FIX.md` - State management fixes
- `NAME_LOOP_FIX.md` - Name question prevention




