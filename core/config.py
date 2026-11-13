from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./database.db"
    secret_key: SecretStr = Field(min_length=32)
    algorithm: str = "HS256"
    debug: bool = False
    sqlite_wal: bool = False
    sqlite_busy_timeout_ms: int = Field(default=5000, ge=1, le=60000)


settings = Settings()

DATABASE_URL = settings.database_url
SECRET_KEY = settings.secret_key.get_secret_value()
ALGORITHM = settings.algorithm
