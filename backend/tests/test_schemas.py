"""
Tests for schemas.
"""
from app.schemas.voice_session import VoiceSessionSchema, InterviewStatus, ConnectionStatus
from app.schemas.stt import STTConfig, STTResult
from app.schemas.tts import TTSConfig, TTSResult

def test_voice_session_creation():
    session = VoiceSessionSchema(
        session_id="test_123",
        candidate_id="cand_1",
        job_id="job_1",
        language="en"
    )
    assert session.session_id == "test_123"
    assert session.interview_status == InterviewStatus.PENDING
    assert session.connection_status == ConnectionStatus.DISCONNECTED
    assert session.language == "en"
    
def test_stt_result_creation():
    result = STTResult(
        text="hello",
        language="en",
        confidence=0.99,
        processing_time_ms=10.0,
        provider="mock"
    )
    assert result.text == "hello"

def test_tts_result_creation():
    result = TTSResult(
        audio_data=b"audio",
        audio_format="wav",
        language="en",
        processing_time_ms=20.0,
        provider="mock",
        sample_rate=16000
    )
    assert result.audio_data == b"audio"
