"""
Core configuration settings.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Adaptive Multimodal AI Interview System"
    debug: bool = False
    
    gemini_api_key: str = ""
    
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
