# Medical Consultation Workflow

## Overview

The Medical Health Assistant now uses a **structured doctor-patient consultation workflow** that systematically gathers comprehensive medical information through a predefined question flow.

## Key Features

### ✅ Structured Question Flow
- **One question at a time**: The AI asks a single question and waits for your response before proceeding
- **Comprehensive coverage**: 26 structured questions covering all aspects of a medical consultation
- **Logical progression**: Questions follow a natural doctor-patient consultation flow

### 📋 Consultation Flow Order

1. **Introduction** - Welcome and readiness check
2. **Demographics** - Age, gender
3. **Chief Complaint** - Main reason for visit
4. **History of Present Illness** - Detailed symptom information
   - Onset, nature, severity
   - Triggers and associated symptoms
   - Treatments tried
5. **Past Medical History** - Chronic conditions, surgeries
6. **Medications** - Current medications and supplements
7. **Allergies** - Known allergies
8. **Family History** - Significant family medical conditions
9. **Social History** - Lifestyle factors (smoking, alcohol, occupation)
10. **Review of Systems** - General health indicators
    - Weight changes, appetite, sleep, energy
    - Bowel/bladder habits
11. **Vital Signs** - Temperature, blood pressure (if available)
12. **Assessment** - Final summary and additional concerns

## How It Works

### Backend Implementation

1. **Question Flow Engine** (`question_flow_engine.py`)
   - Uses LangGraph for state management
   - Loads questions from `questions.json`
   - Tracks answered questions and dependencies
   - Stores answers with embeddings for future analysis

2. **Chatbot Engine** (`chatbot_engine.py`)
   - Question flow enabled by default
   - Structured prompts for medical consultations
   - One question at a time enforcement
   - Language detection and multilingual support

3. **Questions File** (`questions.json`)
   - 26 comprehensive questions
   - Organized by category with priorities
   - Dependency tracking ensures logical flow

### Frontend Implementation

- **Welcome Screen**: Explains structured consultation process
- **One Question at a Time**: UI enforces waiting for responses
- **Progress Tracking**: Shows consultation progress
- **Disclaimer**: Clear medical disclaimer displayed

## Usage

### Starting a Consultation

1. Navigate to "Medical Health Assistant" in the sidebar
2. You'll see a welcome message explaining the consultation process
3. Type your first response (e.g., "Yes, I'm ready" or describe your concern)
4. The AI will begin asking questions one at a time

### During Consultation

- **Answer each question** as it appears
- **Wait for the next question** - the AI will ask one at a time
- **Be thorough** - provide detailed answers for better assessment
- **You can type in any language** - the AI will respond in the same language

### Completing Consultation

- After all questions are answered, you'll receive a summary
- You can add additional concerns or ask follow-up questions
- The consultation history is saved for your session

## Technical Details

### Question Flow State Management

- Uses LangGraph with memory checkpointing
- Session-based state tracking
- Prevents duplicate questions
- Handles dependencies between questions

### Emergency Detection

The system includes prompts to detect emergency situations:
- Chest pain
- Difficulty breathing
- Severe trauma
- Loss of consciousness

If detected, the AI will immediately advise seeking emergency medical care.

## Configuration

### Environment Variables

- `ENABLE_QUESTION_FLOW=true` (default: enabled)
- `OPENAI_API_KEY` - Required for AI responses
- `BACKEND_PORT=8001` - Med backend port

### Disabling Question Flow

To disable structured consultation and use free-form chat:

1. Set `ENABLE_QUESTION_FLOW=false` in `.env`
2. Or modify `main.py` to set `enable_question_flow=False`

## Files Modified

1. **`questions.json`** - Comprehensive medical consultation questions
2. **`chatbot_engine.py`** - Question flow enabled by default, improved prompts
3. **`main.py`** - Question flow enabled for all chat endpoints
4. **`MedChatbot.js`** - Frontend updated for structured consultation
5. **`MedChatbot.css`** - Added disclaimer styling

## Important Notes

⚠️ **Medical Disclaimer**: This system is for informational purposes only and does not replace professional medical diagnosis. Always consult with a licensed healthcare professional for diagnosis and treatment.

🔒 **Privacy**: All consultation data is stored in session memory and cleared when the session ends. No data is permanently stored.

🌍 **Multilingual**: The system automatically detects and responds in the user's language.

## Testing

To test the structured consultation:

1. Start the med backend: `python main.py` (in `med/backend`)
2. Start the frontend: `npm start` (in `frontend`)
3. Navigate to Medical Health Assistant
4. Begin a consultation by typing any message
5. Answer questions one at a time as they appear

## Troubleshooting

### Questions not appearing in order
- Check that `questions.json` exists in `med/backend/`
- Verify `ENABLE_QUESTION_FLOW=true` in `.env`
- Check backend logs for initialization messages

### AI not waiting for answers
- Ensure question flow is enabled (check backend logs)
- Verify `use_question_flow: true` is sent from frontend
- Check that `question_flow_engine.py` loaded successfully

### Missing dependencies
- Run `pip install -r requirements.txt` in `med/backend/venv`
- Ensure all LangChain packages are installed





