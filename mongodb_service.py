"""
MongoDB Service for Medical Consultation Responses
Stores session responses with labeled categories/subcategories
"""

import os
from typing import Dict, Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from dotenv import load_dotenv
from datetime import datetime
from bson import ObjectId

load_dotenv()


class MongoDBService:
    """
    Service for storing and retrieving medical consultation responses
    Uses labeled categories/subcategories (A, AA, AB, etc.) internally
    """
    
    def __init__(self):
        """Initialize MongoDB connection"""
        # Use the same MongoDB URI as the main backend
        self.mongodb_uri = os.getenv(
            "MONGODB_URI",
            "mongodb+srv://kartikml420_db_user:lrgRxpzixAfC49BO@cluster0.w3i8zy8.mongodb.net/?appName=Cluster0"
        )
        
        try:
            self.client = MongoClient(self.mongodb_uri)
            # Use the same database and collection as main backend: Users.plsplspls
            self.db: Database = self.client["Users"]
            self.responses_collection: Collection = self.db["plsplspls"]
            
            # Create indexes for faster queries
            self.responses_collection.create_index("username")
            self.responses_collection.create_index("sessionId")
            
            print("[OK] MongoDB connection established: Users.plsplspls (same as main backend)")
        except Exception as e:
            print(f"[WARN] Warning: MongoDB connection failed: {e}")
            self.client = None
            self.db = None
            self.responses_collection = None
    
    def save_response(self, username: str, session_id: str, question_label: str, answer: str) -> bool:
        """
        Save a single question-answer pair to MongoDB
        
        Args:
            username: User's email/username
            session_id: Unique session identifier
            question_label: Label like "AA_1", "BA_2", etc.
            answer: User's answer text
            
        Returns:
            True if saved successfully, False otherwise
        """
        if self.responses_collection is None:
            print("[WARN] MongoDB not available, skipping save")
            return False
        
        try:
            # Find existing document for this username and session
            existing_doc = self.responses_collection.find_one({"username": username, "sessionId": session_id})
            
            if existing_doc:
                # Update existing document
                self.responses_collection.update_one(
                    {"username": username, "sessionId": session_id},
                    {
                        "$set": {
                            f"responses.{question_label}": answer,
                            "updatedAt": datetime.utcnow()
                        }
                    }
                )
            else:
                # Create new document
                self.responses_collection.insert_one({
                    "username": username,
                    "sessionId": session_id,
                    "responses": {
                        question_label: answer
                    },
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                })
            
            return True
        except Exception as e:
            print(f"[ERROR] Error saving response to MongoDB: {e}")
            return False
    
    def save_responses_batch(self, username: str, session_id: str, responses: Dict[str, str]) -> bool:
        """
        Save multiple question-answer pairs in a single operation
        
        Args:
            username: User's email/username
            session_id: Unique session identifier
            responses: Dictionary mapping question_text -> answer (questions as keys, answers as values)
            
        Returns:
            True if saved successfully, False otherwise
        """
        if self.responses_collection is None:
            print("[WARN] MongoDB not available, skipping batch save")
            return False
        
        if not responses:
            return True
        
        try:
            # Find existing document for this username and session
            existing_doc = self.responses_collection.find_one({"username": username, "sessionId": session_id})
            
            if existing_doc:
                # Update existing document with all responses
                update_dict = {f"responses.{label}": answer for label, answer in responses.items()}
                update_dict["updatedAt"] = datetime.utcnow()
                
                self.responses_collection.update_one(
                    {"username": username, "sessionId": session_id},
                    {"$set": update_dict}
                )
            else:
                # Create new document
                self.responses_collection.insert_one({
                    "username": username,
                    "sessionId": session_id,
                    "responses": responses,
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                })
            
            return True
        except Exception as e:
            print(f"[ERROR] Error saving batch responses to MongoDB: {e}")
            return False
    
    def save_user_responses(self, user_email: str, session_id: str, responses: Dict[str, str]) -> bool:
        """
        Save consultation results directly to the user's document in Users.plsplspls
        Uses email as primary key to find and update the user's existing document
        Stores question-answer pairs in consultation_results field (question text as key, answer as value)
        Also updates consultation_updated_at timestamp
        
        Requirements:
        - Only saves real questions that were actually shown (no placeholders)
        - Never saves empty strings, null, or placeholder answers
        - Supports random question order (order-agnostic)
        - Prevents duplicate keys for same question text
        - Atomic updates to avoid race conditions
        - Incremental updates (never replaces full document)
        
        Args:
            user_email: User's email (primary key - used to find user document)
            session_id: Session identifier (for tracking, but not used as key)
            responses: Dictionary mapping question_text -> answer (questions as keys, answers as values)
                      Question text must be the EXACT text shown to the user (not labels or placeholders)
            
        Returns:
            True if saved successfully, False otherwise
        """
        if self.responses_collection is None:
            print("[WARN] MongoDB not available, skipping user response save")
            return False
        
        if not responses:
            return True
        
        # CRITICAL: Filter out invalid entries before saving
        # Never save: placeholders, empty strings, null answers, or invalid question texts
        valid_responses = {}
        for question_text, answer in responses.items():
            # Skip if question is empty, None, or looks like a placeholder/label
            if not question_text or not isinstance(question_text, str):
                print(f"[SKIP] Invalid question text (empty or not string): {question_text}")
                continue
            
            # Skip if question looks like a label (e.g., "AA_1", "intro_1") instead of actual question text
            # Labels typically have underscore and short format, real questions are longer
            if len(question_text) < 20 and ('_' in question_text or question_text.isalnum()):
                print(f"[SKIP] Question appears to be a label, not actual text: '{question_text}'")
                continue
            
            # Skip if answer is empty, None, or invalid
            if not answer or not isinstance(answer, str) or not answer.strip():
                print(f"[SKIP] Invalid answer (empty or not string): '{answer}' for question: '{question_text[:50]}...'")
                continue
            
            # Skip placeholder answers
            answer_lower = answer.strip().lower()
            placeholder_indicators = ['placeholder', 'n/a', 'not applicable', 'none', 'null', 'undefined']
            if any(placeholder in answer_lower for placeholder in placeholder_indicators):
                print(f"[SKIP] Answer appears to be placeholder: '{answer}' for question: '{question_text[:50]}...'")
                continue
            
            # All checks passed - this is a valid question-answer pair
            valid_responses[question_text.strip()] = answer.strip()
        
        if not valid_responses:
            print("[WARN] No valid responses to save after filtering")
            return True  # Return True to avoid error, but nothing was saved
        
        try:
            print(f"[MongoDB] Looking for user with email: {user_email}")
            # Find existing user document by email (PRIMARY KEY)
            existing_user = self.responses_collection.find_one({"email": user_email})
            
            if existing_user:
                print(f"[MongoDB] [OK] Found user document for: {user_email}")
                
                # Get existing consultation_results to merge (preserve previous answers)
                existing_results = existing_user.get("consultation_results", {})
                if not isinstance(existing_results, dict):
                    existing_results = {}
                
                # Merge new responses with existing (new answers overwrite old ones for same question)
                # This ensures incremental updates without losing previous answers
                merged_results = existing_results.copy()
                merged_results.update(valid_responses)
                
                # Build update dict with atomic $set operation
                # Each question-answer pair is stored as consultation_results.{question_text} = answer
                update_dict = {}
                for question_text, answer in valid_responses.items():
                    # Use question text as key in consultation_results
                    # MongoDB dot notation: consultation_results.{question_text} = answer
                    update_dict[f"consultation_results.{question_text}"] = answer
                
                # Update timestamps
                update_dict["consultation_updated_at"] = datetime.utcnow()
                update_dict["updated_at"] = datetime.utcnow()
                
                print(f"[MongoDB] Updating with {len(update_dict)} fields ({len(valid_responses)} new Q&A pairs)...")
                
                # Atomic update operation - prevents race conditions
                result = self.responses_collection.update_one(
                    {"email": user_email},  # Use email as primary key
                    {"$set": update_dict}  # Atomic $set operation
                )
                
                print(f"[MongoDB] Update result - Matched: {result.matched_count}, Modified: {result.modified_count}")
                print(f"[OK] Updated user document (email: {user_email}) with {len(valid_responses)} consultation results")
                print(f"   Questions saved: {list(valid_responses.keys())[:3]}...")  # Show first 3 questions
                
                # Verify the update worked
                verify_user = self.responses_collection.find_one({"email": user_email})
                if verify_user and "consultation_results" in verify_user:
                    result_count = len(verify_user.get("consultation_results", {}))
                    print(f"[MongoDB] [OK] VERIFIED: consultation_results field exists with {result_count} entries")
                else:
                    print(f"[MongoDB] [WARN] WARNING: consultation_results field NOT found after update!")
                
                return True
            else:
                # User doesn't exist - this shouldn't happen if user is logged in
                # But create document with consultation results if needed
                print(f"[WARN] User document not found for email: {user_email}, creating new document")
                
                # Create new document with consultation_results
                # Questions as keys, answers as values
                result = self.responses_collection.insert_one({
                    "email": user_email,  # Email as primary key
                    "consultation_results": valid_responses,  # Questions as keys, answers as values
                    "consultation_updated_at": datetime.utcnow(),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                })
                print(f"[OK] Created new user document (email: {user_email}) with ID: {result.inserted_id}")
                print(f"[OK] Created with {len(valid_responses)} consultation results")
                return True
        except Exception as e:
            print(f"[ERROR] Error saving user responses to MongoDB: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_session_responses(self, username: str, session_id: str) -> Optional[Dict[str, str]]:
        """
        Retrieve all responses for a username and session
        
        Args:
            username: User's email/username
            session_id: Unique session identifier
            
        Returns:
            Dictionary mapping question_label -> answer, or None if not found
        """
        if self.responses_collection is None:
            return None
        
        try:
            doc = self.responses_collection.find_one({"username": username, "sessionId": session_id})
            if doc and "responses" in doc:
                return doc["responses"]
            return None
        except Exception as e:
            print(f"[ERROR] Error retrieving responses from MongoDB: {e}")
            return None
    
    def get_response(self, username: str, session_id: str, question_label: str) -> Optional[str]:
        """
        Retrieve a specific response by question label
        
        Args:
            username: User's email/username
            session_id: Unique session identifier
            question_label: Label like "AA_1", "BA_2", etc.
            
        Returns:
            Answer text or None if not found
        """
        responses = self.get_session_responses(username, session_id)
        if responses:
            return responses.get(question_label)
        return None
    
    def delete_session(self, username: str, session_id: str) -> bool:
        """
        Delete all responses for a username and session
        
        Args:
            username: User's email/username
            session_id: Unique session identifier
            
        Returns:
            True if deleted successfully, False otherwise
        """
        if self.responses_collection is None:
            return False
        
        try:
            result = self.responses_collection.delete_one({"username": username, "sessionId": session_id})
            return result.deleted_count > 0
        except Exception as e:
            print(f"[ERROR] Error deleting session from MongoDB: {e}")
            return False


# Global instance
mongodb_service = MongoDBService()

