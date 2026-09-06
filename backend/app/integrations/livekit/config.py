"""
LiveKit configuration.
"""
from pydantic import BaseModel, Field

class LiveKitConfig(BaseModel):
    url: str = Field(default="", description="LiveKit server URL")
    api_key: str = Field(default="", description="LiveKit API key")
    api_secret: str = Field(default="", description="LiveKit API secret")

    def is_valid(self) -> bool:
        return bool(self.url and self.api_key and self.api_secret)
