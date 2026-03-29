import os

__version__ = "0.1.2"


def get_app_version() -> str:
    return os.environ.get("APP_VERSION", __version__).strip() or __version__
