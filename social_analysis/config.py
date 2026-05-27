import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")
    x_bearer_token: str = os.getenv("X_BEARER_TOKEN", "")
    x_use_scraper: bool = os.getenv("X_USE_SCRAPER", "false").lower() == "true"
    ig_username: str = os.getenv("IG_USERNAME", "")
    ig_password: str = os.getenv("IG_PASSWORD", "")
    ig_session_id: str = os.getenv("IG_SESSION_ID", "")
    ig_csrftoken: str = os.getenv("IG_CSRFTOKEN", "")
    threads_sessionid: str = os.getenv("THREADS_SESSIONID", "")
    threads_csrftoken: str = os.getenv("THREADS_CSRFTOKEN", "")
    threads_mid: str = os.getenv("THREADS_MID", "")
    threads_ds_user_id: str = os.getenv("THREADS_DS_USER_ID", "")
    db_url: str = os.getenv("DB_URL", "sqlite:///./social_analysis.db")
    publish_target: str = os.getenv("PUBLISH_TARGET", "file")
    webhook_url: str = os.getenv("WEBHOOK_URL", "")
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_pass: str = os.getenv("SMTP_PASS", "")
    email_to: str = os.getenv("EMAIL_TO", "")

    # Photo Agent
    photo_queue_dir: str = os.getenv("PHOTO_QUEUE_DIR", "photos/queue")
    photo_posted_dir: str = os.getenv("PHOTO_POSTED_DIR", "photos/posted")
    photo_failed_dir: str = os.getenv("PHOTO_FAILED_DIR", "photos/failed")
    post_schedule: str = os.getenv("POST_SCHEDULE", "08:00,20:00")
    ig_post_feed: bool = os.getenv("IG_POST_FEED", "true").lower() == "true"
    ig_post_story: bool = os.getenv("IG_POST_STORY", "true").lower() == "true"
    threads_post: bool = os.getenv("THREADS_POST", "true").lower() == "true"


settings = Settings()
