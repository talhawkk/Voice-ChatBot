"""
Voice agent orchestration package.

- VoiceAgent: Legacy voice agent (separate STT -> LLM -> TTS calls)
- DeepgramVoiceAgent: Deepgram Voice Agent API (combined STT + LLM + TTS)
"""

from .voice_agent import VoiceAgent
from .deepgram_voice_agent import (
    DeepgramVoiceAgent,
    create_voice_agent,
    is_voice_agent_available
)

__all__ = [
    'VoiceAgent',
    'DeepgramVoiceAgent', 
    'create_voice_agent',
    'is_voice_agent_available'
]
