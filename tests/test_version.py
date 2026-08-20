import os

from src.version import __version__, get_app_version


class TestGetAppVersion:
    def test_default_matches_module_version(self):
        os.environ.pop("APP_VERSION", None)
        assert get_app_version() == __version__

    def test_env_override(self):
        os.environ["APP_VERSION"] = "9.9.9"
        try:
            assert get_app_version() == "9.9.9"
        finally:
            os.environ.pop("APP_VERSION", None)

    def test_env_whitespace_stripped(self):
        os.environ["APP_VERSION"] = "  9.9.9  "
        try:
            assert get_app_version() == "9.9.9"
        finally:
            os.environ.pop("APP_VERSION", None)

    def test_empty_env_falls_back_to_default(self):
        os.environ["APP_VERSION"] = ""
        try:
            assert get_app_version() == __version__
        finally:
            os.environ.pop("APP_VERSION", None)

    def test_whitespace_only_env_falls_back_to_default(self):
        os.environ["APP_VERSION"] = "   "
        try:
            assert get_app_version() == __version__
        finally:
            os.environ.pop("APP_VERSION", None)
