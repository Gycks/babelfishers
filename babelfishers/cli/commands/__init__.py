from .init import initialize
from .locales import locales
from .memory import translation_memory
from .run_lock import run_lock
from .translate import translate


COMMANDS = [initialize, run_lock, translate, locales, translation_memory]
