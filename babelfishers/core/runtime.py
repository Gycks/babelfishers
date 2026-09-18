import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from babelfishers.core.parsers.parser_factory import ParserFactory
from babelfishers.core.run_lock import RunLockStore, compute_config_fingerprint
from babelfishers.core.tm_store import TMStore
from babelfishers.core.translation_pipeline import TranslationPipeline
from babelfishers.models.app_config import AppConfig
from babelfishers.models.engine import Engine
from babelfishers.models.plan import LocalePlan
from babelfishers.models.run_lock import RunLockEntry
from babelfishers.models.translations import ParseResult
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import get_translation_store_storage_path, hash_file_contents


@dataclass
class _StaleJob:
    plan: LocalePlan
    pipeline: TranslationPipeline
    parse_result: ParseResult
    content_hash: str


class Runtime:
    def __init__(
        self,
        config: AppConfig,
        db_storage: Path | None = None,
        max_workers: int = 8,
    ) -> None:
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._config: AppConfig = config
        self._tm_store_path: Path = db_storage or get_translation_store_storage_path()
        self._run_lock_store: RunLockStore = RunLockStore()
        self._config_fingerprint: str = compute_config_fingerprint(config)
        self._max_workers = max_workers

    def plan(self) -> list[LocalePlan]:
        """
        Work out what `orchestrate_translation_workflow` would do, without doing it.

        Read-only: no provider is called, no file is written, the run lock is left
        alone, and the translation memory is neither created nor updated.

        Returns:
            One entry per source file and target locale, stale ones carrying a volume estimate.
        """
        tm_store = TMStore(self._tm_store_path) if self._tm_store_path.exists() else None
        plans, stale_jobs = self._collect_jobs(tm_store)

        for job in stale_jobs:
            job.plan.volume = job.pipeline.plan(job.parse_result, self._config.source_locale, job.plan.locale)

        return plans

    def orchestrate_translation_workflow(self) -> None:
        plans, stale_jobs = self._collect_jobs(TMStore(self._tm_store_path))
        self._log_up_to_date(plans)

        run_lock_entries: list[RunLockEntry] = []

        try:
            with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
                futures: dict[Future[RunLockEntry], str] = {
                    executor.submit(self._run_single_locale, job): (
                        f"[{self._config.source_locale} - {job.plan.locale}] {job.plan.source_path}"
                    )
                    for job in stale_jobs
                }

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
            # Entries for files or locales that left the project would otherwise stay forever.
            self._run_lock_store.remove_orphans({(str(plan.source_path), plan.locale) for plan in plans})

    def refresh_run_lock(self) -> tuple[int, int]:
        """
        Rebuild the run lock from the current state alone: the config, the source files and the
        target files already on disk. Every target that exists is recorded as up to date for its
        current source, nothing is translated, and entries for anything else are dropped.

        Returns:
            How many (source file, locale) pairs were recorded, and how many were skipped because
            the target file does not exist.
        """
        entries: list[RunLockEntry] = []
        skipped = 0
        now = int(time.time())

        for resource in self._config.resources:
            for resource_path in resource.paths:
                content_hash = hash_file_contents(resource_path.path)
                for locale in self._config.target_locales:
                    if not resource_path.get_destination_path(locale).exists():
                        skipped += 1
                        continue

                    entries.append(
                        RunLockEntry(
                            path=str(resource_path.path),
                            locale=locale,
                            content_hash=content_hash,
                            config_fingerprint=self._config_fingerprint,
                            last_run_at=now,
                        )
                    )

        self._run_lock_store.replace(entries)
        return len(entries), skipped

    def _collect_jobs(self, tm_store: TMStore | None) -> tuple[list[LocalePlan], list[_StaleJob]]:
        plans: list[LocalePlan] = []
        stale_jobs: list[_StaleJob] = []

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
                        f"An entry in the {resource.resource_type.upper()} resource bucket "
                        f"will be skipped. Reason: Entry has no valid paths. "
                        f"Please check your configuration file."
                    )
                )
                continue

            parser = ParserFactory.create(resource.resource_type)

            engines: list[Engine] = []
            if resource.engine:
                engines.append(resource.engine)
            engines.append(self._config.translation_engine)

            pipeline = TranslationPipeline(
                translation_engines=engines,
                glossary=self._config.glossary,
                translation_store=tm_store,
            )

            for resource_path in resource.paths:
                source_path = resource_path.path
                content_hash = hash_file_contents(source_path)

                file_plans: list[LocalePlan] = []
                for locale in self._config.target_locales:
                    destination = resource_path.get_destination_path(locale)
                    file_plans.append(
                        LocalePlan(
                            source_path=source_path,
                            locale=locale,
                            destination=destination,
                            engines=engines,
                            stale_reason=self._run_lock_store.stale_reason(
                                path=str(source_path),
                                locale=locale,
                                content_hash=content_hash,
                                config_fingerprint=self._config_fingerprint,
                                destination_path=destination,
                            ),
                        )
                    )

                plans.extend(file_plans)

                stale_plans = [plan for plan in file_plans if plan.is_stale]
                if not stale_plans:
                    continue

                parse_result = parser.parse(
                    source_path=source_path,
                    excluded_keys=resource.excluded_keys,
                )

                for plan in stale_plans:
                    stale_jobs.append(_StaleJob(plan, pipeline, parser.clone(parse_result), content_hash))

        return plans, stale_jobs

    def _log_up_to_date(self, plans: list[LocalePlan]) -> None:
        stale_paths = {plan.source_path for plan in plans if plan.is_stale}
        logged: set[Path] = set()

        for plan in plans:
            if plan.source_path in stale_paths or plan.source_path in logged:
                continue

            logged.add(plan.source_path)
            self._logger.info(
                ConsoleFormatter.info(f"{plan.source_path} -> Up to date for every target locale, skipping")
            )

    def _run_single_locale(self, job: _StaleJob) -> RunLockEntry:
        plan = job.plan
        source_locale = self._config.source_locale

        self._logger.info(
            ConsoleFormatter.info(f"[{source_locale} - {plan.locale}] -> Running translation for {plan.source_path}")
        )

        job.pipeline.run(job.parse_result, source_locale, plan.locale, plan.destination)

        self._logger.info(
            ConsoleFormatter.success(f"[{source_locale} - {plan.locale}] -> Pipeline success for {plan.source_path}")
        )

        return RunLockEntry(
            path=str(plan.source_path),
            locale=plan.locale,
            content_hash=job.content_hash,
            config_fingerprint=self._config_fingerprint,
            last_run_at=int(time.time()),
        )
