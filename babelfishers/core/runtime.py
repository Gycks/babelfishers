import logging
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path

from babelfishers.core.parsers.parser_factory import ParserFactory
from babelfishers.core.tm_store import TMStore
from babelfishers.core.translation_pipeline import TranslationPipeline
from babelfishers.models.app_config import AppConfig
from babelfishers.models.translation_resource import ResourcePath
from babelfishers.models.translations import ParseResult
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import get_translation_store_storage_path


class Runtime:
    def __init__(
        self, config: AppConfig, db_storage: Path | None = None, dry_run: bool = False, max_workers: int = 8
    ) -> None:
        self._logger: logging.Logger = logging.getLogger(__file__)
        self._config: AppConfig = config
        self._dry_run: bool = dry_run
        self._tm_store: TMStore = TMStore(db_storage or get_translation_store_storage_path())
        self._max_workers = max_workers

    def orchestrate_translation_workflow(self) -> None:
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures: dict[Future[None], str] = {}

            for resource in self._config.resources:
                if len(resource.paths) == 0:
                    self._logger.warning(
                        ConsoleFormatter.warning(f"Skipping bucket: '{resource.resource_type}'. Reason: Bucket empty")
                    )
                    continue

                parser = ParserFactory.create(resource.resource_type)

                engines = []
                if resource.engine:
                    engines.append(resource.engine)
                engines.append(self._config.translation_engine)

                pipeline = TranslationPipeline(
                    translation_engines=engines,
                    glossary=self._config.glossary,
                    translation_store=self._tm_store,
                )

                for resource_path in resource.paths:
                    source_path = resource_path.path
                    parse_result = parser.parse(
                        source_path=source_path,
                        excluded_keys=resource.excluded_keys,
                    )

                    for locale in self._config.target_locales:
                        future = executor.submit(
                            self._run_single_locale,
                            pipeline,
                            parser.clone(parse_result),
                            resource_path,
                            locale,
                            source_path,
                        )
                        futures[future] = f"[{self._config.source_locale} - {locale}] {source_path}"

            for future in as_completed(futures):
                job_label = futures[future]
                try:
                    future.result()
                except Exception as exe:
                    self._logger.exception(ConsoleFormatter.error(f"{job_label} -> Pipeline failed"), exc_info=exe)
                    raise

    def _run_single_locale(
        self,
        pipeline: TranslationPipeline,
        parse_result: ParseResult,
        resource_path: ResourcePath,
        locale: str,
        source_path: Path,
    ) -> None:
        self._logger.info(
            ConsoleFormatter.info(f"[{self._config.source_locale} - {locale}] -> Running translation for {source_path}")
        )

        destination = resource_path.get_destination_path(locale)
        pipeline.run(parse_result, self._config.source_locale, locale, destination)

        self._logger.info(
            ConsoleFormatter.success(f"[{self._config.source_locale} - {locale}] -> Pipeline success for {source_path}")
        )
