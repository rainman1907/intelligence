import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv


load_dotenv()


@dataclass
class Settings:
    """
    Container for environment-driven configuration values.

    If you prefer hard-coded values, edit defaults below or override them via
    environment variables in a local `.env` file.
    """

    multilogin_api_base: str = os.getenv("MULTILOGIN_API_BASE", "http://127.0.0.1:35000")
    multilogin_api_token: str = os.getenv("MULTILOGIN_API_TOKEN", "")
    multilogin_profiles: List[str] = field(
        default_factory=lambda: [
            profile.strip()
            for profile in os.getenv("MULTILOGIN_PROFILE_IDS", "").split(",")
            if profile.strip()
        ]
    )

    captcha_api_key: str = os.getenv("CAPTCHA_API_KEY", "")
    captcha_poll_interval: int = int(os.getenv("CAPTCHA_POLL_INTERVAL", "5"))
    captcha_timeout: int = int(os.getenv("CAPTCHA_TIMEOUT", "180"))

    login_retries: int = int(os.getenv("LOGIN_RETRIES", "2"))
    page_load_timeout: int = int(os.getenv("PAGE_LOAD_TIMEOUT", "60"))
    implicit_wait: int = int(os.getenv("SELENIUM_IMPLICIT_WAIT", "10"))

    remote_debug_host: str = os.getenv("REMOTE_DEBUG_HOST", "127.0.0.1")
    use_rest_api: bool = os.getenv("MULTILOGIN_USE_REST", "true").lower() == "true"

    gmail_login_url: str = os.getenv(
        "GOOGLE_LOGIN_URL", "https://accounts.google.com/signin/v2/identifier"
    )
    gmail_recovery_url: str = os.getenv(
        "GOOGLE_RECOVERY_URL", "https://accounts.google.com/signin/v2/challenge"
    )


settings = Settings()
