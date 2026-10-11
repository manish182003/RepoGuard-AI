from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name:str = "RepoGuard AI"
    app_env:str = "development"

    groq_api_key:str= ""
    github_token:str= ""
    groq_model: str = "qwen/qwen3.8-27b"
    openrouter_api_key: str | None = None
    openrouter_model: str = "openrouter/free"
    cloudflare_account_id: str | None = None
    cloudflare_api_token: str | None = None
    cloudflare_model: str = "@cf/qwen/qwen2.5-coder-32b-instruct"

    model_config= SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings=Settings()