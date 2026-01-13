"""
Chatbot Engine using LangChain + OpenAI ChatGPT
Handles conversation flow, memory, and multi-language support
Now includes LangGraph-based question flow engine
"""

import os
from typing import List, Dict, Optional, AsyncGenerator
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, AIMessage
from dotenv import load_dotenv
import re

# Import question flow engine
try:
    from question_flow_engine import QuestionFlowEngine
    QUESTION_FLOW_AVAILABLE = True
except ImportError:
    QUESTION_FLOW_AVAILABLE = False
    print("⚠ Warning: Question flow engine not available")

# Import MongoDB service - ALWAYS try to import and verify
MONGODB_AVAILABLE = False
mongodb_service = None

try:
    from mongodb_service import mongodb_service
    # Verify the service is actually available and connected
    if mongodb_service and hasattr(mongodb_service, 'responses_collection') and mongodb_service.responses_collection is not None:
        MONGODB_AVAILABLE = True
        print("[OK] MongoDB service imported and verified - ready to save consultation results")
    else:
        MONGODB_AVAILABLE = False
        print("[WARN] MongoDB service imported but collection is None - will retry at runtime")
except ImportError as e:
    MONGODB_AVAILABLE = False
    print(f"[WARN] MongoDB service import failed (ImportError): {e} - will retry at runtime")
except Exception as e:
    MONGODB_AVAILABLE = False
    print(f"[WARN] MongoDB service import failed: {e} - will retry at runtime")

load_dotenv()


