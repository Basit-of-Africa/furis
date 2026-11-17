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

    # "development" | "production". Production refuses to start with dev sign-in.
    environment: str = "development"

    # Authentication (see furis/auth.py):
    #   "oidc"       university single sign-on via any OpenID Connect provider
    #   "dev_header" trusts an email with no password; development only
    auth_mode: str = "dev_header"

    # OpenID Connect. Examples of issuer:
    #   Google Workspace:      https://accounts.google.com
    #   Microsoft Entra ID:    https://login.microsoftonline.com/<tenant-id>/v2.0
    #   Keycloak:              https://sso.example.edu.ng/realms/<realm>
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None  # the ID token's expected audience
    # Only these email domains may sign in, e.g. ["fuo.edu.ng"]. Required in oidc mode.
    oidc_allowed_email_domains: list[str] = []
    # Claims tried in order for the user's email (Entra often puts it in preferred_username).
    oidc_email_claims: list[str] = ["email", "preferred_username", "upn"]
    # Optional extra claim checks, e.g. {"hd": "fuo.edu.ng"} (Google) or {"tid": "<tenant-id>"} (Entra).
    oidc_required_claims: dict[str, str] = {}

    # FURIS session tokens (HS256). Use a long random value in production:
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    session_secret: str | None = None
    session_ttl_minutes: int = 480


@lru_cache
def get_settings() -> Settings:
    return Settings()


class ConfigError(RuntimeError):
    pass


def validate_auth_settings(s: Settings) -> None:
    """Fail fast on unsafe or incomplete authentication configuration."""
    if s.auth_mode not in ("oidc", "dev_header"):
        raise ConfigError(f"unknown FURIS_AUTH_MODE {s.auth_mode!r}")
    if s.environment == "production":
        if s.auth_mode != "oidc":
            raise ConfigError("production requires FURIS_AUTH_MODE=oidc; dev sign-in has no password check")
        if not s.session_secret or len(s.session_secret) < 32:
            raise ConfigError("production requires FURIS_SESSION_SECRET of at least 32 characters")
    if s.auth_mode == "oidc":
        missing = [n for n, v in (("FURIS_OIDC_ISSUER", s.oidc_issuer), ("FURIS_OIDC_CLIENT_ID", s.oidc_client_id),
                                  ("FURIS_SESSION_SECRET", s.session_secret)) if not v]
        if not s.oidc_allowed_email_domains:
            missing.append("FURIS_OIDC_ALLOWED_EMAIL_DOMAINS")
        if missing:
            raise ConfigError(f"oidc mode needs {', '.join(missing)}")
        if not s.oidc_issuer.startswith("https://") and s.environment == "production":
            raise ConfigError("FURIS_OIDC_ISSUER must use https")
