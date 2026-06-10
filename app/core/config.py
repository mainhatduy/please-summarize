from typing import Optional
import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    MODEL_NAME: str = Field(default="gemini-2.5-flash")
    DISCORD_TOKEN: str = Field(default="")
    GEMINI_API_KEY: str = Field(default="")
    CHANNEL_ID: Optional[int] = Field(default=None)
    DISCORD_WEBHOOK_URL: Optional[str] = Field(default=None)
    DATA_DIR: str = Field(default="data")
    MEMORY_TTL_HOURS: int = Field(default=48)
    MEMORY_MAX_CHARS: int = Field(default=2500)

    def data_path(self, filename: str) -> str:
        return os.path.join(self.DATA_DIR, filename)

# Create a singleton instance for backward compatibility
Config = Settings()
