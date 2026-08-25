"""
Central configuration for the project.

Everything reads from .env via pydantic-settings. Import `settings` anywhere
you need a config value - never read os.environ directly in other modules.
"""

from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    # ---- LLM provider selection ----
    llm_provider: str = Field("groq", alias="LLM_PROVIDER")  # groq | azure | deepseek (text/planning)
    vision_llm_provider: str = Field("groq", alias="VISION_LLM_PROVIDER")  # groq | azure (deepseek has no vision)

    # ---- Groq ----
    groq_api_key: Optional[str] = Field(None, alias="GROQ_API_KEY")
    groq_model: str = Field("openai/gpt-oss-20b", alias="GROQ_MODEL")
    groq_vision_model: str = Field("qwen/qwen3.6-27b", alias="GROQ_VISION_MODEL")

    # ---- Azure OpenAI ----
    azure_openai_api_key: Optional[str] = Field(None, alias="AZURE_OPENAI_API_KEY")
    azure_openai_endpoint: Optional[str] = Field(None, alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_version: str = Field("2024-08-01-preview", alias="AZURE_OPENAI_API_VERSION")
    azure_openai_deployment: Optional[str] = Field(None, alias="AZURE_OPENAI_DEPLOYMENT")
    # Optional: only needed if your vision-capable deployment has a different
    # name than your main text deployment. Falls back to azure_openai_deployment.
    azure_openai_vision_deployment: Optional[str] = Field(None, alias="AZURE_OPENAI_VISION_DEPLOYMENT")

    # ---- DeepSeek (text/planning only - no vision support) ----
    deepseek_api_key: Optional[str] = Field(None, alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field("https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field("deepseek-chat", alias="DEEPSEEK_MODEL")

    # ---- Target under test ----
    platform: str = Field("web", alias="PLATFORM")  # web | android | ios
    target_url: str = Field("https://www.saucedemo.com", alias="TARGET_URL")

    # ---- Appium / mobile ----
    appium_server_url: str = Field("http://127.0.0.1:4723", alias="APPIUM_SERVER_URL")
    android_device_name: str = Field("Android Device", alias="ANDROID_DEVICE_NAME")
    android_app_package: str = Field("", alias="ANDROID_APP_PACKAGE")
    android_app_activity: str = Field("", alias="ANDROID_APP_ACTIVITY")

    # ---- Agent behaviour ----
    max_steps: int = Field(15, alias="MAX_STEPS")
    fuzzy_match_threshold: int = Field(75, alias="FUZZY_MATCH_THRESHOLD")
    enable_vision_fallback: bool = Field(True, alias="ENABLE_VISION_FALLBACK")
    android_auto_grant_permissions: bool = Field(True, alias="ANDROID_AUTO_GRANT_PERMISSIONS")
    popup_dismiss_enabled: bool = Field(True, alias="POPUP_DISMISS_ENABLED")
    scroll_pixels: int = Field(600, alias="SCROLL_PIXELS")

    # ---- Paths (not read from env) ----
    base_dir: Path = BASE_DIR
    screenshot_dir: Path = BASE_DIR / "logs" / "screenshots"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )


settings = Settings()
settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
