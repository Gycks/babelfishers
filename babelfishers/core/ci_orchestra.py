import logging
from pathlib import Path

from babelfishers.core.ci_runners.runner import CIRunnerFactory
from babelfishers.core.runtime import Runtime
from babelfishers.models.app_config import AppConfig
from babelfishers.models.ci import CIRunConfig
from babelfishers.utils.console_formater import ConsoleFormatter


class CIOrchestra:
    def __init__(self, config: AppConfig, db_storage: Path | None = None) -> None:
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._translation_runtime: Runtime = Runtime(config, db_storage)

    def run(self, options: CIRunConfig) -> None:
        self._logger.info(ConsoleFormatter.info(f"CI run with options\n{options}"))
        runner = CIRunnerFactory.create(options.platform)
        if not runner.validate():
            return

        reason = runner.skip_reason(options)
        if reason:
            self._logger.info(ConsoleFormatter.info(f"Skipping the CI run: {reason}"))
            return

        runner.check_context(options)

        run_result = self._translation_runtime.orchestrate_translation_workflow()
        if run_result.empty:
            return
        runner.publish(run_result.paths, options)
