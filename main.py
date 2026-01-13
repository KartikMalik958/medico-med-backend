"""
Multilingual Voice + Text Chatbot Backend
FastAPI + LangChain + OpenAI ChatGPT + Whisper API
"""

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
import os
from dotenv import load_dotenv
import tempfile
import json
from datetime import datetime
import asyncio
import base64

# Import chatbot modules
from chatbot_engine import ChatbotEngine
from audio_processor import AudioProcessor

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="Multilingual Voice Chatbot API",
    description="ChatGPT-like chatbot with voice and text support",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize chatbot engine and audio processor
# Medical chatbot with question flow enabled by default for structured consultations
enable_question_flow = os.getenv("ENABLE_QUESTION_FLOW", "true").lower() == "true"
print(f"🔧 Initializing Medical Assistant with question flow: {'ENABLED' if enable_question_flow else 'DISABLED'}")
chatbot_engine = ChatbotEngine(enable_question_flow=enable_question_flow)
audio_processor = AudioProcessor()

# Store conversation sessions (in production, use Redis or a DB)
conversation_sessions: Dict[str, List[Dict]] = {}


# ---------- MODELS ----------

class TextChatRequest(BaseModel):
    message: str
    session_id: str
    language: Optional[str] = "auto"
    use_question_flow: Optional[bool] = None  # None = use default, True/False = override
    username: Optional[str] = None  # User's email for MongoDB storage (required to save in user document)


class ChatResponse(BaseModel):
    response: str
    detected_language: Optional[str] = None
    timestamp: str
    session_id: str


class SessionRequest(BaseModel):
    session_id: str


# ---------- ROUTES ----------

@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "online",
        "service": "Multilingual Voice Chatbot",
        "version": "1.0.0"
    }


