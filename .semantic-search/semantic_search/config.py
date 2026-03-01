from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Embedder
    embedder_type: str = "voyage"
    voyage_api_key: str = ""
    ollama_url: str = "http://localhost:11434"
    local_model_name: str = "nomic-embed-text"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    docs_collection: str = "docs_index"
    code_collection: str = "code_index"

    # Indexing
    docs_root: str = "../docs"
    code_root: str = "../src"
    index_extensions_docs: list[str] = [".md", ".yaml", ".mmd"]
    index_extensions_code: list[str] = [
        ".py", ".js", ".jsx", ".ts", ".tsx",
        ".java", ".kt", ".kts", ".scala", ".groovy",
        ".cs", ".fs", ".vb",
        ".go", ".rs", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp",
        ".swift", ".dart", ".rb", ".php", ".lua", ".pl",
        ".sh", ".bash", ".zsh", ".ps1",
        ".r", ".jl", ".hs", ".ex", ".exs", ".erl", ".clj",
    ]
    index_exclude: list[str] = [
        ".git", "__pycache__", ".venv", "node_modules",
        ".semantic-search", "qdrant_storage",
    ]

    @field_validator("index_extensions_docs", "index_extensions_code", "index_exclude", mode="before")
    @classmethod
    def split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


settings = Settings()  # type: ignore[call-arg]
