"""
Tests for schemas.
"""
from app.schemas.voice_session import VoiceSessionSchema, VoiceSessionStartResponse, InterviewStatus, ConnectionStatus
from app.schemas.stt import STTConfig, STTResult
from app.schemas.tts import TTSConfig, TTSResult

def test_voice_session_creation():
    session = VoiceSessionSchema(
        session_id="test_123",
        application_id=1,
        candidate_id="5",
        job_id="7",
        language="en"
    )
    assert session.application_id == 1
    assert session.candidate_id == "5"
    assert session.job_id == "7"
    assert session.session_id == "test_123"
    assert session.interview_status == InterviewStatus.PENDING
    assert session.connection_status == ConnectionStatus.DISCONNECTED
    assert session.language == "en"
    assert "token" not in session.model_dump()


def test_voice_session_start_response_join_contract():
    payload = VoiceSessionStartResponse(
        status="started",
        session_id="sess-1",
        livekit_url="wss://example.livekit.cloud",
        room_name="interview-sess-1",
        token="join-token",
        identity="candidate-cand_1",
    )
    dumped = payload.model_dump()
    assert dumped == {
        "status": "started",
        "session_id": "sess-1",
        "livekit_url": "wss://example.livekit.cloud",
        "room_name": "interview-sess-1",
        "token": "join-token",
        "identity": "candidate-cand_1",
    }


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
