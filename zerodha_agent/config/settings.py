from __future__ import annotations

import shlex
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ENV_FILE)


class Settings(BaseSettings):
    app_name: str = "Zerodha Agent"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8000"])

    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4.1-mini"
    langsmith_tracing: bool = False
    langsmith_api_key: Optional[str] = None
    langsmith_project: str = "zerodha-agent"

    zerodha_api_key: Optional[str] = None
    zerodha_api_secret: Optional[str] = None
    zerodha_access_token: Optional[str] = None

    # login_tool removed (no login flow)
    profile_tool: str = "get_profile"
    margins_tool: str = "get_margins"
    holdings_tool: str = "get_holdings"
    positions_tool: str = "get_positions"
    orders_tool: str = "get_orders"
    place_order_tool: str = "place_order"
    cancel_order_tool: str = "cancel_order"
    modify_order_tool: str = "modify_order"

    project_root: Path = Path(__file__).resolve().parents[1]
    static_dir: Path = project_root / "static"

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
