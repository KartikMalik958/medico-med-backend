"""
Quick test script to verify question flow engine is working
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test_question_flow():
    """Test the question flow engine"""
    try:
        from question_flow_engine import QuestionFlowEngine
        
        print("Testing Question Flow Engine...")
        engine = QuestionFlowEngine()
        
        print(f"\n✓ Loaded {len(engine.questions)} questions")
        print(f"✓ Flow order: {engine.questions_data.get('flow_order', [])}")
        
        # Test first question
        session_state = {
            "answered_questions": set(),
            "answers": {},
            "question_embeddings": {},
            "messages": [],
            "current_question_id": None
        }
        
        result = await engine.process_message("Hello", session_state, thread_id="test")
        
        print(f"\n✓ First question response:")
        print(f"  Response: {result.get('response', 'NO RESPONSE')[:100]}...")
        print(f"  Current Question ID: {result.get('current_question_id')}")
        print(f"  Total Questions: {result.get('total_questions')}")
        
        if result.get('response'):
            print("\n✅ Question flow engine is working!")
        else:
            print("\n❌ Question flow engine returned no response")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_question_flow())





