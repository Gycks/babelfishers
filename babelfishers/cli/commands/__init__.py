from .formats import formats
from .init import initialize
from .locales import locales
from .memory import translation_memory
from .translate import translate


COMMANDS = [initialize, translate, formats, locales, translation_memory]
