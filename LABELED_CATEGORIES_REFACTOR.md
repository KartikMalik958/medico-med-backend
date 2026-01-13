# Medical Health Assistant - Labeled Categories Refactor

## Overview
Refactored the Medical Health Assistant question flow to support labeled categories and subcategories, with MongoDB persistence using labels as keys.

## Changes Made

### 1. MongoDB Service (`mongodb_service.py`)
- **New file** for MongoDB operations
- Stores responses using labels (AA_1, BA_2, etc.) as keys
- Methods:
  - `save_response(session_id, question_label, answer)` - Save single answer
  - `save_responses_batch(session_id, responses)` - Save multiple answers
  - `get_session_responses(session_id)` - Retrieve all responses
  - `get_response(session_id, question_label)` - Retrieve specific response
  - `delete_session(session_id)` - Delete session data

### 2. Questions Structure (`questions.json`)
- **Refactored** to nested category/subcategory structure:
  ```json
  {
    "categories": {
      "A": {
        "title": "Introduction",
        "subcategories": {
          "AA": {
            "title": "Welcome",
            "questions": {
              "AA_1": "Question text..."
            }
          }
        }
      }
    }
  }
  ```
- **Labels**: A, B, C... (categories), AA, AB, AC... (subcategories), AA_1, AA_2... (questions)
- **Flow order**: Array of category labels (A, B, C, ...)
- **Dependencies**: Map of question_label -> [dependencies]
- **Priorities**: Map of question_label -> priority number

### 3. Question Flow Engine (`question_flow_engine.py`)
- **Updated** `_load_questions()` to parse nested structure
- **New** `_flatten_questions()` method to create flat question map
- **Updated** all methods to use labels (AA_1, BA_2, etc.) instead of old IDs
- **Updated** `_get_available_questions()` to work with labels
- **Updated** `_sort_questions_by_order()` to use category labels and priorities
- **Updated** `_judge_next_question()` to return labels
- **Updated** `_store_answer_with_embedding()` to use labels

### 4. Chatbot Engine (`chatbot_engine.py`)
- **Added** MongoDB service import
- **Added** automatic saving of answers to MongoDB using labels
- **Updated** to use labels internally while exposing only question text
- **Ensured** labels are never exposed in API responses

### 5. Main API (`main.py`)
- **Updated** to remove `current_question_id` from API responses (it's a label)
- **Ensured** labels are never exposed to frontend

## Label Structure

### Categories (High-level)
- **A**: Introduction
- **B**: Demographics
- **C**: Chief Complaint
- **D**: History of Present Illness
- **E**: Past Medical History
- **F**: Medications
- **G**: Allergies
- **H**: Family History
- **I**: Social History
- **J**: Review of Systems
- **K**: Vital Signs
- **L**: Assessment

### Subcategories (Under each category)
- **AA, AB, AC...** (under A)
- **BA, BB, BC...** (under B)
- etc.

### Questions (Under each subcategory)
- **AA_1, AA_2...** (under AA)
- **BA_1, BA_2...** (under BA)
- etc.

## MongoDB Schema

```javascript
{
  sessionId: "session_123",
  responses: {
    "AA_1": "yes",
    "BA_1": "22",
    "BA_2": "Male",
    "CA_1": "Chest pain",
    // ... more responses
  },
  createdAt: ISODate("2025-12-04T..."),
  updatedAt: ISODate("2025-12-04T...")
}
```

## Key Features

1. **Labels are Internal Only**
   - Never exposed in API responses
   - Never shown in logs (only in debug prints)
   - Only question text is sent to frontend

2. **Deterministic Labels**
   - Labels are consistent across sessions
   - Based on category/subcategory structure
   - Format: `{category}{subcategory}_{number}`

3. **Flow Order Preserved**
   - Questions follow: category → subcategory → priority
   - Dependencies still respected
   - Same consultation flow as before

4. **MongoDB Persistence**
   - Answers stored with labels as keys
   - Batch saving for efficiency
   - Session-based storage

## Usage

### Backend
1. Install dependencies: `pip install -r requirements.txt`
2. Set `MONGODB_URI` in `.env` (or uses default from main backend)
3. Start server: `python main.py`

### MongoDB Access
```python
from mongodb_service import mongodb_service

# Save answer
mongodb_service.save_response("session_123", "AA_1", "yes")

# Get all responses
responses = mongodb_service.get_session_responses("session_123")
# Returns: {"AA_1": "yes", "BA_1": "22", ...}

# Get specific response
answer = mongodb_service.get_response("session_123", "AA_1")
# Returns: "yes"
```

## Testing

1. **Start the backend**: `python main.py`
2. **Send a message**: "hi"
3. **Check MongoDB**: Verify responses are saved with labels
4. **Verify API**: Ensure no labels are in API responses
5. **Check logs**: Labels only in debug prints, not in user-facing logs

## Migration Notes

- Old question IDs (intro_1, demo_1, etc.) are replaced with labels (AA_1, BA_1, etc.)
- Session state still uses labels internally
- Frontend receives only question text (no labels)
- MongoDB stores answers with labels as keys

## Files Modified

1. `med/backend/questions.json` - Refactored structure
2. `med/backend/question_flow_engine.py` - Updated to use labels
3. `med/backend/chatbot_engine.py` - Added MongoDB saving
4. `med/backend/main.py` - Removed label exposure
5. `med/backend/requirements.txt` - Added pymongo
6. `med/backend/mongodb_service.py` - New file

## Constraints Met

✅ Labels are internal only (never exposed)  
✅ MongoDB persistence with labels as keys  
✅ Flow order preserved (category → subcategory → question)  
✅ Minimal changes, clean code  
✅ Uses existing MongoDB connection  
✅ Deterministic and consistent labels  



