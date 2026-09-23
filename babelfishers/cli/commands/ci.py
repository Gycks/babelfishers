import click

from babelfishers.cli.project import load_app_config
from babelfishers.core.ci_runners import CIRunnerType


@click.command(
    name="ci",
    help="Translate the project files on a CI runner and write the changes back through a pull request.",
)
@click.argument("platform", nargs=1, type=click.Choice(CIRunnerType, case_sensitive=False))
@click.option(
    "--pull-request",
    is_flag=True,
    help="Open a new pull request from a bot branch instead of updating the current one.",
)
@click.option("--pull-request-title", help="Title of a new pull request. Defaults to the commit message.")
@click.option("--pull-request-body", help="Description of a new pull request.")
@click.option("--commit-message", help="Message of the commit that holds the translations.")
def ci(
    platform: CIRunnerType,
    pull_request: bool,
    pull_request_title: str | None,
    pull_request_body: str | None,
    commit_message: str | None,
) -> None:
    from babelfishers.core.ci_orchestra import CIOrchestra
    from babelfishers.models.ci import CIRunConfig

    given = {
        "pull_request_title": pull_request_title,
        "pull_request_body": pull_request_body,
        "commit_message": commit_message,
    }

    runner = CIOrchestra(load_app_config())
    options = CIRunConfig(
        platform=platform,
        pull_request=pull_request,
        **{name: value for name, value in given.items() if value is not None},
    )
    runner.run(options)
