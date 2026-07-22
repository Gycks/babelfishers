import logging

from babelfishers.core.parsers.parser_factory import ParserFactory
from babelfishers.core.tm_store import TMStore
from babelfishers.core.translation_pipeline import TranslationPipeline
from babelfishers.models.app_config import AppConfig
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import get_translation_store_storage_path


class Runtime:
    def __init__(self, config: AppConfig, dry_run: bool = False) -> None:
        self._logger: logging.Logger = logging.getLogger(__file__)
        self._config: AppConfig = config
        self._dry_run: bool = dry_run
        self._tm_store: TMStore = TMStore(get_translation_store_storage_path())

    def orchestrate_translation_workflow(self) -> None:
        for resource in self._config.resources:
            parser = ParserFactory.create(resource.resource_type)

            engines = []
            if resource.engine:
                engines.append(resource.engine)

            engines.append(self._config.translation_engine)
            pipeline = TranslationPipeline(
                translation_engines=engines, glossary=self._config.glossary, translation_store=self._tm_store
            )

            for resource_path in resource.paths:
                source_path = resource_path.path
                parse_result = parser.parse(
                    source_path=source_path,
                    excluded_keys=resource.excluded_keys,
                )

                for locale in self._config.target_locales:
                    self._logger.info(
                        ConsoleFormatter.info(
                            f"[{self._config.source_locale} - {locale}] -> Running translation for {source_path}"
                        )
                    )

                    destination = resource_path.get_destination_path(locale)
                    pipeline.run(parse_result, self._config.source_locale, locale, destination)

                    self._logger.info(
                        ConsoleFormatter.success(
                            f"[{self._config.source_locale} - {locale}] -> Pipeline success for {source_path}"
                        )
                    )
