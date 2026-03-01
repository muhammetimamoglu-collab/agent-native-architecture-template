from __future__ import annotations

from pathlib import Path
from typing import Any, Tuple, Type

from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, DotEnvSettingsSource, EnvSettingsSource, PydanticBaseSettingsSource, SettingsConfigDict

_ENV_FILE = Path(__file__).parent.parent / ".env"

# Fields that accept comma-separated strings from .env (e.g. ".md,.yaml,.mmd").
# pydantic-settings v2 calls json.loads() for list[str] fields before validators
# run; this custom source intercepts those fields and splits by comma instead.
_CSV_FIELDS = frozenset(["index_extensions_docs", "index_extensions_code", "index_exclude"])


def _parse_csv(value: Any) -> Any:
    """If value is a plain CSV string, split it; otherwise return as-is."""
    if isinstance(value, str) and not value.startswith("["):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class _CsvEnvSource(EnvSettingsSource):
    def decode_complex_value(self, field_name: str, field_info: FieldInfo, value: Any) -> Any:
        if field_name in _CSV_FIELDS:
            return _parse_csv(value)
        return super().decode_complex_value(field_name, field_info, value)


class _CsvDotEnvSource(DotEnvSettingsSource):
    def decode_complex_value(self, field_name: str, field_info: FieldInfo, value: Any) -> Any:
        if field_name in _CSV_FIELDS:
            return _parse_csv(value)
        return super().decode_complex_value(field_name, field_info, value)


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

    # Indexing — paths relative to the git repository root
    docs_root: str = "docs"
    code_root: str = "src"
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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            _CsvEnvSource(settings_cls),
            _CsvDotEnvSource(settings_cls, env_file=str(_ENV_FILE), env_file_encoding="utf-8"),
            file_secret_settings,
        )


settings = Settings()  # type: ignore[call-arg]
