from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FURIS_", env_file=".env", extra="ignore")

    # Neon: use the *pooled* string for the app, the *direct* string for Alembic (§11.4).
    database_url: str = "sqlite:///./furis_dev.db"
    database_url_direct: str | None = None

    # Polite-pool contact for OpenAlex/Crossref. Set to a Research Office mailbox.
    contact_email: str | None = None
    openalex_api_key: str | None = None

    http_timeout_seconds: float = 30.0
    http_max_retries: int = 4
    # Hard cap per query so a common name cannot pull tens of thousands of works.
    max_records_per_query: int = 1000

    # Institution identity. Fill these with Fountain University's verified OpenAlex
    # institution ID(s) and ROR ID before the pilot; affiliation text matching is used too.
    fu_openalex_institution_ids: list[str] = []
    fu_ror_ids: list[str] = []

    # "dev_header" trusts an X-User-Email header. Development only: replace with real
    # SSO/OIDC before any deployment that holds staff data.
    auth_mode: str = "dev_header"


@lru_cache
def get_settings() -> Settings:
    return Settings()
