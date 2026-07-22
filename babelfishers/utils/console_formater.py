from datetime import datetime
from enum import StrEnum

from babelfishers import APPLICATION_NAME
from babelfishers.utils.themes import StyleTheme, _Ansi


class Level(StrEnum):
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEBUG = "DEBUG"


class ConsoleFormatter:
    def __init__(self, app_prefix: str = APPLICATION_NAME):
        self._app_prefix: str = app_prefix.strip()
        self._theme: StyleTheme = StyleTheme()
        self._show_time: bool = True
        self._use_color: bool = True

    @staticmethod
    def info(msg: str) -> str:
        return ConsoleFormatter()._format(Level.INFO, msg)

    @staticmethod
    def success(msg: str) -> str:
        return ConsoleFormatter()._format(Level.SUCCESS, msg)

    @staticmethod
    def warning(msg: str) -> str:
        return ConsoleFormatter()._format(Level.WARNING, msg)

    @staticmethod
    def error(msg: str) -> str:
        return ConsoleFormatter()._format(Level.ERROR, msg)

    @staticmethod
    def debug(msg: str) -> str:
        return ConsoleFormatter()._format(Level.DEBUG, msg)

    def _format(self, level: Level, msg: str) -> str:
        # Build prefix parts
        time_part: str = ""
        if self._show_time:
            time_part = datetime.now().strftime("%H:%M:%S")

        prefix: str = self._format_prefix(time_part=time_part)

        tag: str = self._format_tag(level)
        text: str = self._format_message(level, msg)

        return f"{prefix}{tag} {text}".rstrip()

    def _format_prefix(self, *, time_part: str) -> str:
        parts: list[str] = []

        if time_part:
            parts.append(self._color(self._theme.time, time_part))

        if self._app_prefix:
            parts.append(self._color(self._theme.prefix, self._app_prefix))

        if not parts:
            return ""

        return " ".join(parts) + " "

    def _format_tag(self, level: Level) -> str:
        label: str = {
            Level.INFO: "INFO",
            Level.SUCCESS: "OK",
            Level.WARNING: "WARN",
            Level.ERROR: "ERR",
            Level.DEBUG: "DBG",
        }[level]

        label = f"[{label:4}]"

        color: str = self._tag_color(level)
        return self._color(color, label)

    def _format_message(self, level: Level, msg: str) -> str:
        return self._color(self._msg_color(level), msg)

    def _tag_color(self, level: Level) -> str:
        return {
            Level.INFO: self._theme.tag_info,
            Level.SUCCESS: self._theme.tag_success,
            Level.WARNING: self._theme.tag_warning,
            Level.ERROR: self._theme.tag_error,
            Level.DEBUG: self._theme.tag_debug,
        }[level]

    def _msg_color(self, level: Level) -> str:
        return {
            Level.INFO: self._theme.msg_info,
            Level.SUCCESS: self._theme.msg_success,
            Level.WARNING: self._theme.msg_warning,
            Level.ERROR: self._theme.msg_error,
            Level.DEBUG: self._theme.msg_debug,
        }[level]

    def _color(self, color_code: str, text: str) -> str:
        if not self._use_color:
            return text
        return f"{color_code}{text}{_Ansi.RESET}"
