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

# Create a singleton instance for backward compatibility
Config = Settings()
