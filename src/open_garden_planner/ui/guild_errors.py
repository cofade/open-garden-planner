"""Translate structured validation errors only at the UI boundary."""

from typing import Any

from PyQt6.QtCore import QCoreApplication

from open_garden_planner.models.guild_errors import MESSAGES, GuildValidationError


def guild_error_message(error: Exception) -> str:
    if isinstance(error, GuildValidationError):
        return guild_error_details(error.code, error.details)
    return QCoreApplication.translate("GuildErrors", "Invalid template or file: {reason}").format(reason=str(error))


def guild_error_details(code: str, details: dict[str, Any]) -> str:
    values = dict(details)
    if "field" in values:
        values["field"] = QCoreApplication.translate("GuildErrors", str(values["field"]))
    return QCoreApplication.translate("GuildErrors", MESSAGES[code]).format(**values)
