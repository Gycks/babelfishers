import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path

from babelfishers.core.parsers.parser_factory import ParserFactory
from babelfishers.core.run_lock import RunLockStore, compute_config_fingerprint
from babelfishers.core.tm_store import TMStore
from babelfishers.core.translation_pipeline import TranslationPipeline
from babelfishers.models.app_config import AppConfig
from babelfishers.models.run_lock import RunLockEntry
from babelfishers.models.translation_resource import ResourcePath
from babelfishers.models.translations import ParseResult
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import get_translation_store_storage_path, hash_file_contents


class Runtime:
    def __init__(
        self,
        config: AppConfig,
        db_storage: Path | None = None,
        dry_run: bool = False,
        max_workers: int = 8,
    ) -> None:
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._config: AppConfig = config
        self._dry_run: bool = dry_run
        self._tm_store: TMStore = TMStore(db_storage or get_translation_store_storage_path())
        self._run_lock_store: RunLockStore = RunLockStore()
        self._config_fingerprint: str = compute_config_fingerprint(config)
        self._max_workers = max_workers

    def orchestrate_translation_workflow(self) -> None:
        run_lock_entries: list[RunLockEntry] = []

        try:
            with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
                futures: dict[Future[RunLockEntry], str] = {}

                if len(self._config.resources) == 0:
                    self._logger.warning(
                        ConsoleFormatter.warning(
                            "No resources found in the configuration. Please check your configuration file."
                        )
                    )

                for resource in self._config.resources:
                    if len(resource.paths) == 0:
                        self._logger.warning(
                            ConsoleFormatter.warning(
                                f"Skipping bucket: '{resource.resource_type}'. Reason: Bucket empty"
                            )
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
                        content_hash = hash_file_contents(source_path)

                        stale_locales = [
                            locale
                            for locale in self._config.target_locales
                            if self._run_lock_store.is_stale(
                                path=str(source_path),
                                locale=locale,
                                content_hash=content_hash,
                                config_fingerprint=self._config_fingerprint,
                                destination_path=resource_path.get_destination_path(locale),
                            )
                        ]

                        if not stale_locales:
                            self._logger.info(
                                ConsoleFormatter.info(f"{source_path} -> Up to date for every target locale, skipping")
                            )
                            continue

                        parse_result = parser.parse(
                            source_path=source_path,
                            excluded_keys=resource.excluded_keys,
                        )

                        for locale in stale_locales:
                            future = executor.submit(
                                self._run_single_locale,
                                pipeline,
                                parser.clone(parse_result),
                                resource_path,
                                locale,
                                source_path,
                                content_hash,
                            )
                            futures[future] = f"[{self._config.source_locale} - {locale}] {source_path}"

                for future in as_completed(futures):
                    job_label = futures[future]
                    try:
                        run_lock_entries.append(future.result())
                    except Exception as exe:
                        self._logger.exception(ConsoleFormatter.error(f"{job_label} -> Pipeline failed"), exc_info=exe)
                        raise
        finally:
            # Best-effort: whatever succeeded before a failure is still recorded,
            # so a re-run doesn't re-translate files that already completed.
            self._run_lock_store.create(run_lock_entries)

    def _run_single_locale(
        self,
        pipeline: TranslationPipeline,
        parse_result: ParseResult,
        resource_path: ResourcePath,
        locale: str,
        source_path: Path,
        content_hash: str,
    ) -> RunLockEntry:
        self._logger.info(
            ConsoleFormatter.info(f"[{self._config.source_locale} - {locale}] -> Running translation for {source_path}")
        )

        destination = resource_path.get_destination_path(locale)
        pipeline.run(parse_result, self._config.source_locale, locale, destination)

        self._logger.info(
            ConsoleFormatter.success(f"[{self._config.source_locale} - {locale}] -> Pipeline success for {source_path}")
        )

        return RunLockEntry(
            path=str(source_path),
            locale=locale,
            content_hash=content_hash,
            config_fingerprint=self._config_fingerprint,
            last_run_at=int(time.time()),
        )
