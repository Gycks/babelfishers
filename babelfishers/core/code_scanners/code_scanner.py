from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

from babelfishers.models.extract import Extract, ScanResult


_SKIPPED_FOLDERS = frozenset(
    {".git", ".venv", "venv", "env", "site-packages", "node_modules", "__pycache__", "build", "dist", "bin", "obj"}
)


class CodeScanner(ABC):
    """
    Abstract base class for code scanners.

    A code scanner reads an app's code and finds the translatable strings in it
    i.e. the calls the app makes to its localization library
    """

    def __init__(self, extensions: tuple[str, ...] = ()):
        self.__file_extensions: tuple[str, ...] = extensions
        self._comment_tag: str = "BF_TRANSLATOR:"

    @abstractmethod
    def scan(self, extract: Extract) -> ScanResult:
        """Find the translatable strings in the code under an extract's root.

        Args:
            extract: The extract entry to scan: its root and what to exclude.

        Returns:
            The strings found, and the calls whose text could not be read because
            it is built at runtime.
        """
        raise NotImplementedError("The abstract method 'scan()' must be implemented by subclasses.")

    def _code_files(self, extract: Extract) -> Iterator[Path]:
        """Every file under the extract's root with one of this scanner's extensions,
        except the excluded ones and those in folders that never hold the app's code."""
        for path in sorted(extract.root.rglob("*")):
            if path.suffix not in self.__file_extensions or not path.is_file():
                continue
            if _SKIPPED_FOLDERS.intersection(path.relative_to(extract.root).parts):
                continue
            if extract.is_excluded(path):
                continue
            yield path
