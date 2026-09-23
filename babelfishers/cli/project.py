from babelfishers.cli import ui
from babelfishers.cli.errors import CliError
from babelfishers.models.app_config import AppConfig


def load_app_config() -> AppConfig:
    from babelfishers.utils.utils import get_app_config_storage_path

    config_path = get_app_config_storage_path()
    if not config_path.exists():
        raise CliError(
            f"No Babel Fishers project found at {config_path}. Run '{ui.command('babelfishers init')}' first."
        )

    return AppConfig.load(config_path)
