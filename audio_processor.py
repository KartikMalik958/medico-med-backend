"""
Audio Processing Module
Handles speech-to-text (OpenAI Whisper API) and text-to-speech (gTTS)
"""

import os
import tempfile
from typing import Dict, Optional
from openai import AsyncOpenAI
from gtts import gTTS
from dotenv import load_dotenv
import asyncio
import sys

load_dotenv()


class AudioProcessor:
    """
    Handles audio transcription and text-to-speech conversion
    Uses OpenAI Whisper API
    """
    
    def __init__(self):
        """Initialize audio processor with OpenAI API"""
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        # Initialize OpenAI client
        self.openai_client = AsyncOpenAI(api_key=self.openai_api_key)
        
        print("✓ OpenAI Whisper API initialized successfully!")
    
    async def transcribe_audio(self, audio_file_path: str) -> Dict:
        """
        Transcribe audio file using OpenAI Whisper API
        
        Args:
            audio_file_path: Path to the audio file
        
        Returns:
            Dict with transcription text and detected language
        """
        try:
            # Open the audio file
            with open(audio_file_path, "rb") as audio_file:
                # Call OpenAI Whisper API
                transcription = await self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json"
                )
            
            return {
                "text": transcription.text.strip(),
                "language": transcription.language if hasattr(transcription, 'language') else "unknown"
            }
        
        except Exception as e:
            print(f"Error transcribing audio: {str(e)}")
            return {
                "text": "",
                "language": "unknown",
                "error": str(e)
            }
    
    async def text_to_speech(
        self,
        text: str,
        language: str = "auto",
        slow: bool = False
    ) -> str:
        """
        Convert text to speech using gTTS
        
        Args:
            text: Text to convert
            language: Language code (e.g., 'en', 'hi', 'es')
            slow: Speak slowly
        
        Returns:
            Path to generated audio file
        """
        try:
            # Map language codes if needed
            lang_map = {
                "auto": "en",
                "english": "en",
                "hindi": "hi",
                "spanish": "es",
                "french": "fr",
                "german": "de",
                "italian": "it",
                "japanese": "ja",
                "korean": "ko",
                "chinese": "zh",
                "arabic": "ar",
                "russian": "ru",
                "portuguese": "pt",
                "dutch": "nl",
                "turkish": "tr",
                "polish": "pl",
                "ukrainian": "uk",
                "swedish": "sv",
                "danish": "da",
                "norwegian": "no",
                "finnish": "fi"
            }
            
            # Get language code
            lang_code = lang_map.get(language.lower(), language)
            
            # Detect language from text if auto
            if lang_code == "en" and language == "auto":
                lang_code = self._detect_language_for_tts(text)
            
            # Create temporary file for audio
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            temp_file.close()
            
            # Generate speech using gTTS in thread pool (it's blocking)
            await asyncio.to_thread(
                self._generate_tts,
                text,
                lang_code,
                temp_file.name,
                slow
            )
            
            return temp_file.name
        
        except Exception as e:
            print(f"Error generating speech: {str(e)}")
            raise
    
    def _generate_tts(self, text: str, lang: str, filename: str, slow: bool):
        """Helper method to generate TTS (blocking operation)"""
        try:
            tts = gTTS(text=text, lang=lang, slow=slow)
            tts.save(filename)
        except Exception as e:
            # If language not supported, fallback to English
            print(f"Language '{lang}' not supported, using English. Error: {str(e)}")
            tts = gTTS(text=text, lang='en', slow=slow)
            tts.save(filename)
    
    def _detect_language_for_tts(self, text: str) -> str:
        """
        Detect language for TTS based on character patterns
        """
        import re
        
        # Check for common language patterns
        if re.search(r'[\u0900-\u097F]', text):  # Devanagari (Hindi)
            return "hi"
        elif re.search(r'[\u4E00-\u9FFF]', text):  # Chinese
            return "zh-CN"
        elif re.search(r'[\u3040-\u309F\u30A0-\u30FF]', text):  # Japanese
            return "ja"
        elif re.search(r'[\uAC00-\uD7AF]', text):  # Korean
            return "ko"
        elif re.search(r'[\u0600-\u06FF]', text):  # Arabic
            return "ar"
        elif re.search(r'[\u0400-\u04FF]', text):  # Cyrillic (Russian)
            return "ru"
        elif re.search(r'[\u0590-\u05FF]', text):  # Hebrew
            return "iw"
        else:
            return "en"  # Default to English
