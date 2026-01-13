"""
LangGraph-based Question Flow Engine
Implements: JSON questions -> Trivial model judge -> Store answers -> Ollama embeddings
"""

import os
import json
from typing import List, Dict, Optional, Set, TypedDict, Annotated
from pathlib import Path
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import operator

# Try to import Ollama (optional - will fallback to OpenAI if not available)
try:
    from langchain_ollama import OllamaEmbeddings, ChatOllama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("Warning: Ollama not available, will use OpenAI embeddings as fallback")

load_dotenv()


class QuestionFlowState(TypedDict):
    """State for the question flow graph"""
    messages: List  # List of messages (HumanMessage, AIMessage)
    answered_questions: Set[str]
    current_question_id: Optional[str]
    answers: Dict[str, str]
    question_embeddings: Dict[str, List[float]]
    all_question_embeddings: List[Dict[str, any]]
    flow_complete: bool


class QuestionFlowEngine:
    """
    LangGraph-based engine that automatically asks next relevant question
    Flow: JSON questions -> Trivial model judge -> Store answers -> Ollama embeddings
    """
    
    def __init__(self, questions_file: str = "questions.json"):
        """Initialize the question flow engine"""
        self.questions_file = questions_file
        self.questions_data = self._load_questions()
        # Flatten the nested structure into a flat questions map with labels as keys
        self.questions = self._flatten_questions()
        
        # Handle dependencies and priorities for both old and new structures
        if self.questions_data.get("question_dependencies"):
            # New structure with explicit dependencies and priorities
            self.dependencies = self.questions_data.get("question_dependencies", {})
            self.priorities = self.questions_data.get("question_priorities", {})
            self.flow_order = self.questions_data.get("flow_order", [])
        else:
            # Old structure - build dependencies and priorities from questions array
            self.dependencies = {}
            self.priorities = {}
            questions_list = self.questions_data.get("questions", [])
            for q in questions_list:
                old_id = q.get("id", "")
                # Find the new label for this question
                new_label = None
                for label, q_data in self.questions.items():
                    if q_data.get("old_id") == old_id:
                        new_label = label
                        break
                
                if new_label:
                    # Map old dependencies to new labels
                    old_deps = q.get("dependencies", [])
                    new_deps = []
                    for old_dep in old_deps:
                        for label, q_data in self.questions.items():
                            if q_data.get("old_id") == old_dep:
                                new_deps.append(label)
                                break
                    self.dependencies[new_label] = new_deps
                    self.priorities[new_label] = q.get("priority", 1)
            
            # Build flow_order from categories
            category_to_label = {
                "introduction": "A",
                "demographics": "B",
                "chief_complaint": "C",
                "history_of_present_illness": "D",
                "past_medical_history": "E",
                "medications": "F",
                "allergies": "G",
                "family_history": "H",
                "social_history": "I",
                "review_of_systems": "J",
                "vital_signs": "K",
                "assessment": "L"
            }
            self.flow_order = []
            for cat in self.questions_data.get("flow_order", []):
                if cat in category_to_label:
                    self.flow_order.append(category_to_label[cat])
        print(f"[OK] Question Flow Engine initialized: {len(self.questions)} questions loaded")
        if self.questions:
            first_label = list(self.questions.keys())[0]
            print(f"[OK] First question: {first_label} - {self.questions[first_label]['question'][:60]}...")
        
        # Initialize models
        # Trivial model for judging next question (using smaller/faster model)
        self.judge_model = ChatOpenAI(
            model="gpt-3.5-turbo",  # Can be replaced with even smaller model
            temperature=0.3,  # Lower temperature for more consistent judgments
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # Main model for conversation
        self.main_model = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0.7,
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # Ollama embeddings model (with fallback to OpenAI)
        if OLLAMA_AVAILABLE:
            try:
                self.embeddings_model = OllamaEmbeddings(
                    model="nomic-embed-text"  # Default Ollama embedding model
                )
                print("[OK] Ollama embeddings model initialized")
            except Exception as e:
                print(f"[WARN] Ollama initialization failed, using OpenAI embeddings: {e}")
                # Fallback to OpenAI embeddings if Ollama not available
                from langchain_openai import OpenAIEmbeddings
                self.embeddings_model = OpenAIEmbeddings(
                    openai_api_key=os.getenv("OPENAI_API_KEY")
                )
        else:
            # Use OpenAI embeddings as fallback
            from langchain_openai import OpenAIEmbeddings
            self.embeddings_model = OpenAIEmbeddings(
                openai_api_key=os.getenv("OPENAI_API_KEY")
            )
            print("[OK] Using OpenAI embeddings (Ollama not installed)")
        
        # Initialize memory/checkpointing for LangGraph
        self.memory = MemorySaver()
        
        # Build LangGraph workflow with checkpointing
        self.workflow = self._build_graph()
        
        # Store embeddings for all answers
        self.answer_embeddings_store: List[Dict[str, any]] = []
    
    def _load_questions(self) -> Dict:
        """Load questions from JSON file"""
        # Try to find questions.json in root or backend directory
        root_path = Path(__file__).parent.parent / self.questions_file
        backend_path = Path(__file__).parent / self.questions_file
        
        if root_path.exists():
            with open(root_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        elif backend_path.exists():
            with open(backend_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            raise FileNotFoundError(f"Questions file not found: {self.questions_file}")
    
    def _flatten_questions(self) -> Dict[str, Dict]:
        """
        Flatten the nested category/subcategory structure into a flat map
        Returns: {label: {question: text, category: A, subcategory: AA, ...}}
        Supports both old structure (questions array) and new structure (categories object)
        """
        questions_map = {}
        
        # Check if new structure exists (categories object)
        categories = self.questions_data.get("categories")
        questions_list = self.questions_data.get("questions", [])
        
        # Check if categories is a non-empty dict (new structure)
        # But also check if it has the expected nested structure (subcategories -> questions)
        has_nested_structure = False
        if categories is not None and isinstance(categories, dict) and len(categories) > 0:
            # Check if it has the nested structure (subcategories -> questions)
            for cat_data in categories.values():
                if isinstance(cat_data, dict) and "subcategories" in cat_data:
                    has_nested_structure = True
                    break
        
        if has_nested_structure:
            # New structure: categories -> subcategories -> questions
            for cat_label, cat_data in categories.items():
                cat_title = cat_data.get("title", "")
                subcategories = cat_data.get("subcategories", {})
                
                for subcat_label, subcat_data in subcategories.items():
                    subcat_title = subcat_data.get("title", "")
                    questions = subcat_data.get("questions", {})
                    
                    for question_label, question_text in questions.items():
                        questions_map[question_label] = {
                            "question": question_text,  # Only question text for display
                            "category": cat_label,      # A, B, C, etc.
                            "category_title": cat_title,
                            "subcategory": subcat_label,  # AA, AB, etc.
                            "subcategory_title": subcat_title,
                            "label": question_label     # AA_1, BA_1, etc. (internal only)
                        }
        elif questions_list and isinstance(questions_list, list) and len(questions_list) > 0:
            # Old structure: questions array - convert to new format with labels
            # Map old IDs to new labels based on category
            category_to_label = {
                "introduction": "A",
                "demographics": "B",
                "chief_complaint": "C",
                "history_of_present_illness": "D",
                "past_medical_history": "E",
                "medications": "F",
                "allergies": "G",
                "family_history": "H",
                "social_history": "I",
                "review_of_systems": "J",
                "vital_signs": "K",
                "assessment": "L"
            }
            
            # Group questions by category and assign labels
            category_counts = {}
            for q in questions_list:
                old_id = q.get("id", "")
                category = q.get("category", "")
                question_text = q.get("question", "")
                
                # Get category label (A, B, C, etc.)
                cat_label = category_to_label.get(category, "Z")
                
                # Count questions in this category to assign subcategory (AA, AB, etc.)
                if category not in category_counts:
                    category_counts[category] = {}
                    category_counts[category]["count"] = 0
                    category_counts[category]["subcat"] = "AA"
                
                # Assign subcategory label
                subcat_label = category_counts[category]["subcat"]
                category_counts[category]["count"] += 1
                
                # Create question label (AA_1, AA_2, etc.)
                q_num = category_counts[category]["count"]
                question_label = f"{subcat_label}_{q_num}"
                
                # Move to next subcategory if needed (every 5 questions or when category changes)
                if category_counts[category]["count"] % 5 == 0:
                    # Increment subcategory (AA -> AB -> AC, etc.)
                    subcat_letter = ord(subcat_label[1]) + 1
                    if subcat_letter > ord('Z'):
                        subcat_letter = ord('A')
                    category_counts[category]["subcat"] = subcat_label[0] + chr(subcat_letter)
                
                questions_map[question_label] = {
                    "question": question_text,
                    "category": cat_label,
                    "category_title": category.replace("_", " ").title(),
                    "subcategory": subcat_label,
                    "subcategory_title": category.replace("_", " ").title(),
                    "label": question_label,
                    "old_id": old_id  # Keep old ID for reference
                }
        
        if not questions_map:
            print(f"[ERROR] No questions found in questions.json! Check file structure.")
            print(f"   File has 'categories': {categories is not None}")
            print(f"   Categories is dict: {isinstance(categories, dict) if categories is not None else False}")
            print(f"   File has 'questions': {bool(self.questions_data.get('questions'))}")
            print(f"   Questions length: {len(questions_list) if isinstance(questions_list, list) else 0}")
        
        return questions_map
    
    def _get_available_questions(self, answered_questions: Set[str]) -> List[Dict]:
        """Get questions that can be asked (dependencies satisfied)"""
        # TESTING: Limit to 2 questions for now
        MAX_QUESTIONS = 2
        
        # Ensure answered_questions is a set
        if isinstance(answered_questions, list):
            answered_questions = set(answered_questions)
        
        # Stop if we've already answered MAX_QUESTIONS
        if len(answered_questions) >= MAX_QUESTIONS:
            print(f"[TEST] Already answered {len(answered_questions)} questions (MAX: {MAX_QUESTIONS}) - no more questions")
            return []
        
        available = []
        for question_label, question_data in self.questions.items():
            # Skip if already answered
            if question_label in answered_questions:
                continue
            
            # Check if dependencies are satisfied
            deps = self.dependencies.get(question_label, [])
            if all(dep in answered_questions for dep in deps):
                # Create question dict with label as id for compatibility
                q_dict = {
                    "id": question_label,  # Use label as id internally
                    "question": question_data["question"],
                    "category": question_data["category"],
                    "subcategory": question_data["subcategory"],
                    "label": question_label
                }
                available.append(q_dict)
                
                # TESTING: Stop after finding MAX_QUESTIONS available questions
                if len(available) >= MAX_QUESTIONS:
                    break
        
        print(f"[TEST] Available questions: {len(available)} (answered: {len(answered_questions)}, MAX: {MAX_QUESTIONS})")
        return available
    
    def _sort_questions_by_order(self, questions: List[Dict]) -> List[Dict]:
        """
        Sort questions by proper order: category (A, B, C...) -> priority -> question number
        This ensures questions are asked in the correct structured order
        """
        category_order_map = {cat: idx for idx, cat in enumerate(self.flow_order)}
        
        def sort_key(q):
            question_label = q.get("id", "")  # Label like "AA_1", "BA_2", etc.
            category = q.get("category", "")    # A, B, C, etc.
            category_order = category_order_map.get(category, 999)
            priority = self.priorities.get(question_label, 999)
            
            # Extract number from label (format: "AA_1", "BA_2", etc.)
            try:
                if "_" in question_label:
                    q_num = int(question_label.split("_")[1])
                else:
                    q_num = 999
            except:
                q_num = 999
            
            return (category_order, priority, q_num)
        
        return sorted(questions, key=sort_key)
    
    def _judge_next_question(
        self, 
        available_questions: List[Dict], 
        conversation_history: List[Dict],
        current_answers: Dict[str, str]
    ) -> Optional[str]:
        """
        Select next question following strict order from questions.json
        Order: personal_info → medical_history → symptoms → additional_info
        Follows file order strictly as per medical assistant requirements
        """
        if not available_questions:
            return None
        
        # Sort available questions using the proper order function
        sorted_questions = self._sort_questions_by_order(available_questions)
        
        if sorted_questions:
            # Return the first question in the sorted order (strict file order)
            selected_id = sorted_questions[0]["id"]  # This is the label (AA_1, BA_2, etc.)
            selected_q = sorted_questions[0]
            priority = self.priorities.get(selected_id, 0)
            print(f"\n{'='*80}")
            print(f"🎯 SELECTED NEXT QUESTION: {selected_id}")
            print(f"   Question: {selected_q['question'][:80]}...")
            print(f"   Category: {selected_q['category']}, Subcategory: {selected_q['subcategory']}, Priority: {priority}")
            print(f"   Label: {selected_id} (internal only, never exposed)")
            print(f"{'='*80}\n")
            return selected_id
        
        return None
    
    def _store_answer_with_embedding(self, question_id: str, answer: str):
        """Store answer and convert to embedding using Ollama"""
        try:
            # Generate embedding for the answer
            embedding = self.embeddings_model.embed_query(answer)
            
            # Store in embeddings store
            question_data = self.questions.get(question_id, {})
            answer_data = {
                "question_id": question_id,  # Label like "AA_1", "BA_2", etc.
                "question": question_data.get("question", ""),
                "answer": answer,
                "embedding": embedding,
                "category": question_data.get("category", ""),  # A, B, C, etc.
                "subcategory": question_data.get("subcategory", "")  # AA, AB, etc.
            }
            
            self.answer_embeddings_store.append(answer_data)
            
            print(f"✓ Stored answer for {question_id} with embedding (dim: {len(embedding)})")
            return embedding
        except Exception as e:
            print(f"Error storing embedding: {e}")
            return None
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow"""
        workflow = StateGraph(QuestionFlowState)
        
        # Add nodes
        workflow.add_node("process_answer", self._process_answer_node)
        workflow.add_node("select_question", self._select_question_node)
        workflow.add_node("ask_question", self._ask_question_node)
        workflow.add_node("check_completion", self._check_completion_node)
        
        # Define edges - process answer first, then select and ask next question
        workflow.set_entry_point("process_answer")
        workflow.add_edge("process_answer", "select_question")
        workflow.add_edge("select_question", "ask_question")
        workflow.add_edge("ask_question", "check_completion")
        workflow.add_conditional_edges(
            "check_completion",
            self._should_continue,
            {
                "continue": END,  # End after asking question, wait for user response
                "end": END
            }
        )
        
        return workflow.compile()
    
    def _select_question_node(self, state: QuestionFlowState) -> QuestionFlowState:
        """Select next question using judge model"""
        # Ensure answered_questions is a set
        answered = state.get("answered_questions", set())
        if isinstance(answered, list):
            answered = set(answered)
        
        # CRITICAL: Also add all questions that have answers to the answered set
        # This ensures consistency - if there's an answer, the question is considered answered
        answers_dict = state.get("answers", {})
        for q_id in answers_dict.keys():
            answered.add(q_id)
        state["answered_questions"] = answered  # Update state with merged set
        
        print(f"🔍 Selecting next question. Answered: {list(answered)} (from answered_questions + answers dict)")
        print(f"   Answers dict has: {list(answers_dict.keys())}")
        
        available = self._get_available_questions(answered)
        
        if not available:
            state["flow_complete"] = True
            state["current_question_id"] = None
            print("✓ No more questions available - flow complete")
            return state
        
        # Use judge model to select next question
        conversation_history = [
            {"question_id": qid, "content": answer}
            for qid, answer in state.get("answers", {}).items()
        ]
        
        selected_id = self._judge_next_question(
            available, 
            conversation_history,
            state.get("answers", {})
        )
        
        # CRITICAL: Verify selected question is not already answered
        if selected_id and selected_id in answered:
            print(f"⚠ ERROR: Selected question {selected_id} is already answered!")
            print(f"   This should not happen - question selection logic has a bug")
            print(f"   Answered set: {list(answered)}")
            print(f"   Available questions: {[q['id'] for q in available]}")
            # Remove from available and select next using proper sorting
            available = [q for q in available if q["id"] != selected_id]
            if available:
                sorted_questions = self._sort_questions_by_order(available)
                selected_id = sorted_questions[0]["id"]
                print(f"   Fixed: Selected next question: {selected_id}")
            else:
                selected_id = None
                print(f"   No more questions available")
        
        if selected_id and selected_id in [q["id"] for q in available]:
            state["current_question_id"] = selected_id
            print(f"✓ Selected next question: {selected_id} - {self.questions[selected_id]['question'][:60]}...")
        else:
            # Fallback to first available using proper sorting
            sorted_questions = self._sort_questions_by_order(available)
            if sorted_questions:
                state["current_question_id"] = sorted_questions[0]["id"]
                print(f"✓ Fallback selected question: {state['current_question_id']} - {sorted_questions[0]['question'][:60]}...")
            else:
                state["current_question_id"] = None
                state["flow_complete"] = True
        
        return state
    
    def _ask_question_node(self, state: QuestionFlowState) -> QuestionFlowState:
        """Ask the selected question"""
        question_id = state.get("current_question_id")
        if question_id and question_id in self.questions:
            question_text = self.questions[question_id]["question"]
            state["messages"].append(AIMessage(content=question_text))
            
            # CRITICAL: Mark this question as ASKED (not answered yet, but asked)
            # This prevents it from being asked again
            if "asked_questions" not in state:
                state["asked_questions"] = set()
            if isinstance(state["asked_questions"], list):
                state["asked_questions"] = set(state["asked_questions"])
            state["asked_questions"].add(question_id)
            print(f"\n{'='*80}")
            print(f"🔵 ASKING QUESTION: {question_id}")
            print(f"   Question: {question_text[:80]}...")
            print(f"   Added to asked_questions: {list(state['asked_questions'])}")
            print(f"   Current asked_questions count: {len(state['asked_questions'])}")
            print(f"{'='*80}\n")
        return state
    
    def _process_answer_node(self, state: QuestionFlowState) -> QuestionFlowState:
        """Process user's answer and store with embedding"""
        # Get the last user message as answer
        messages = state.get("messages", [])
        if not messages:
            return state
        
        # Find the last HumanMessage (user's answer)
        last_user_message = None
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                last_user_message = msg
                break
        
        if not last_user_message:
            return state
        
        answer = last_user_message.content
        
        # Get answered questions set
        answered_set = state.get("answered_questions", set())
        if isinstance(answered_set, list):
            answered_set = set(answered_set)
        
        # Try to find which question this answers
        # First, check if there's a current_question_id from previous state
        question_id = state.get("current_question_id")
        
        # If no current_question_id, try to find it from the message history
        if not question_id:
            # Look for the last AIMessage (the question that was asked)
            for i in range(len(messages) - 1, -1, -1):
                msg = messages[i]
                if isinstance(msg, AIMessage):
                    question_text = msg.content
                    # Try to match with questions
                    for q_id, q_data in self.questions.items():
                        if q_data["question"] == question_text or q_data["question"][:50] in question_text:
                            question_id = q_id
                            state["current_question_id"] = q_id
                            break
                    if question_id:
                        break
        
        # Process the answer if we have a question_id
        if question_id:
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
            
            # Store with embedding (only if not already stored to avoid duplicate work)
            if question_id not in state.get("question_embeddings", {}):
                embedding = self._store_answer_with_embedding(question_id, answer)
                if embedding:
                    if "question_embeddings" not in state:
                        state["question_embeddings"] = {}
                    state["question_embeddings"][question_id] = embedding
            
            was_already_answered = question_id in answered_set
            if was_already_answered:
                print(f"✓ Updated answer for already-answered question {question_id}: {answer[:50]}...")
            else:
                print(f"✓ Processed NEW answer for question {question_id}: {answer[:50]}...")
        else:
            print(f"⚠ ERROR: Could not determine which question was answered for: {answer[:50]}...")
            print(f"   State keys: {list(state.keys())}")
            print(f"   Messages count: {len(messages)}")
            print(f"   This might cause the question to be repeated!")
        
        return state
    
    def _check_completion_node(self, state: QuestionFlowState) -> QuestionFlowState:
        """Check if flow is complete"""
        answered = state.get("answered_questions", set())
        available = self._get_available_questions(answered)
        
        if not available:
            state["flow_complete"] = True
        else:
            state["flow_complete"] = False
        
        return state
    
    def _should_continue(self, state: QuestionFlowState) -> str:
        """
        Determine if we should continue asking questions
        CRITICAL: Always return "continue" which maps to END in workflow
        This ensures the workflow stops after asking ONE question and waits for user response
        """
        # Both "continue" and "end" map to END in the workflow
        # This prevents event loops - workflow stops after asking one question
        if state.get("flow_complete", False):
            return "end"  # All questions answered
        return "continue"  # Stop after asking this question, wait for user
    
    async def process_message(
        self, 
        user_message: str, 
        session_state: Optional[Dict] = None,
        thread_id: Optional[str] = None
    ) -> Dict:
        """
        Process user message and return next question or response
        
        Args:
            user_message: User's input
            session_state: Current session state (answers, answered_questions, etc.)
        
        Returns:
            Dict with response, next_question, flow_status, etc.
        """
        # Initialize or get session state
        if session_state is None:
            session_state = {
                "answered_questions": set(),
                "answers": {},
                "question_embeddings": {},
                "messages": [],
                "current_question_id": None
            }
        
        # Convert list back to set if needed (for compatibility)
        answered_questions = session_state.get("answered_questions", set())
        if isinstance(answered_questions, list):
            answered_questions = set(answered_questions)
        
        # Check if this is the first interaction (no questions answered yet AND no current question)
        # CRITICAL: If we have a current_question_id, we're answering a question, not starting fresh
        current_q_id_from_state = session_state.get("current_question_id")
        is_first_interaction = len(answered_questions) == 0 and current_q_id_from_state is None
        
        print(f"🔍 First interaction check: answered_count={len(answered_questions)}, current_q_id={current_q_id_from_state}, is_first={is_first_interaction}")
        
        # If first interaction, immediately start structured consultation
        if is_first_interaction:
            # Get the first question from questions.json (intro_1)
            available = self._get_available_questions(set())
            if available:
                # Get first question by category order and priority
                sorted_questions = self._sort_questions_by_order(available)
                first_question = sorted_questions[0]
                question_text = first_question["question"]
                
                print(f"✓ First question selected: {first_question['id']} - {question_text[:60]}...")
                
                # Update session state
                session_state["messages"] = session_state.get("messages", []) + [
                    user_message,
                    question_text
                ]
                first_q_id = first_question["id"]
                session_state["current_question_id"] = first_q_id
                # Mark as ASKED
                if "asked_questions" not in session_state:
                    session_state["asked_questions"] = set()
                if isinstance(session_state["asked_questions"], list):
                    session_state["asked_questions"] = set(session_state["asked_questions"])
                session_state["asked_questions"].add(first_q_id)
                print(f"✓ Marked first question {first_q_id} as ASKED")
                
                return {
                    "response": question_text,
                    "next_question": question_text,
                    "flow_complete": False,
                    "answered_count": 0,
                    "total_questions": len(self.questions),
                    "session_state": session_state,
                    "embeddings_count": len(self.answer_embeddings_store),
                    "current_question_id": first_question["id"]
                }
            else:
                # Fallback if no questions available
                error_msg = f"Error: No questions available. Questions file loaded: {len(self.questions)} questions found."
                print(f"⚠ {error_msg}")
                return {
                    "response": "Hello! I'm your Medical Assistant. I'll guide you through a structured consultation. Are you ready to begin?",
                    "next_question": None,
                    "flow_complete": False,
                    "answered_count": 0,
                    "total_questions": len(self.questions),
                    "session_state": session_state,
                    "embeddings_count": 0,
                    "current_question_id": None,
                    "error": error_msg
                }
        
        # For subsequent interactions, process the answer and ask next question
        # IMPORTANT: Get the current_question_id from session state (the question that was just asked)
        current_q_id = session_state.get("current_question_id")
        print(f"📝 Processing answer for question: {current_q_id}, User message: {user_message[:50]}...")
        print(f"📊 Current answered questions: {list(answered_questions)}")
        print(f"📊 Current answers in session: {list(session_state.get('answers', {}).keys())}")
        
        # CRITICAL: If we have a current question ID, mark it as answered BEFORE processing
        # This ensures the question won't be selected again
        if current_q_id:
            if current_q_id not in answered_questions:
                # Store the answer immediately
                if "answers" not in session_state:
                    session_state["answers"] = {}
                session_state["answers"][current_q_id] = user_message
                answered_questions.add(current_q_id)
                print(f"✓ Marked question {current_q_id} as answered with answer: {user_message[:50]}...")
            else:
                print(f"⚠ Question {current_q_id} already in answered_questions, but processing answer anyway")
                # Still update the answer in case it changed
                if "answers" not in session_state:
                    session_state["answers"] = {}
                session_state["answers"][current_q_id] = user_message
        else:
            print(f"⚠ WARNING: No current_question_id found in session state! This might cause issues.")
            print(f"   Session state keys: {list(session_state.keys())}")
        
        # Add user message to state
        initial_state = {
            "messages": session_state.get("messages", []) + [HumanMessage(content=user_message)],
            "answered_questions": answered_questions,  # Use updated set with current question marked
            "answers": session_state.get("answers", {}),
            "question_embeddings": session_state.get("question_embeddings", {}),
            "current_question_id": current_q_id,  # PRESERVE current question ID for answer processing
            "flow_complete": False,
            "all_question_embeddings": self.answer_embeddings_store
        }
        print(f"📦 Initial state prepared: answered={list(answered_questions)}, current_q={current_q_id}")
        
        # Run the workflow with checkpointing (memory)
        # Use thread_id for session management - use session_id as thread_id
        thread_id_for_memory = thread_id or session_state.get("thread_id", "default")
        config = {"configurable": {"thread_id": thread_id_for_memory}}
        
        try:
            # Get current state from LangGraph memory if exists
            try:
                current_state = self.workflow.get_state(config)
                if current_state and current_state.values:
                    # Merge with existing state from LangGraph memory
                    existing = current_state.values
                    # CRITICAL: Merge answered questions - don't overwrite, merge sets
                    if existing.get("answered_questions"):
                        existing_answered = existing["answered_questions"]
                        if isinstance(existing_answered, set):
                            existing_answered_set = existing_answered
                        elif isinstance(existing_answered, list):
                            existing_answered_set = set(existing_answered)
                        else:
                            existing_answered_set = set()
                        # Merge with current answered questions
                        answered_questions = answered_questions.union(existing_answered_set)
                        initial_state["answered_questions"] = answered_questions
                        print(f"✓ Merged answered questions: {list(answered_questions)}")
                    # Preserve answers from memory - merge, don't overwrite
                    if existing.get("answers"):
                        # Merge answers - current answers take precedence
                        merged_answers = {**existing["answers"], **initial_state.get("answers", {})}
                        initial_state["answers"] = merged_answers
                        # Ensure all answers in merged_answers are in answered_questions
                        for q_id in merged_answers.keys():
                            answered_questions.add(q_id)
                        initial_state["answered_questions"] = answered_questions
                        print(f"✓ Merged answers: {list(merged_answers.keys())}")
                    # Preserve question embeddings
                    if existing.get("question_embeddings"):
                        initial_state["question_embeddings"] = {**existing["question_embeddings"], **initial_state.get("question_embeddings", {})}
                    # CRITICAL: Preserve current question ID from initial_state (the question being answered)
                    # Don't overwrite it with existing state - we want to process the answer to the current question
                    # Only use existing if we don't have one (shouldn't happen, but safety check)
                    if not initial_state.get("current_question_id") and existing.get("current_question_id"):
                        print(f"⚠ Using existing current_question_id from memory: {existing.get('current_question_id')}")
                        initial_state["current_question_id"] = existing["current_question_id"]
                    else:
                        print(f"✓ Preserving current_question_id from initial_state: {initial_state.get('current_question_id')}")
                    # Preserve messages from memory
                    if existing.get("messages"):
                        initial_state["messages"] = existing["messages"] + [HumanMessage(content=user_message)]
                    else:
                        initial_state["messages"] = [HumanMessage(content=user_message)]
                    initial_state["answered_questions"] = answered_questions
                    print(f"✓ Loaded state from LangGraph memory: {len(answered_questions)} questions answered")
            except Exception as e:
                print(f"⚠ No existing state in LangGraph memory, starting fresh: {e}")
                # No existing state, use initial_state as is
                initial_state["messages"] = [HumanMessage(content=user_message)]
            
            # Run workflow with checkpointing - state will be saved automatically
            final_state = await self.workflow.ainvoke(initial_state, config)
            print(f"✓ Workflow completed, state saved to memory (thread_id: {thread_id_for_memory})")
            
            # Extract response
            messages = final_state.get("messages", [])
            last_message = messages[-1] if messages else None
            
            response_text = ""
            next_question = None
            current_q_id = final_state.get("current_question_id")
            
            if isinstance(last_message, AIMessage):
                response_text = last_message.content
                next_question = response_text
            
            # Update session state (convert set to list for JSON serialization)
            answered_set = final_state.get("answered_questions", set())
            if isinstance(answered_set, list):
                answered_set = set(answered_set)
            
            # CRITICAL: Ensure all answers are reflected in answered_questions
            for q_id in final_state.get("answers", {}).keys():
                answered_set.add(q_id)
            
            session_state["answered_questions"] = list(answered_set)  # Store as list for JSON
            session_state["answers"] = final_state.get("answers", {})
            session_state["question_embeddings"] = final_state.get("question_embeddings", {})
            session_state["current_question_id"] = current_q_id  # CRITICAL: Preserve for next interaction
            session_state["messages"] = [msg.content if hasattr(msg, 'content') else str(msg) for msg in messages]
            
            # CRITICAL: Ensure current_question_id is always set if we have a response
            if current_q_id is None and response_text:
                # If we got a response but no current_question_id, something is wrong
                # Try to extract it from the response or use the first available question
                print(f"⚠ WARNING: Got response but no current_question_id! Response: {response_text[:60]}...")
                # Find which question matches this response
                for q_id, q_data in self.questions.items():
                    if q_data["question"] == response_text or q_data["question"][:50] in response_text:
                        current_q_id = q_id
                        session_state["current_question_id"] = q_id
                        print(f"✓ Found matching question: {q_id}")
                        break
            
            print(f"📊 Session state updated: {len(answered_set)} questions answered: {list(answered_set)}, current_q: {current_q_id}")
            
            return {
                "response": response_text,
                "next_question": next_question,
                "flow_complete": final_state.get("flow_complete", False),
                "answered_count": len(final_state.get("answered_questions", set())),
                "total_questions": len(self.questions),
                "session_state": session_state,
                "embeddings_count": len(self.answer_embeddings_store),
                "current_question_id": current_q_id
            }
        except Exception as e:
            print(f"Error in workflow: {e}")
            import traceback
            traceback.print_exc()
            return {
                "response": f"I encountered an error: {str(e)}",
                "next_question": None,
                "flow_complete": False,
                "error": str(e)
            }
    
    def get_embeddings_store(self) -> List[Dict]:
        """Get all stored answer embeddings"""
        return self.answer_embeddings_store
    
    def reset_flow(self):
        """Reset the question flow"""
        self.answer_embeddings_store = []

