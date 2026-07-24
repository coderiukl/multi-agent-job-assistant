import logging

from app.core.config import Settings
from app.core.logging import build_logging_config, configure_logging


def test_build_logging_config_uses_configured_level() -> None:
    settings = Settings(
        log_level="DEBUG",
        _env_file=None,
    )

    config = build_logging_config(settings)

    assert config["root"]["level"] == "DEBUG"
    assert config["handlers"]["console"]["level"] == "DEBUG"


def test_logging_config_contains_console_handler() -> None:
    settings = Settings(
        log_level="INFO",
        _env_file=None,
    )

    config = build_logging_config(settings)

    assert "console" in config["handlers"]
    assert (
        config["handlers"]["console"]["class"]
        == "logging.StreamHandler"
    )


def test_configure_logging_sets_root_level() -> None:
    settings = Settings(
        log_level="WARNING",
        _env_file=None,
    )

    configure_logging(settings)

    root_logger = logging.getLogger()

    assert root_logger.level == logging.WARNING

def test_default_log_level() -> None:
    settings = Settings(_env_file=None)

    assert settings.log_level == "INFO"


def test_log_level_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "ERROR")

    settings = Settings(_env_file=None)

    assert settings.log_level == "ERROR"