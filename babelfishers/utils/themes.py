from pydantic import BaseModel


class _Ansi:
    RESET: str = "\x1b[0m"
    BOLD: str = "\x1b[1m"
    DIM: str = "\x1b[2m"

    BLACK: str = "\x1b[30m"
    RED: str = "\x1b[31m"
    GREEN: str = "\x1b[32m"
    YELLOW: str = "\x1b[33m"
    BLUE: str = "\x1b[34m"
    MAGENTA: str = "\x1b[35m"
    CYAN: str = "\x1b[36m"
    WHITE: str = "\x1b[37m"

    GRAY: str = "\x1b[90m"


class StyleTheme(BaseModel):
    tag_info: str = _Ansi.CYAN
    tag_success: str = _Ansi.GREEN
    tag_warning: str = _Ansi.YELLOW
    tag_error: str = _Ansi.RED
    tag_debug: str = _Ansi.MAGENTA
    tag_normal: str = _Ansi.WHITE

    msg_info: str = _Ansi.WHITE
    msg_success: str = _Ansi.WHITE
    msg_warning: str = _Ansi.WHITE
    msg_error: str = _Ansi.WHITE
    msg_debug: str = _Ansi.GRAY
    msg_normal: str = _Ansi.WHITE

    prefix: str = _Ansi.GRAY
    time: str = _Ansi.GRAY
