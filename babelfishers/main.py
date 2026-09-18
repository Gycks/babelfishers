import logging
import sys

from babelfishers.cli.main import main


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

sys.tracebacklimit = 0  # Disable traceback for unhandled exceptions


def run() -> None:
    """Run the Babel Fishers command line interface."""
    main()


if __name__ == "__main__":
    run()
