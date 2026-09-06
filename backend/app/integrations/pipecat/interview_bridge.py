"""
Bridge between Pipecat pipeline and Interview Intelligence.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class InterviewBridge(ABC):
    @abstractmethod
    async def process_candidate_response(self, text: str, session_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_next_question(self, session_id: str) -> Optional[str]:
        pass

    @abstractmethod
    async def evaluate_answer(self, text: str, question_id: str, session_id: str) -> Dict[str, Any]:
        pass

class MockInterviewBridge(InterviewBridge):
    async def process_candidate_response(self, text: str, session_id: str) -> Dict[str, Any]:
        return {"status": "processed", "text": text}

    async def get_next_question(self, session_id: str) -> Optional[str]:
        return "Could you tell me about yourself?"

    async def evaluate_answer(self, text: str, question_id: str, session_id: str) -> Dict[str, Any]:
        return {"score": 0.8, "feedback": "Good response"}
