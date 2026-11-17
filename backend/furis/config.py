from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FURIS_", env_file=".env", extra="ignore", populate_by_name=True)

    # Neon: use the *pooled* string for the app, the *direct* string for Alembic (§11.4).
    # Also reads the names the Vercel–Neon integration injects (DATABASE_URL = pooled,
    # DATABASE_URL_UNPOOLED = direct); FURIS_* takes precedence when both are set.
    database_url: str = Field("sqlite:///./furis_dev.db",
                              validation_alias=AliasChoices("FURIS_DATABASE_URL", "DATABASE_URL"))
    database_url_direct: str | None = Field(None, validation_alias=AliasChoices("FURIS_DATABASE_URL_DIRECT",
                                                                                   "DATABASE_URL_UNPOOLED"))

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

    # How the "Run discovery" button works:
    #   "background" run in the API process (a normal always-on server)
    #   "queue"      record a request for the scheduled worker (serverless, e.g. Vercel)
    # Defaults to "queue" when running on Vercel.
    discovery_mode: str | None = None

    # Start the GitHub Actions discovery job as soon as discovery is requested (queue mode),
    # instead of waiting for GitHub's hourly schedule. Needs a fine-grained token limited to
    # this repository with "Actions: Read and write" permission.
    github_token: str | None = None
    github_repository: str = "Basit-of-Africa/furis"
    github_workflow: str = "discovery.yml"
    github_ref: str = "main"

    # "development" | "production". Production refuses to start with dev sign-in.
    environment: str = "development"

    # Authentication (see furis/auth.py and furis/passwords.py):
    #   "password"   Research Desk accounts with passwords (no external provider needed)
    #   "oidc"       university single sign-on via any OpenID Connect provider
    #   "dev_header" trusts an email with no password; development only
    auth_mode: str = "dev_header"

    # First Research Desk officer (password mode). On first sign-in with exactly these
    # credentials the account is created as Super Administrator and must change its
    # password. After that the account's own password is used; remove these settings.
    bootstrap_admin_email: str | None = None
    bootstrap_admin_name: str = "Research Desk Officer"
    bootstrap_admin_password: str | None = None

    # Public, read-only research view (confirmed publications only). No sign-in.
    public_view: bool = True

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


def discovery_mode(s: Settings) -> str:
    import os

    return s.discovery_mode or ("queue" if os.environ.get("VERCEL") else "background")


class ConfigError(RuntimeError):
    pass


def validate_auth_settings(s: Settings) -> None:
    """Fail fast on unsafe or incomplete authentication configuration."""
    import os

    if s.auth_mode not in ("password", "oidc", "dev_header"):
        raise ConfigError(f"unknown FURIS_AUTH_MODE {s.auth_mode!r}")
    public_server = bool(os.environ.get("VERCEL")) or s.environment == "production"
    if public_server:
        # Every Vercel deployment has a public URL: never serve password-free sign-in there,
        # even if FURIS_ENVIRONMENT was forgotten.
        if s.auth_mode == "dev_header":
            raise ConfigError("on a public server FURIS_AUTH_MODE must be password or oidc; "
                              "dev sign-in has no password check")
        if not s.session_secret or len(s.session_secret) < 32:
            raise ConfigError("FURIS_SESSION_SECRET of at least 32 characters is required on a public server")
    if s.auth_mode == "password":
        if s.bootstrap_admin_password is not None and len(s.bootstrap_admin_password) < 12:
            raise ConfigError("FURIS_BOOTSTRAP_ADMIN_PASSWORD must be at least 12 characters")
        if bool(s.bootstrap_admin_email) != bool(s.bootstrap_admin_password):
            raise ConfigError("set both FURIS_BOOTSTRAP_ADMIN_EMAIL and FURIS_BOOTSTRAP_ADMIN_PASSWORD, or neither")
    if s.auth_mode == "oidc":
        missing = [n for n, v in (("FURIS_OIDC_ISSUER", s.oidc_issuer), ("FURIS_OIDC_CLIENT_ID", s.oidc_client_id),
                                  ("FURIS_SESSION_SECRET", s.session_secret)) if not v]
        if not s.oidc_allowed_email_domains:
            missing.append("FURIS_OIDC_ALLOWED_EMAIL_DOMAINS")
        if missing:
            raise ConfigError(f"oidc mode needs {', '.join(missing)}")
        if not s.oidc_issuer.startswith("https://") and s.environment == "production":
            raise ConfigError("FURIS_OIDC_ISSUER must use https")
