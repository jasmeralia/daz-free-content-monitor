from src.config import get_display_tz


def test_default_timezone(monkeypatch):
    monkeypatch.delenv("DISPLAY_TIMEZONE", raising=False)
    tz = get_display_tz()
    assert str(tz) == "America/Los_Angeles"


def test_custom_timezone(monkeypatch):
    monkeypatch.setenv("DISPLAY_TIMEZONE", "America/New_York")
    tz = get_display_tz()
    assert str(tz) == "America/New_York"


def test_empty_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("DISPLAY_TIMEZONE", "   ")
    tz = get_display_tz()
    assert str(tz) == "America/Los_Angeles"


def test_invalid_timezone_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("DISPLAY_TIMEZONE", "Not/AReal_Zone")
    tz = get_display_tz()
    assert str(tz) == "America/Los_Angeles"