class ChatbotEngine:
    """
    Main chatbot engine powered by OpenAI ChatGPT and LangChain
    Now supports LangGraph-based automatic question flow
    """
    
    def __init__(self, enable_question_flow: bool = True):
        """
        Initialize the chatbot engine
        
        Args:
            enable_question_flow: If True, enables LangGraph question flow mode (default: True for medical consultations)
        """
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        # Initialize OpenAI ChatGPT - Fast and powerful
        self.llm = ChatOpenAI(
            model="gpt-3.5-turbo",  # Fast, cost-effective model (or use "gpt-4" for best quality)
            temperature=0.7,
            openai_api_key=self.openai_api_key
        )
        
        # Initialize question flow engine (enabled by default for structured medical consultations)
        self.enable_question_flow = enable_question_flow and QUESTION_FLOW_AVAILABLE
        self.question_flow_engine = None
        self.question_flow_sessions: Dict[str, Dict] = {}  # Store session states
        
        # Temporary storage for all Q&A pairs per user (ensures nothing is lost)
        # Structure: {user_email: {question: answer, ...}}
        self.temp_qa_storage: Dict[str, Dict[str, str]] = {}
        
        # Temporary storage for all Q&A pairs per user (ensures nothing is lost)
        # Structure: {user_email: {question: answer, ...}}
        self.temp_qa_storage: Dict[str, Dict[str, str]] = {}
        
        if self.enable_question_flow:
            try:
                self.question_flow_engine = QuestionFlowEngine()
                print("✓ LangGraph question flow engine initialized - Structured medical consultation enabled")
                print(f"✓ Total questions available: {len(self.question_flow_engine.questions)}")
                # Verify first question is correct
                first_q_id = list(self.question_flow_engine.questions.keys())[0]
                first_q = self.question_flow_engine.questions[first_q_id]
                print(f"✓ First question: {first_q_id} - {first_q['question'][:80]}...")
            except Exception as e:
                print(f"⚠ ERROR: Could not initialize question flow engine: {e}")
                import traceback
                traceback.print_exc()
                print(f"⚠ CRITICAL: Falling back to standard chat mode - this may cause unstructured questions!")
                print(f"⚠ The chatbot may ask 'What is your name?' instead of using structured flow")
                self.enable_question_flow = False
                self.question_flow_engine = None
        else:
            # Question flow disabled - chatbot works in normal mode
            print("⚠ Question flow disabled - using standard chat mode")
        
        # Create custom prompt template for medical assistant chatbot
        self.prompt_template = PromptTemplate(
            input_variables=["history", "input"],
            template="""You are a professional Medical Assistant conducting a structured doctor-patient consultation. Your role is to systematically gather comprehensive medical information through a structured question flow.

CRITICAL RULES:
1. Ask ONE question at a time - wait for the patient's response before proceeding
2. Follow the structured consultation flow: Introduction → Demographics → Chief Complaint → History of Present Illness → Past Medical History → Medications → Allergies → Family History → Social History → Review of Systems → Vital Signs → Assessment
3. Be empathetic, professional, and supportive
4. Do NOT diagnose or provide treatment recommendations
5. For emergencies (chest pain, difficulty breathing, severe trauma, loss of consciousness), immediately advise seeking emergency medical care
6. Automatically detect the language of the user's input and respond in the SAME language
7. Maintain patient confidentiality and privacy
8. Always remind users that this is for informational purposes only and not a substitute for professional medical diagnosis
9. DO NOT ask for the patient's name - this is not needed for medical consultation
10. Start with: "Are you ready to begin?" - do NOT ask for name, age, or any other information first

CONSULTATION FLOW:
- Start with introduction and readiness check: "Are you ready to begin?"
- Collect basic demographics (age, gender) - DO NOT ask for name
- Identify chief complaint (main reason for visit)
- Gather detailed history of present illness (onset, nature, severity, triggers, associated symptoms, treatments tried)
- Review past medical history (chronic conditions, surgeries)
- Document current medications and supplements
- Check for allergies
- Review family history
- Assess social history (smoking, alcohol, occupation)
- Conduct review of systems (weight, appetite, sleep, energy, bowel/bladder)
- Collect vital signs if available
- Final assessment and summary

Conversation History:
{history}

User: {input}
Assistant:"""
        )
    
    def _format_history(self, history: List[Dict]) -> str:
        """Format conversation history for the prompt"""
        formatted = []
        for msg in history[-10:]:  # Keep last 10 messages
            role = "User" if msg["role"] == "user" else "Assistant"
            formatted.append(f"{role}: {msg['content']}")
        return "\n".join(formatted)
    
    def _detect_language(self, text: str) -> str:
        """
        Simple language detection based on character patterns
        In production, consider using langdetect or similar library
        """
        # Check for common language patterns
        if re.search(r'[\u0900-\u097F]', text):  # Devanagari (Hindi)
            return "hi"
        elif re.search(r'[\u0C00-\u0C7F]', text):  # Telugu
            return "te"
        elif re.search(r'[\u4E00-\u9FFF]', text):  # Chinese
            return "zh"
        elif re.search(r'[\u3040-\u309F\u30A0-\u30FF]', text):  # Japanese
            return "ja"
        elif re.search(r'[\uAC00-\uD7AF]', text):  # Korean
            return "ko"
        elif re.search(r'[\u0600-\u06FF]', text):  # Arabic
            return "ar"
        elif re.search(r'[\u0590-\u05FF]', text):  # Hebrew
            return "he"
        elif re.search(r'[\u0400-\u04FF]', text):  # Cyrillic (Russian)
            return "ru"
        else:
            return "en"  # Default to English
    
    async def get_response(
        self,
        message: str,
        history: List[Dict],
        language: str = "auto",
        session_id: Optional[str] = None,
        use_question_flow: Optional[bool] = None,
        user_email: Optional[str] = None  # User's email to save answers in user document
    ) -> Dict:
        """
        Get chatbot response for a message
        
        Args:
            message: User's input message
            history: Conversation history
            language: Preferred language (auto-detect if "auto")
            session_id: Session ID for question flow state management
            use_question_flow: Override question flow setting (None = use default)
        
        Returns:
            Dict with response and detected language
        """
        try:
            # Check if question flow should be used (enabled by default for medical consultations)
            should_use_flow = use_question_flow if use_question_flow is not None else self.enable_question_flow
            
            # CRITICAL: Always use question flow if available and session_id provided
            if should_use_flow and self.question_flow_engine and session_id:
                print(f"✓ Using question flow for session: {session_id}")
                # Use LangGraph question flow
                result = await self._get_response_with_question_flow(
                    message, history, language, session_id, user_email
                )
                response_text = result.get('response', '')
                print(f"✓ Question flow returned response: {response_text[:100]}...")
                
                # CRITICAL: If response contains "name" question, something is wrong
                if 'name' in response_text.lower() and ('what' in response_text.lower() or 'your name' in response_text.lower()):
                    print(f"⚠ ERROR: Question flow returned a 'name' question - this should not happen!")
                    print(f"   Response: {response_text}")
                    print(f"   This suggests the question flow is not working correctly")
                    # Force use the first question from questions.json
                    available = self.question_flow_engine._get_available_questions(set())
                    if available:
                        sorted_questions = self.question_flow_engine._sort_questions_by_order(available)
                        first_question = sorted_questions[0]
                        result["response"] = first_question["question"]
                        result["current_question_id"] = first_question["id"]
                        print(f"✓ Fixed: Using first question from questions.json: {first_question['id']}")
                
                return result
            elif not self.question_flow_engine:
                print(f"⚠ ERROR: Question flow engine not available")
                print(f"   Returning hardcoded first question from questions.json")
                print(f"   This ensures structured consultation starts correctly")
                # Return first question directly - DO NOT use LLM (prevents name questions)
                # Use first question label (AA_1) instead of hardcoded "intro_1"
                return {
                    "response": "Hello! I'm your Medical Assistant. I'll be conducting a structured consultation to better understand your health concerns. This will help me provide you with appropriate guidance. Please note that this is for informational purposes only and does not replace professional medical diagnosis. Are you ready to begin?",
                    "detected_language": self._detect_language(message) if language == "auto" else language,
                    "current_question_id": "AA_1"  # First question label
                }
            elif not session_id:
                print(f"⚠ ERROR: No session_id provided")
                print(f"   Returning hardcoded first question from questions.json")
                print(f"   Session ID is required for structured consultation")
                # Return first question directly - DO NOT use LLM (prevents name questions)
                # Use first question label (AA_1) instead of hardcoded "intro_1"
                return {
                    "response": "Hello! I'm your Medical Assistant. I'll be conducting a structured consultation to better understand your health concerns. This will help me provide you with appropriate guidance. Please note that this is for informational purposes only and does not replace professional medical diagnosis. Are you ready to begin?",
                    "detected_language": self._detect_language(message) if language == "auto" else language,
                    "current_question_id": "AA_1"  # First question label
                }
            
            # CRITICAL: Never use LLM fallback for medical consultations
            # This prevents unstructured questions like "What is your name?"
            # If we reach here, something is seriously wrong - return first question
            print(f"⚠ CRITICAL ERROR: Reached unexpected code path")
            print(f"   Returning hardcoded first question to prevent name questions")
            # Use first question label (AA_1) instead of hardcoded "intro_1"
            return {
                "response": "Hello! I'm your Medical Assistant. I'll be conducting a structured consultation to better understand your health concerns. This will help me provide you with appropriate guidance. Please note that this is for informational purposes only and does not replace professional medical diagnosis. Are you ready to begin?",
                "detected_language": self._detect_language(message) if language == "auto" else language,
                "current_question_id": "AA_1"  # First question label
            }
        
        except Exception as e:
            print(f"⚠ ERROR in get_response: {str(e)}")
            import traceback
            traceback.print_exc()
            # CRITICAL: Even on error, return first question - never use LLM or ask for name
            return {
                "response": "Hello! I'm your Medical Assistant. I'll be conducting a structured consultation to better understand your health concerns. This will help me provide you with appropriate guidance. Please note that this is for informational purposes only and does not replace professional medical diagnosis. Are you ready to begin?",
                "detected_language": language if language != "auto" else "en",
                "current_question_id": "AA_1",  # First question label
                "error": str(e)
            }
    
    async def _get_response_with_question_flow(
        self,
        message: str,
        history: List[Dict],
        language: str,
        session_id: str,
        user_email: Optional[str] = None  # User's email to save answers in user document
    ) -> Dict:
        """
        Get response using LangGraph question flow engine
        
        Flow: JSON questions -> Trivial model judge -> Store answers -> Ollama embeddings
        """
        try:
            # Get or create session state
            if session_id not in self.question_flow_sessions:
                self.question_flow_sessions[session_id] = {
                    "answered_questions": [],  # Questions that have been answered (stored as list for JSON)
                    "asked_questions": [],      # Questions that have been asked (stored as list for JSON)
                    "answers": {},
                    "question_embeddings": {},
                    "messages": [],
                    "current_question_id": None
                }
                print(f"✓ Created new session state for {session_id}")
            else:
                print(f"✓ Loaded existing session state for {session_id}")
            
            # CRITICAL: Create a deep copy of session state to work with
            # This prevents mutations from affecting the stored state until we explicitly save
            import copy
            session_state = copy.deepcopy(self.question_flow_sessions[session_id])
            
            # Convert lists back to sets for easier manipulation
            if isinstance(session_state.get("answered_questions"), list):
                session_state["answered_questions"] = set(session_state["answered_questions"])
            if isinstance(session_state.get("asked_questions"), list):
                session_state["asked_questions"] = set(session_state["asked_questions"])
            
            print(f"\n{'='*80}")
            print(f"📂 LOADED SESSION STATE (DEEP COPY)")
            print(f"   Session ID: {session_id}")
            print(f"   Current Question ID: {session_state.get('current_question_id')}")
            print(f"   Asked Questions ({len(session_state.get('asked_questions', []))}): {list(session_state.get('asked_questions', []))}")
            print(f"   Answered Questions ({len(session_state.get('answered_questions', []))}): {list(session_state.get('answered_questions', []))}")
            print(f"   Answers: {list(session_state.get('answers', {}).keys())}")
            print(f"{'='*80}\n")
            
            # CRITICAL: Create DEEP copy of current session state to track what was asked BEFORE processing
            # This prevents asking the same question twice in the current session
            # Deep copy ensures we have independent copies of nested structures (sets, dicts)
            previous_session_state = copy.deepcopy(session_state)
            previous_answered_questions = set(previous_session_state.get("answered_questions", []))
            previous_asked_questions = set(previous_session_state.get("asked_questions", []))
            if isinstance(previous_answered_questions, list):
                previous_answered_questions = set(previous_answered_questions)
            if isinstance(previous_asked_questions, list):
                previous_asked_questions = set(previous_asked_questions)
            previous_answers = copy.deepcopy(previous_session_state.get("answers", {}))
            previous_current_q = previous_session_state.get("current_question_id")
            
            print(f"📋 Previous session state (DEEP copy): answered={list(previous_answered_questions)}, asked={list(previous_asked_questions)}, current_q={previous_current_q}, answers={list(previous_answers.keys())}")
            
            # CRITICAL: Track current question-answer pair in temporary storage
            # This ensures we capture the exact question asked and answer given
            current_qa_pair = None
            if previous_current_q and message and message.strip():
                # User is answering a question - get the ACTUAL question text that was shown in chat
                # First try to get it from session state (the actual question from chat response)
                question_text = None
                if "current_question_text" in session_state and previous_current_q in session_state["current_question_text"]:
                    question_text = session_state["current_question_text"][previous_current_q]
                    print(f"[QA-PAIR] Using ACTUAL question text from chat: '{question_text[:50]}...'")
                else:
                    # Fallback: get from JSON file if not stored
                    question_data = self.question_flow_engine.questions.get(previous_current_q) if self.question_flow_engine else None
                    if question_data:
                        question_text = question_data.get("question", previous_current_q)
                        print(f"[QA-PAIR] Using question from JSON file (fallback): '{question_text[:50]}...'")
                    else:
                        question_text = previous_current_q
                        print(f"[QA-PAIR] Using label as question (last resort): '{question_text}'")
                
                if question_text:
                    answer_text = message.strip()
                    current_qa_pair = {"question": question_text, "answer": answer_text}
                    print(f"[QA-PAIR] Captured Q&A: Q='{question_text[:50]}...' A='{answer_text[:50]}...'")
                    
                    # Store in temporary storage immediately
                    if user_email:
                        if user_email not in self.temp_qa_storage:
                            self.temp_qa_storage[user_email] = {}
                        # Store question as key, answer as value
                        self.temp_qa_storage[user_email][question_text] = answer_text
                        print(f"[QA-PAIR] Stored in temp storage: {len(self.temp_qa_storage[user_email])} total Q&A pairs")
            
            # Convert set to list for JSON serialization in session state
            if isinstance(session_state.get("answered_questions"), set):
                session_state["answered_questions"] = list(session_state["answered_questions"])
            
            # Check if this is the very first message (greeting/start)
            # CRITICAL: Check if we have a current_question_id OR asked_questions - if so, it's NOT the first message
            answered_count = len(session_state.get("answered_questions", []))
            asked_count = len(session_state.get("asked_questions", []))
            current_q_id = session_state.get("current_question_id")
            has_answers = len(session_state.get("answers", {})) > 0
            
            # CRITICAL: If we have a current_question_id OR asked_questions, we're NOT on the first message
            # This is the KEY fix - if current_question_id or asked_questions exists, force is_first_message = False
            if current_q_id is not None or asked_count > 0:
                is_first_message = False
                print(f"⚠ CRITICAL FIX: current_question_id={current_q_id}, asked_count={asked_count} - Forcing is_first_message=False to prevent loop.")
            else:
                is_first_message = answered_count == 0 and not has_answers
            
            print(f"📋 First message check: answered_count={answered_count}, asked_count={asked_count}, current_q_id={current_q_id}, has_answers={has_answers}, is_first={is_first_message}")
            print(f"   Session state keys: {list(session_state.keys())}")
            print(f"   Asked questions: {list(session_state.get('asked_questions', []))}")
            print(f"   Answers: {list(session_state.get('answers', {}).keys())}")
            
            # CRITICAL: Double-check - if current_question_id exists, we MUST process it as an answer, not first message
            if current_q_id is not None:
                print(f"⚠ CRITICAL: current_question_id={current_q_id} exists! This is NOT a first message - will process as answer.")
                is_first_message = False
            
            # For medical chatbot: If first message, immediately start structured consultation
            if is_first_message:
                print(f"✓ First message detected - starting structured consultation flow")
                # Process the first message - will immediately ask first question from questions.json
                flow_result = await self.question_flow_engine.process_message(
                    message, session_state, thread_id=session_id
                )
                
                print(f"✓ First question flow result: response={flow_result.get('response', '')[:100]}..., current_q={flow_result.get('current_question_id')}")
                
                # CRITICAL: After asking the first question, mark it in session_state
                # This ensures the question is tracked as "asked" even if not yet answered
                if flow_result.get("current_question_id"):
                    first_q_id = flow_result["current_question_id"]
                    session_state["current_question_id"] = first_q_id
                    # Mark as ASKED (not answered yet, but asked)
                    if "asked_questions" not in session_state:
                        session_state["asked_questions"] = set()
                    if isinstance(session_state["asked_questions"], list):
                        session_state["asked_questions"] = set(session_state["asked_questions"])
                    session_state["asked_questions"].add(first_q_id)
                    print(f"\n{'='*80}")
                    print(f"🔵 MARKING FIRST QUESTION: {first_q_id}")
                    print(f"   Question text: {self.question_flow_engine.questions.get(first_q_id, {}).get('question', 'N/A')[:80]}...")
                    print(f"   Added to asked_questions: {list(session_state['asked_questions'])}")
                    print(f"   Set current_question_id: {first_q_id}")
                    
                    # CRITICAL: Save state IMMEDIATELY after marking question as asked
                    # This ensures the state is persisted before returning
                    import copy
                    session_state_to_save = copy.deepcopy(session_state)
                    # Convert sets to lists for JSON serialization
                    if isinstance(session_state_to_save.get("asked_questions"), set):
                        session_state_to_save["asked_questions"] = list(session_state_to_save["asked_questions"])
                    if isinstance(session_state_to_save.get("answered_questions"), set):
                        session_state_to_save["answered_questions"] = list(session_state_to_save["answered_questions"])
                    self.question_flow_sessions[session_id] = session_state_to_save
                    print(f"   ✅ SAVED to session storage")
                    print(f"   Saved state: current_q={session_state_to_save.get('current_question_id')}, asked={session_state_to_save.get('asked_questions')}")
                    print(f"{'='*80}\n")
                
                # Ensure we have a response
                if not flow_result.get("response"):
                    print(f"⚠ No response from question flow, using fallback")
                    # Fallback: get first question directly using proper sorting
                    available = self.question_flow_engine._get_available_questions(set())
                    if available:
                        sorted_questions = self.question_flow_engine._sort_questions_by_order(available)
                        first_question = sorted_questions[0]
                        flow_result["response"] = first_question["question"]
                        flow_result["current_question_id"] = first_question["id"]
                        print(f"✓ Fallback: Using first question: {first_question['id']} - {first_question['question'][:60]}...")
                    else:
                        flow_result["response"] = "Hello! I'm your Medical Assistant. I'll guide you through a structured consultation. Are you ready to begin?"
                        print(f"⚠ No questions available in questions.json!")
            else:
                # Process message through question flow
                # CRITICAL: This processes ONE answer and asks ONE next question, then STOPS
                # It does NOT loop - waits for next user message
                print(f"\n{'='*80}")
                print(f"📥 Processing user answer for session: {session_id}")
                print(f"{'='*80}")
                print(f"   Previous state (DEEP copy): answered={list(previous_answered_questions)}, asked={list(previous_asked_questions)}, current_q={previous_current_q}, answers={list(previous_answers.keys())}")
                print(f"   Current state before processing: answered={len(session_state.get('answered_questions', []))}, asked={len(session_state.get('asked_questions', []))}, current_q={session_state.get('current_question_id')}, answers={list(session_state.get('answers', {}).keys())}")
                
                # CRITICAL: If current_question_id exists, mark it as ANSWERED BEFORE processing
                # This prevents the question from being asked again in the current session
                if previous_current_q:
                    # Ensure this question is in asked_questions (should already be there)
                    if "asked_questions" not in session_state:
                        session_state["asked_questions"] = set()
                    if isinstance(session_state["asked_questions"], list):
                        session_state["asked_questions"] = set(session_state["asked_questions"])
                    session_state["asked_questions"].add(previous_current_q)
                    print(f"\n🔵 MARKING QUESTION: {previous_current_q}")
                    print(f"   Added to asked_questions: {list(session_state['asked_questions'])}")
                    
                    # Mark as ANSWERED if not already answered
                    if previous_current_q not in previous_answered_questions:
                        if "answers" not in session_state:
                            session_state["answers"] = {}
                        # Store the answer for the current question
                        session_state["answers"][previous_current_q] = message
                        # Mark as answered
                        answered_set = set(session_state.get("answered_questions", []))
                        if isinstance(answered_set, list):
                            answered_set = set(answered_set)
                        answered_set.add(previous_current_q)
                        session_state["answered_questions"] = list(answered_set)
                        print(f"   ✅ PRE-MARKED question {previous_current_q} as ANSWERED with answer: '{message[:50]}...'")
                        print(f"   Answered questions now: {list(answered_set)}")
                    else:
                        print(f"   ℹ️  Question {previous_current_q} already answered, updating answer")
                        if "answers" not in session_state:
                            session_state["answers"] = {}
                        session_state["answers"][previous_current_q] = message
                    print(f"{'='*80}\n")
                
                flow_result = await self.question_flow_engine.process_message(
                    message, session_state, thread_id=session_id
                )
                print(f"📤 Question flow returned response: {flow_result.get('response', '')[:60]}..., current_q={flow_result.get('current_question_id')}")
                print(f"   State after processing: answered={len(flow_result.get('session_state', {}).get('answered_questions', []))}, current_q={flow_result.get('current_question_id')}")
                
                # CRITICAL: Track the NEW question being asked (if any)
                # This happens after processing, when a new question is selected
                new_current_q = flow_result.get('current_question_id')
                new_question_text = flow_result.get('response', '').strip()
                
                # If we have a new question being asked, store the ACTUAL question text from the chat response
                if new_current_q and new_question_text and new_current_q != previous_current_q:
                    # This is a new question being asked - use the ACTUAL text from the response
                    # Don't use the JSON file question, use what was actually shown in chat
                    actual_question_text = new_question_text
                    print(f"[QA-PAIR] New question being asked (from chat response): '{actual_question_text[:50]}...' (label: {new_current_q})")
                    # Store the ACTUAL question text in session state so we can match it with the answer later
                    if "current_question_text" not in session_state:
                        session_state["current_question_text"] = {}
                    session_state["current_question_text"][new_current_q] = actual_question_text
                    print(f"[QA-PAIR] Stored actual question text for label {new_current_q}: '{actual_question_text[:80]}...'")
            
            # Update session state - CRITICAL: Preserve answered questions and current question ID
            updated_session_state = flow_result.get("session_state", session_state)
            
            # CRITICAL: Merge all state from flow_result into session_state
            # This ensures current_question_id is ALWAYS saved when a question is asked
            if "current_question_id" in flow_result:
                session_state["current_question_id"] = flow_result["current_question_id"]
                print(f"✓ CRITICAL: Set current_question_id from flow_result: {flow_result['current_question_id']}")
            elif "current_question_id" in updated_session_state:
                session_state["current_question_id"] = updated_session_state["current_question_id"]
                print(f"✓ Set current_question_id from updated_session_state: {updated_session_state['current_question_id']}")
            
            # Ensure answered questions are properly tracked
            if "answered_questions" in updated_session_state:
                # Convert to set for proper tracking
                if isinstance(updated_session_state["answered_questions"], list):
                    answered_set = set(updated_session_state["answered_questions"])
                else:
                    answered_set = updated_session_state["answered_questions"]
                # Store back as list for JSON serialization
                session_state["answered_questions"] = list(answered_set)
            
            # Preserve answers - merge with existing
            if "answers" in updated_session_state:
                if "answers" not in session_state:
                    session_state["answers"] = {}
                # Merge answers - new answers take precedence
                session_state["answers"].update(updated_session_state["answers"])
            
            # CRITICAL: Update answered_questions to match all answers
            if "answers" in session_state:
                answered_set = set(session_state.get("answered_questions", []))
                for q_id in session_state["answers"].keys():
                    answered_set.add(q_id)
                session_state["answered_questions"] = list(answered_set)
                print(f"✓ Updated answered_questions to match answers: {list(answered_set)}")
            
            # CRITICAL: Save answers to MongoDB automatically after each question
            # Always try to save if we have valid Q&A pairs, regardless of initial MongoDB status
            print(f"[DEBUG] MongoDB save check: user_email={user_email}")
            print(f"[DEBUG] Session state answers: {list(session_state.get('answers', {}).keys())}")
            print(f"[DEBUG] Current Q&A pair: {current_qa_pair}")
            
            # CRITICAL: Build all_answers_by_question dictionary with ACTUAL question text as keys
            # Priority: 1) current_qa_pair (most reliable), 2) session_state answers converted from labels
            all_answers_by_question = {}
            
            # STEP 1: Always add current_qa_pair first (it has the actual question text from chat)
            if current_qa_pair:
                question_text = current_qa_pair.get("question", "").strip()
                answer_text = current_qa_pair.get("answer", "").strip()
                if question_text and answer_text and len(question_text) >= 20:
                    all_answers_by_question[question_text] = answer_text
                    print(f"[SAVE] ✓ Added current Q&A pair: '{question_text[:60]}...' = '{answer_text[:50]}...'")
                else:
                    print(f"[SAVE] ⚠ Current Q&A pair invalid: Q length={len(question_text)}, A length={len(answer_text)}")
            
            # STEP 2: Convert session_state answers (labels) to question text and add to dict
            if "answers" in session_state and session_state["answers"] and self.question_flow_engine:
                all_answers_by_label = session_state["answers"]
                print(f"[SAVE] Converting {len(all_answers_by_label)} answers from labels to question text...")
                
                # Get current_question_text mapping from session state
                question_text_map = session_state.get("current_question_text", {})
                
                for label, answer in all_answers_by_label.items():
                    # Skip if answer is invalid
                    if not answer or not isinstance(answer, str) or not answer.strip():
                        continue
                    
                    answer = answer.strip()
                    
                    # Try to get actual question text from session state first (what was shown in chat)
                    question_text = question_text_map.get(label)
                    
                    if not question_text:
                        # Fallback: get from JSON file
                        question_data = self.question_flow_engine.questions.get(label)
                        if question_data:
                            question_text = question_data.get("question", "").strip()
                    
                    # Validate question text
                    if question_text and len(question_text) >= 20:
                        # Only add if not already in dict (current_qa_pair takes priority)
                        if question_text not in all_answers_by_question:
                            all_answers_by_question[question_text] = answer
                            print(f"[SAVE] ✓ Added from label '{label}': '{question_text[:60]}...' = '{answer[:50]}...'")
                        else:
                            print(f"[SAVE] ⊙ Skipped duplicate question text from label '{label}' (already in dict)")
                    else:
                        print(f"[SAVE] ⚠ Skipped label '{label}' - invalid question text (length: {len(question_text) if question_text else 0})")
                    
            print(f"[SAVE] Final answers by question ({len(all_answers_by_question)} total): {list(all_answers_by_question.keys())[:3]}...")
                    
            # STEP 3: Save to MongoDB if we have valid Q&A pairs
            save_status = "no_answers"
            if all_answers_by_question and user_email:
                print(f"[SAVE] ⚡ ATTEMPTING TO SAVE {len(all_answers_by_question)} Q&A pairs for user: {user_email}")
                    
                # Store in temporary storage first (ensures nothing is lost)
                        if user_email not in self.temp_qa_storage:
                            self.temp_qa_storage[user_email] = {}
                        self.temp_qa_storage[user_email].update(all_answers_by_question)
                print(f"[TEMP] Stored {len(all_answers_by_question)} Q&A pairs in temp storage (total: {len(self.temp_qa_storage[user_email])})")
                    
                # Save to MongoDB
                        try:
                            from mongodb_service import mongodb_service as mongo_svc
                            if mongo_svc and mongo_svc.responses_collection is not None:
                        # Use all Q&A pairs from temp storage (includes previous + new)
                                all_qa_to_save = self.temp_qa_storage.get(user_email, all_answers_by_question)
                                print(f"[SAVE] Saving {len(all_qa_to_save)} Q&A pairs to MongoDB...")
                                
                                saved = mongo_svc.save_user_responses(user_email, session_id, all_qa_to_save)
                                
                                if saved:
                                    save_status = "saved"
                            print(f"[OK] ✓✓✓ SAVED {len(all_qa_to_save)} Q&A pairs to user document '{user_email}' ✓✓✓")
                                else:
                                    save_status = "failed"
                            print(f"[ERROR] ✗✗✗ SAVE FAILED for user '{user_email}' ✗✗✗")
                            else:
                        save_status = "no_mongodb"
                                print(f"[ERROR] MongoDB service or collection is None")
                except ImportError as e:
                    save_status = "no_mongodb"
                    print(f"[ERROR] MongoDB service not available: {e}")
                        except Exception as e:
                    save_status = "failed"
                    print(f"[ERROR] Exception saving to MongoDB: {e}")
                            import traceback
                            traceback.print_exc()
                        
                # Store save status in session state
                        if "save_status" not in session_state:
                            session_state["save_status"] = []
                        session_state["save_status"].append({
                            "status": save_status,
                            "count": len(all_answers_by_question),
                            "timestamp": datetime.now().isoformat()
                        })
            elif all_answers_by_question and not user_email:
                        save_status = "no_email"
                print(f"[WARN] ⚠️  No user email provided - answers NOT saved. User must be logged in.")
            elif not all_answers_by_question:
                print(f"[INFO] No valid Q&A pairs to save")
            
            # CRITICAL: Save session state IMMEDIATELY after updating
            # This ensures current_question_id and asked_questions are persisted before returning
            # Use deep copy to ensure we save the actual state, not a reference
            import copy
            # Ensure asked_questions and answered_questions are sets before deep copying
            if "asked_questions" in session_state:
                if isinstance(session_state["asked_questions"], list):
                    session_state["asked_questions"] = set(session_state["asked_questions"])
            if "answered_questions" in session_state:
                if isinstance(session_state["answered_questions"], list):
                    session_state["answered_questions"] = set(session_state["answered_questions"])
            
            # Create deep copy to ensure independent state
            session_state_copy = copy.deepcopy(session_state)
            
            # Convert sets to lists for JSON serialization
            if isinstance(session_state_copy.get("asked_questions"), set):
                session_state_copy["asked_questions"] = list(session_state_copy["asked_questions"])
            if isinstance(session_state_copy.get("answered_questions"), set):
                session_state_copy["answered_questions"] = list(session_state_copy["answered_questions"])
            
            # Save to session storage
            self.question_flow_sessions[session_id] = session_state_copy
            
            # Verify the save worked
            saved_state = self.question_flow_sessions.get(session_id, {})
            saved_current_q = saved_state.get("current_question_id")
            saved_asked = saved_state.get("asked_questions", [])
            saved_answered = saved_state.get("answered_questions", [])
            print(f"\n{'='*80}")
            print(f"💾 SESSION STATE SAVED (DEEP COPY)")
            print(f"   Session ID: {session_id}")
            print(f"   Current Question ID: {saved_current_q}")
            print(f"   Asked Questions ({len(saved_asked)}): {saved_asked}")
            print(f"   Answered Questions ({len(saved_answered)}): {saved_answered}")
            print(f"   Answers stored: {list(session_state_copy.get('answers', {}).keys())}")
            print(f"{'='*80}\n")
            expected_current_q = session_state.get("current_question_id")
            
            print(f"✓ Session state SAVED for {session_id}: answered={len(session_state.get('answered_questions', []))}, current_q={expected_current_q}, answers={list(session_state.get('answers', {}).keys())}")
            print(f"✓ Verification: Saved state has current_q={saved_current_q} (expected: {expected_current_q})")
            
            # Double-check: Verify current_question_id is set and saved correctly
            if expected_current_q is None:
                print(f"⚠ WARNING: current_question_id is None after state update! This will cause the question to be asked again.")
                # Try to get it from flow_result as last resort
                if "current_question_id" in flow_result:
                    session_state["current_question_id"] = flow_result["current_question_id"]
                    session_state_copy = copy.deepcopy(session_state)
                    self.question_flow_sessions[session_id] = session_state_copy
                    print(f"✓ Fixed: Set current_question_id from flow_result: {flow_result['current_question_id']}")
                    print(f"✓ Re-verified: Saved state has current_q={self.question_flow_sessions[session_id].get('current_question_id')}")
            elif saved_current_q != expected_current_q:
                print(f"⚠ ERROR: State save mismatch! Expected current_q={expected_current_q}, but saved has {saved_current_q}")
                # Force save again with correct value
                session_state["current_question_id"] = expected_current_q
                self.question_flow_sessions[session_id] = copy.deepcopy(session_state)
                print(f"✓ Force re-saved state with current_q={expected_current_q}")
            
            # Detect language
            detected_lang = self._detect_language(message) if language == "auto" else language
            
            # Format response
            response_text = flow_result.get("response", "")
            
            # CRITICAL: Remove any labels from response before returning
            # Labels (AA_1, BA_2, etc.) are internal only and must never be exposed
            response_dict = {
                "response": response_text,
                "detected_language": detected_lang,
                "session_state": session_state
            }
            # Remove current_question_id (which is a label) from response
            if "current_question_id" in flow_result:
                # Keep it in session_state for internal tracking, but don't expose in response
                pass  # Already in session_state, don't add to response dict
            
            # CRITICAL: Check if response contains name question - replace immediately
            if response_text and ('name' in response_text.lower() and ('what' in response_text.lower() or 'your name' in response_text.lower())):
                print(f"⚠ CRITICAL: Response contains name question! Replacing with first question.")
                print(f"   Original response: {response_text}")
                # Force use the first question from questions.json
                available = self.question_flow_engine._get_available_questions(
                    set(session_state.get("answered_questions", []))
                )
                if available:
                    sorted_questions = self.question_flow_engine._sort_questions_by_order(available)
                    first_question = sorted_questions[0]
                    response_text = first_question["question"]
                    flow_result["response"] = first_question["question"]
                    flow_result["current_question_id"] = first_question["id"]
                    session_state["current_question_id"] = first_question["id"]
                    print(f"✓ Replaced with first question: {first_question['id']} - {first_question['question'][:60]}...")
                else:
                    response_text = "Hello! I'm your Medical Assistant. I'll be conducting a structured consultation to better understand your health concerns. This will help me provide you with appropriate guidance. Please note that this is for informational purposes only and does not replace professional medical diagnosis. Are you ready to begin?"
                    flow_result["response"] = response_text
                    # Use first question label (AA_1) instead of hardcoded "intro_1"
                    available = self.question_flow_engine._get_available_questions(set())
                    if available:
                        sorted_questions = self.question_flow_engine._sort_questions_by_order(available)
                        first_label = sorted_questions[0]["id"]
                        flow_result["current_question_id"] = first_label
                        session_state["current_question_id"] = first_label
                    else:
                        flow_result["current_question_id"] = "AA_1"  # First question label
                        session_state["current_question_id"] = "AA_1"
            
            # If no response, try to get first question directly
            if not response_text:
                print("⚠ No response from flow_result, getting first question directly")
                available = self.question_flow_engine._get_available_questions(
                    set(session_state.get("answered_questions", []))
                )
                if available:
                    # Use proper sorting to ensure questions are in correct order
                    sorted_questions = self.question_flow_engine._sort_questions_by_order(available)
                    first_question = sorted_questions[0]
                    response_text = first_question["question"]
                    flow_result["current_question_id"] = first_question["id"]
                    print(f"✓ Got first question directly: {first_question['id']}")
                else:
                    response_text = "Hello! I'm your Medical Assistant. I'll guide you through a structured consultation. Are you ready to begin?"
                    print("⚠ No available questions found")
            
            # CRITICAL: Final check - ensure response never contains name question
            if response_text and ('name' in response_text.lower() and ('what' in response_text.lower() or 'your name' in response_text.lower())):
                print(f"⚠ FINAL CHECK: Response still contains name question! Forcing replacement.")
                response_text = "Hello! I'm your Medical Assistant. I'll be conducting a structured consultation to better understand your health concerns. This will help me provide you with appropriate guidance. Please note that this is for informational purposes only and does not replace professional medical diagnosis. Are you ready to begin?"
                # Use first question label (AA_1) instead of hardcoded "intro_1"
                available = self.question_flow_engine._get_available_questions(set())
                if available:
                    sorted_questions = self.question_flow_engine._sort_questions_by_order(available)
                    first_label = sorted_questions[0]["id"]
                    flow_result["current_question_id"] = first_label
                    session_state["current_question_id"] = first_label
                else:
                    flow_result["current_question_id"] = "AA_1"  # First question label
                    session_state["current_question_id"] = "AA_1"
            
            # Add flow metadata
            # Get save status from session state to show in response
            save_status_msg = ""
            if "save_status" in session_state and session_state["save_status"]:
                last_save = session_state["save_status"][-1]
                if last_save["status"] == "saved":
                    save_status_msg = f"\n\n[OK] Question answers saved ({last_save['count']} Q&A pairs)"
                elif last_save["status"] == "failed":
                    save_status_msg = f"\n\n[ERROR] Question answers failed to save"
                elif last_save["status"] == "no_email":
                    save_status_msg = f"\n\n[WARN] Please log in to save your answers"
            
            response_metadata = {
                "response": response_text + save_status_msg,  # Add save status to response
                "detected_language": detected_lang,
                "question_flow": {
                    "active": True,
                    "flow_complete": flow_result.get("flow_complete", False),
                    "answered_count": flow_result.get("answered_count", 0),
                    "total_questions": flow_result.get("total_questions", len(self.question_flow_engine.questions)),
                    "embeddings_count": flow_result.get("embeddings_count", 0)
                    # CRITICAL: current_question_id is a label (AA_1, BA_2, etc.) - never expose in API
                }
            }
            
            # If flow is complete, add completion message
            if flow_result.get("flow_complete", False):
                response_metadata["response"] = (
                    f"✅ Thank you for completing the medical consultation. "
                    f"I've collected {flow_result.get('answered_count', 0)} pieces of information.\n\n"
                    f"**Important**: This consultation is for informational purposes only. "
                    f"Please consult with a licensed healthcare professional for diagnosis and treatment.\n\n"
                    f"Is there anything else you'd like to discuss?"
                )
            
            # CRITICAL: Remove any labels from response before returning
            # Labels (AA_1, BA_2, etc.) are internal only and must never be exposed
            if "current_question_id" in response_metadata:
                del response_metadata["current_question_id"]
            
            print(f"📤 Returning response: {response_text[:60]}...")
            return response_metadata
            
        except Exception as e:
            print(f"⚠ ERROR in question flow: {str(e)}")
            import traceback
            traceback.print_exc()
            # CRITICAL: Never use LLM fallback - return first question instead
            detected_lang = self._detect_language(message) if language == "auto" else language
            return {
                "response": "Hello! I'm your Medical Assistant. I'll be conducting a structured consultation to better understand your health concerns. This will help me provide you with appropriate guidance. Please note that this is for informational purposes only and does not replace professional medical diagnosis. Are you ready to begin?",
                "detected_language": detected_lang,
                "current_question_id": "AA_1",  # First question label
                "question_flow": {"active": False, "error": str(e)}
            }
    
    async def stream_response(
        self,
        message: str,
        history: List[Dict]
    ) -> AsyncGenerator[str, None]:
        """
        Stream chatbot response chunk by chunk (experimental)
        
        Args:
            message: User's input message
            history: Conversation history
        
        Yields:
            Response chunks
        """
        try:
            formatted_history = self._format_history(history)
            
            # Create a simple streaming version
            prompt = self.prompt_template.format(
                history=formatted_history,
                input=message
            )
            
            # For OpenAI, we'll simulate streaming by getting full response
            # and yielding in chunks (actual streaming requires different setup)
            messages = [HumanMessage(content=prompt)]
            response_obj = await self.llm.ainvoke(messages)
            response = response_obj.content
            
            # Yield response in chunks
            chunk_size = 10
            words = response.split()
            for i in range(0, len(words), chunk_size):
                chunk = " ".join(words[i:i + chunk_size]) + " "
                yield chunk
        
        except Exception as e:
            yield f"Error: {str(e)}"
    
    def get_question_flow_status(self, session_id: str) -> Optional[Dict]:
        """Get question flow status for a session"""
        if not self.enable_question_flow or not self.question_flow_engine:
            return None
        
        if session_id not in self.question_flow_sessions:
            return None
        
        session_state = self.question_flow_sessions[session_id]
        embeddings_store = self.question_flow_engine.get_embeddings_store()
        
        return {
            "answered_questions": list(session_state.get("answered_questions", set())),
            "answers": session_state.get("answers", {}),
            "total_embeddings": len(embeddings_store),
            "embeddings": embeddings_store
        }
    
    def reset_question_flow(self, session_id: Optional[str] = None):
        """Reset question flow for a session or all sessions"""
        if session_id:
            if session_id in self.question_flow_sessions:
                del self.question_flow_sessions[session_id]
        else:
            self.question_flow_sessions.clear()
        
        if self.question_flow_engine:
            self.question_flow_engine.reset_flow()
