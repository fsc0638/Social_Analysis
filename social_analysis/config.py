import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    x_bearer_token: str = os.getenv("X_BEARER_TOKEN", "")
    x_use_scraper: bool = os.getenv("X_USE_SCRAPER", "false").lower() == "true"
    ig_username: str = os.getenv("IG_USERNAME", "")
    ig_password: str = os.getenv("IG_PASSWORD", "")
    threads_cookie: str = os.getenv("THREADS_COOKIE", "")
    db_url: str = os.getenv("DB_URL", "sqlite:///./social_analysis.db")
    publish_target: str = os.getenv("PUBLISH_TARGET", "file")
    webhook_url: str = os.getenv("WEBHOOK_URL", "")
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_pass: str = os.getenv("SMTP_PASS", "")
    email_to: str = os.getenv("EMAIL_TO", "")


settings = Settings()
