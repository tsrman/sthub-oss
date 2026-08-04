from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database. This default targets the Compose stack's `db` service and carries
    # a development-only password — set DATABASE_URL for any shared deployment.
    DATABASE_URL: str = (
        "postgresql+asyncpg://streamlit:streamlit@db:5432/streamlit_registry"
    )

    # Keycloak
    KEYCLOAK_URL: str = "http://keycloak:8080"
    # Optional public URL used by the browser/frontend (defaults to KEYCLOAK_URL).
    KEYCLOAK_PUBLIC_URL: str = ""
    KEYCLOAK_REALM: str = "streamlit-platform"
    KEYCLOAK_CLIENT: str = "streamlit-api"
    KEYCLOAK_CLIENT_SECRET: str = ""
    KEYCLOAK_ALLOWED_GROUPS: str = "streamlit-users,streamlit-admins"
    KEYCLOAK_ADMIN_GROUP: str = "streamlit-admins"
    KEYCLOAK_VERIFY_SSL: bool = True

    @property
    def keycloak_public_url(self) -> str:
        return (self.KEYCLOAK_PUBLIC_URL or self.KEYCLOAK_URL).rstrip("/")

    # Redis / arq
    REDIS_URL: str = "redis://redis:6379"
    # The worker must be configured to listen on the same queue name.
    ARQ_QUEUE_NAME: str = "arq:streamlit"

    # Worker
    WORKER_MAX_JOBS: int = 10
    WORKER_JOB_TIMEOUT: int = 3600  # seconds

    # Public host used for absolute URLs (empty = relative)
    PUBLIC_HOST: str = ""

    # Docker (only Worker uses these directly, API may read for validation defaults)
    DOCKER_HOST: str = "unix:///var/run/docker.sock"
    DOCKER_NETWORK: str = "streamlit-limited"
    STREAMLIT_BASE_IMAGE: str = "streamlit-base:latest"
    # Traefik entrypoint the worker attaches deployed app containers to. Use
    # "web" for the plain-HTTP stack, "websecure" for the TLS (:443) stack.
    TRAEFIK_ENTRYPOINT: str = "web"

    # Container limits
    CONTAINER_MEMORY: str = "512m"
    CONTAINER_MEMORY_RESERVATION: str = "128m"
    CONTAINER_CPU_QUOTA: int = 50000
    CONTAINER_CPU_PERIOD: int = 100000
    CONTAINER_PIDS_LIMIT: int = 100
    CONTAINER_TMPFS_SIZE: str = "64m"
    CONTAINER_TMPFS_RUNTIME_SIZE: str = "32m"

    # Quotas
    MAX_RUNNING_APPS_PER_USER: int = 5
    MAX_FILES_PER_STREAMLIT: int = 100
    MAX_FILE_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB
    MAX_CODE_SIZE: int = 5 * 1024 * 1024  # 5 MB
    MAX_REQUIREMENTS_SIZE: int = 1024 * 1024  # 1 MB

    # Allowed packages (white-list). An empty value denies every package, so the
    # default carries a workable set; .env.example ships the same list.
    ALLOWED_PACKAGES: str = (
        "streamlit,pandas,numpy,scipy,plotly,altair,pydeck,pillow,sqlalchemy,pymysql,"
        "psycopg2-binary,openpyxl,xlrd,pyarrow,fastparquet,scikit-learn,matplotlib,"
        "requests,httpx,pyyaml,python-dotenv,tabulate,rich,jsonschema"
    )

    # AI code assistant (LLM). Reaches the model through a self-hosted
    # OpenAI-compatible gateway. The API key and endpoint live only on the
    # backend; the frontend talks to the Control API, never to the gateway.
    # AI_BASE_URL is the gateway's OpenAI-compatible base (e.g.
    # "https://llm.example.com/v1"). AI_MODEL is the model name the gateway expects.
    AI_ENABLED: bool = False
    AI_API_KEY: str = ""
    AI_BASE_URL: str = ""
    AI_MODEL: str = "gpt-4o-mini"
    AI_MAX_TOKENS: int = 4096
    AI_TIMEOUT: int = 120  # seconds
    # TLS for the self-hosted gateway. AI_CA_CERT is a path (inside the container)
    # to the custom CA bundle used to verify the gateway's certificate; mount
    # it in and set this. AI_VERIFY_SSL=false disables verification entirely
    # (use only as a last resort — prefer providing the CA bundle).
    AI_CA_CERT: str = ""
    AI_VERIFY_SSL: bool = True
    AI_SYSTEM_PROMPT: str = (
        "You are a built-in coding assistant for Python Streamlit applications. "
        "Help the user write, explain, and debug Streamlit code. Answer concisely "
        "and to the point. Put code in markdown blocks with the language annotated. "
        "If the user sends the contents of the open file, treat it as context."
    )
    # Max characters of the open file forwarded as context (guards prompt size).
    AI_MAX_CONTEXT_CHARS: int = 20000

    # CORS
    CORS_ALLOW_ORIGINS: str = "*"

    @property
    def allowed_groups_list(self) -> list[str]:
        return [g.strip() for g in self.KEYCLOAK_ALLOWED_GROUPS.split(",") if g.strip()]

    @property
    def cors_allow_origins_list(self) -> list[str]:
        raw = self.CORS_ALLOW_ORIGINS.strip()
        if raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def allowed_packages_set(self) -> set[str]:
        return {
            p.strip().lower() for p in self.ALLOWED_PACKAGES.split(",") if p.strip()
        }

    @property
    def ai_configured(self) -> bool:
        """True when the AI assistant is enabled and has a gateway or key."""
        return bool(self.AI_ENABLED and (self.AI_BASE_URL or self.AI_API_KEY))

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