@app.post("/api/chat/text", response_model=ChatResponse)
async def text_chat(request: TextChatRequest):
    """Handle text chat"""
    try:
        # Get or create conversation history
        history = conversation_sessions.setdefault(request.session_id, [])

        # Medical chatbot uses structured question flow by default for consultations
        # This ensures one question at a time, following doctor-patient consultation workflow
        use_flow = request.use_question_flow if request.use_question_flow is not None else chatbot_engine.enable_question_flow
        
        response = await chatbot_engine.get_response(
            message=request.message,
            history=history,
            language=request.language,
            session_id=request.session_id,
            use_question_flow=use_flow,
            user_email=request.username  # Pass user email to save in user document
        )
        
        # CRITICAL: Final safety check - never return name questions
        response_text = response.get("response", "")
        if response_text and ('name' in response_text.lower() and ('what' in response_text.lower() or 'your name' in response_text.lower())):
            print(f"⚠ CRITICAL: Backend received response with name question! Replacing.")
            response["response"] = "Hello! I'm your Medical Assistant. I'll be conducting a structured consultation to better understand your health concerns. This will help me provide you with appropriate guidance. Please note that this is for informational purposes only and does not replace professional medical diagnosis. Are you ready to begin?"
            # CRITICAL: Never expose labels in API responses - labels are internal only
            # Remove current_question_id from response if it exists (it's a label)
            if "current_question_id" in response:
                del response["current_question_id"]

        # Update conversation history
        history.extend([
            {"role": "user", "content": request.message, "timestamp": datetime.now().isoformat()},
            {"role": "assistant", "content": response["response"], "timestamp": datetime.now().isoformat()}
        ])

        # Trim history to recent messages
        max_history = int(os.getenv("MAX_CONVERSATION_HISTORY", "10"))
        if len(history) > max_history * 2:
            conversation_sessions[request.session_id] = history[-(max_history * 2):]

        return ChatResponse(
            response=response["response"],
            detected_language=response.get("detected_language"),
            timestamp=datetime.now().isoformat(),
            session_id=request.session_id
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")


@app.post("/api/chat/voice")
async def voice_chat(audio: UploadFile = File(...), session_id: str = Form("default")):
    """Handle voice chat"""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            content = await audio.read()
            temp_audio.write(content)
            temp_audio_path = temp_audio.name

        transcription = await audio_processor.transcribe_audio(temp_audio_path)
        os.unlink(temp_audio_path)

        if not transcription.get("text"):
            raise HTTPException(status_code=400, detail="Could not transcribe audio")

        history = conversation_sessions.setdefault(session_id, [])

        # Use structured question flow for voice chat as well
        # Get username from form data if available
        username = None
        try:
            form_data = await request.form()
            username = form_data.get("username")
        except:
            pass
        
        response = await chatbot_engine.get_response(
            message=transcription["text"],
            history=history,
            language=transcription.get("language", "auto"),
            session_id=session_id,
            use_question_flow=chatbot_engine.enable_question_flow,
            user_email=username  # Pass user email if available
        )

        # Update conversation history
        history.extend([
            {"role": "user", "content": transcription["text"], "timestamp": datetime.now().isoformat()},
            {"role": "assistant", "content": response["response"], "timestamp": datetime.now().isoformat()}
        ])

        # Trim history
        max_history = int(os.getenv("MAX_CONVERSATION_HISTORY", "10"))
        if len(history) > max_history * 2:
            conversation_sessions[session_id] = history[-(max_history * 2):]

        return {
            "transcription": transcription["text"],
            "response": response["response"],
            "detected_language": transcription.get("language"),
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing voice: {str(e)}")


@app.post("/api/tts")
async def text_to_speech(request: TextChatRequest):
    """Convert text to speech"""
    try:
        audio_path = await audio_processor.text_to_speech(
            text=request.message,
            language=request.language or "auto"
        )
        return FileResponse(audio_path, media_type="audio/mpeg", filename="response.mp3")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating speech: {str(e)}")


@app.post("/api/chat/history")
async def get_chat_history(request: SessionRequest):
    """Retrieve chat history"""
    try:
        history = conversation_sessions.get(request.session_id, [])
        return {"history": history, "session_id": request.session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving history: {str(e)}")


@app.delete("/api/chat/clear")
async def clear_chat_history(request: SessionRequest):
    """Clear chat history"""
    try:
        conversation_sessions[request.session_id] = []
        # Also reset question flow if active
        chatbot_engine.reset_question_flow(request.session_id)
        return {"message": "Chat history cleared", "session_id": request.session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing history: {str(e)}")


@app.get("/api/chat/question-flow/status")
async def get_question_flow_status(session_id: str):
    """Get question flow status for a session"""
    try:
        status = chatbot_engine.get_question_flow_status(session_id)
        if status is None:
            return {"active": False, "message": "Question flow not active for this session"}
        return {
            "active": True,
            "session_id": session_id,
            "status": status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting question flow status: {str(e)}")


@app.post("/api/chat/question-flow/reset")
async def reset_question_flow(request: SessionRequest):
    """Reset question flow for a session"""
    try:
        chatbot_engine.reset_question_flow(request.session_id)
        return {"message": "Question flow reset", "session_id": request.session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resetting question flow: {str(e)}")


@app.get("/api/chat/stream/text")
async def stream_text_chat(message: str, session_id: str = "default"):
    """Stream chatbot responses (experimental)"""
    async def event_generator():
        try:
            history = conversation_sessions.setdefault(session_id, [])
            async for chunk in chatbot_engine.stream_response(message, history):
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket):
    """WebSocket endpoint for live voice chat"""
    await websocket.accept()
    session_id = f"ws_{datetime.now().timestamp()}"
    conversation_sessions.setdefault(session_id, [])

    try:
        await websocket.send_json({"type": "connection", "message": "Connected", "session_id": session_id})

        while True:
            data = await websocket.receive_json()

            if data.get("type") == "audio_chunk":
                try:
                    audio_data = base64.b64decode(data.get("audio", ""))
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio:
                        temp_audio.write(audio_data)
                        temp_audio_path = temp_audio.name

                    transcription = await audio_processor.transcribe_audio(temp_audio_path)
                    os.unlink(temp_audio_path)

                    await websocket.send_json({
                        "type": "transcription",
                        "text": transcription["text"],
                        "language": transcription.get("language", "unknown")
                    })

                    response = await chatbot_engine.get_response(
                        message=transcription["text"],
                        history=conversation_sessions[session_id],
                        language=transcription.get("language", "auto"),
                        session_id=session_id,
                        use_question_flow=False  # Question flow disabled for WebSocket
                    )

                    # Update conversation
                    conversation_sessions[session_id].extend([
                        {"role": "user", "content": transcription["text"], "timestamp": datetime.now().isoformat()},
                        {"role": "assistant", "content": response["response"], "timestamp": datetime.now().isoformat()}
                    ])

                    await websocket.send_json({
                        "type": "response",
                        "text": response["response"],
                        "language": response.get("detected_language", "unknown")
                    })

                    # Generate TTS
                    try:
                        audio_path = await audio_processor.text_to_speech(
                            text=response["response"],
                            language=response.get("detected_language", "auto")
                        )
                        with open(audio_path, "rb") as audio_file:
                            audio_base64 = base64.b64encode(audio_file.read()).decode("utf-8")
                        os.unlink(audio_path)
                        await websocket.send_json({"type": "tts_audio", "audio": audio_base64})
                    except Exception as e:
                        print(f"TTS error: {e}")

                except Exception as e:
                    await websocket.send_json({"type": "error", "message": f"Audio error: {str(e)}"})

            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

            elif data.get("type") == "clear_history":
                conversation_sessions[session_id] = []
                await websocket.send_json({"type": "history_cleared", "message": "History cleared"})

    except WebSocketDisconnect:
        print(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        print(f"WebSocket error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", os.getenv("BACKEND_PORT", "8001")))  # Render uses PORT, local uses BACKEND_PORT
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
