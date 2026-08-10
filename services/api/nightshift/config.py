"""Settings, validated once at import and never read from ``os.environ`` again.

Env validation is an M0 deliverable and it means something specific here: the
process refuses to start on a bad value rather than failing later with a
confusing connection error. A typo in ``POSTGRES_PORT`` should be a startup
error naming the field, not a timeout twenty seconds into the first request.
"""

from __future__ import annotations

import functools
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    """Runtime configuration. Constructed once via :func:`get_settings`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # Reject a URL with whitespace rather than silently connecting nowhere.
        str_strip_whitespace=True,
    )

    nightshift_env: Environment = "development"
    log_level: Literal["debug", "info", "warning", "error"] = "info"

    # -- Postgres ----------------------------------------------------------
    postgres_user: str = "nightshift"
    postgres_password: str = "nightshift_dev_only"
    postgres_db: str = "nightshift"
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5433, ge=1, le=65535)
    database_url: PostgresDsn | None = None

    # -- Redis -------------------------------------------------------------
    redis_host: str = "localhost"
    redis_port: int = Field(default=6380, ge=1, le=65535)
    redis_db: int = Field(default=0, ge=0, le=15)

    # -- API ---------------------------------------------------------------
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    # NoDecode because pydantic-settings otherwise tries to JSON-decode any
    # complex-typed field read from a .env file, which fails before our
    # comma-splitting validator gets a chance to run.
    cors_allow_origins: Annotated[tuple[str, ...], NoDecode] = ("http://localhost:3000",)

    # -- Single-user mode (AMENDMENTS A3) ----------------------------------
    dev_user_id: UUID = UUID("00000000-0000-4000-8000-000000000001")
    dev_user_email: str = "dev@nightshift.local"

    # -- Outbound HTTP -----------------------------------------------------
    # Default false so a clean clone cannot make a network request by accident
    # and `make demo` is offline by construction rather than by convention.
    outbound_http_enabled: bool = False
    http_user_agent: str = "Nightshift/0.1 (+https://github.com/Tahmudun/Nightshift)"
    http_timeout_seconds: float = Field(default=20.0, gt=0, le=300)
    http_max_retries: int = Field(default=3, ge=0, le=10)
    source_requests_per_second: float = Field(default=2.0, gt=0, le=20)
    # Base for exponential backoff between retries. Configurable so the unit
    # suite can shrink it without patching internals — a suite that spends ten
    # seconds asleep is a suite people start skipping.
    http_backoff_base_seconds: float = Field(default=1.0, gt=0, le=30)

    # -- Polling (M1d, ADR 0007) --------------------------------------------
    # Tier intervals. Hot means the board has produced an NYC posting recently;
    # warm is everything else. ADR 0007 rejected a weekly tier because a
    # company's first NYC role could then sit unseen for six days.
    poll_hot_interval_seconds: int = Field(default=3600, ge=60)
    poll_warm_interval_seconds: int = Field(default=86_400, ge=60)
    # How many boards one scheduler tick may enqueue. At 22 boards this never
    # binds. It exists for the recovery case: a scheduler waking after an outage
    # finds every board overdue, and without a cap it would queue the entire
    # registry at once — reintroducing exactly the stampede `next_poll_at` was
    # chosen to avoid.
    poll_enqueue_batch_limit: int = Field(default=500, ge=1, le=10_000)
    # How many (person, posting) pairs one recompute tick may score. The case
    # this exists for is the ruleset version bump: every pair in the corpus goes
    # due at once, and an unbounded run is a single transaction over the whole
    # cross product whose failure discards everything it computed. A batch
    # commits what it finished and the next tick continues from where it stopped.
    match_recompute_batch_limit: int = Field(default=500, ge=1, le=10_000)
    # Per-board backoff, distinct from `http_backoff_base_seconds` above: that
    # one handles a single flaky response and is measured in seconds, this one
    # handles a board that is simply gone. The ceiling matches the warm tier, so
    # a board that comes back is noticed within a day rather than falling out of
    # the system entirely.
    poll_backoff_base_seconds: int = Field(default=900, ge=1)
    poll_backoff_max_seconds: int = Field(default=86_400, ge=60)

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept the comma-separated form that lives naturally in a .env file."""
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @field_validator("http_user_agent")
    @classmethod
    def _require_identifying_ua(cls, value: str) -> str:
        """§7.3: every adapter must identify itself.

        A blank or generic user agent is how you get a source to block you, and
        it is dishonest to a maintainer reading their access logs.
        """
        if len(value) < 10 or "nightshift" not in value.lower():
            raise ValueError(
                "HTTP_USER_AGENT must identify this project — "
                "include 'Nightshift' and a contact URL"
            )
        return value

    @model_validator(mode="after")
    def _forbid_dev_password_in_production(self) -> Settings:
        if self.nightshift_env == "production" and self.postgres_password.endswith("_dev_only"):
            raise ValueError(
                "refusing to start: POSTGRES_PASSWORD is still the development default"
            )
        return self

    # -- Derived -----------------------------------------------------------

    @property
    def async_database_url(self) -> str:
        """SQLAlchemy asyncpg URL used by the API, the worker, and Alembic."""
        if self.database_url is not None:
            # Normalise whatever scheme was supplied to the async driver.
            raw = str(self.database_url)
            for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://"):
                if raw.startswith(prefix):
                    return "postgresql+asyncpg://" + raw[len(prefix) :]
            return raw
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_dsn(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def redis_settings_kwargs(self) -> dict[str, object]:
        """Kwargs for ``arq.connections.RedisSettings``."""
        return {"host": self.redis_host, "port": self.redis_port, "database": self.redis_db}

    def redacted(self) -> dict[str, object]:
        """Config safe to log or expose. Never includes the password."""
        return {
            "env": self.nightshift_env,
            "postgres": f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}",
            "redis": f"{self.redis_host}:{self.redis_port}/{self.redis_db}",
            "outbound_http_enabled": self.outbound_http_enabled,
        }


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton.

    Cached because :class:`Settings` reads the filesystem, and because config
    changing mid-process is a bug, not a feature. Tests clear the cache.
    """
    return Settings()
