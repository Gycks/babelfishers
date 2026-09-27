from babelfishers.core.code_scanners.code_scanner import CodeScanner
from babelfishers.core.code_scanners.registry import code_scanners_registry
from babelfishers.models.extract import ExtractType


class CodeScannerFactory:
    @staticmethod
    def create(extract_type: ExtractType) -> CodeScanner:
        """
        Creates a code scanner instance for the specified extract type.

        Args:
            extract_type: The extract type to scan code for.

        Returns:
            An instance of the code scanner associated with that type.
        """

        cls = code_scanners_registry.get(extract_type)
        if cls is None:
            raise ValueError(f"No class registered for {extract_type}")

        scanner = cls()
        if not isinstance(scanner, CodeScanner):
            raise ValueError(f"Invalid code scanner: {extract_type}")

        return scanner
