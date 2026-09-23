# Continuous integration

The `babelfishers ci` command runs your translations inside a CI pipeline. It writes the result back to your repository through a pull request. Nobody has to run the tool by hand.

It works with GitHub Actions and GitLab CI/CD.

```bash
babelfishers ci github --pull-request
```

## How it works

1. **Check the setup.** Babel Fishers confirms that it runs on the platform you named and that your token is set.
2. **Decide whether to skip.** Some runs are skipped so the bot never reacts to its own work. See [When a run is skipped](#when-a-run-is-skipped).
3. **Translate.** It runs the same translation as `babelfishers translate`. Only files that need work are translated.
4. **Commit.** The changed files are committed under the name Babel Fishers.
5. **Publish.** The commit goes into a new pull request or into the current one.

If the run changes nothing, nothing is committed.

## Choose a mode

There are two modes. You pick one with the `--pull-request` option.

| | New pull request | Update the current pull request |
|---|---|---|
| Option | `--pull-request` | None |
| Runs on | A branch, such as `main` | A pull request |
| Result | A pull request with the translations | A new commit on the branch of that pull request |
| Good for | Reviewing translations on their own | Translations that arrive with the change that caused them |

### New pull request

Run it on a branch, not on a tag. It must not run as part of a pull request.

The commit goes to a branch that belongs to the bot. Each branch of yours gets one bot branch. For `main` it is `babelfishers/translations/main`. For `release/1.0` it is `babelfishers/translations/release_2F1.0`.

The bot branch is pushed again on every run, so it always sits on the current base branch. A pull request is opened from it. If one is already open, it is updated and no second one is created.

### Update the current pull request

Run it as part of a pull request. The pull request must come from the same repository.

The checkout must be the latest commit of the branch of that pull request. Some platforms check out the merge result by default. GitHub does this for pull request runs. Change that, or the run stops with an error.

## Set up credentials

A CI run needs two kinds of credentials.

**Provider credentials.** These are the usual variables of your [translation provider](providers.md), such as `BF_DEEPL_API_KEY`.

**A token for your platform.** Babel Fishers needs it to push commits and to open pull requests. The token that the platform gives to a job is not enough, so you create your own.

| Platform | Variable | Token to create |
|---|---|---|
| GitHub Actions | `BF_GITHUB_TOKEN` | A personal access token with write access to the repository contents and pull requests. |
| GitLab CI/CD | `BF_GITLAB_TOKEN` | A project access token with the `api` and `write_repository` scopes. |

On GitHub, commits pushed with the built-in `GITHUB_TOKEN` do not start other workflows. The checks of the pull request would never run. That is why you pass a personal token.

Store every key and token as a secret of your platform.

!!! warning "Keep keys out of your repository"

    Never write a key or a token in a file that you commit.

The platform sets some variables by itself. Babel Fishers reads them to confirm where it runs.

| Platform | Variables set by the platform |
|---|---|
| GitHub Actions | `GITHUB_ACTIONS`, `GITHUB_REPOSITORY`, `GITHUB_REF_NAME`, `GITHUB_SERVER_URL`, `GITHUB_API_URL` |
| GitLab CI/CD | `GITLAB_CI`, `CI_PROJECT_ID`, `CI_SERVER_URL`, `CI_API_V4_URL`, `CI_COMMIT_REF_NAME`, `CI_DEFAULT_BRANCH` |

## Examples

The job needs `git` and Python 3.11 or newer. These examples install Babel Fishers with `pip`.

### Open a pull request after every push to the main branch

=== "GitHub Actions"

    ```yaml
    name: translations
    on:
      push:
        branches: [main]

    jobs:
      translate:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-python@v5
            with:
              python-version: "3.12"
          - run: pip install babelfishers
          - run: babelfishers ci github --pull-request
            env:
              BF_DEEPL_API_KEY: ${{ secrets.BF_DEEPL_API_KEY }}
              BF_GITHUB_TOKEN: ${{ secrets.BF_GITHUB_TOKEN }}
    ```

=== "GitLab CI/CD"

    ```yaml
    translate:
      image: python:3.12
      rules:
        - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
      script:
        - pip install babelfishers
        - babelfishers ci gitlab --pull-request
    ```

    Add `BF_DEEPL_API_KEY` and `BF_GITLAB_TOKEN` as masked variables in the CI/CD settings of the project.

### Add translations to each pull request

This example is for GitHub Actions. It checks out the branch of the pull request itself, and not the merge result.

```yaml
name: translations
on:
  pull_request:

jobs:
  translate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.head_ref }}
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install babelfishers
      - run: babelfishers ci github
        env:
          BF_DEEPL_API_KEY: ${{ secrets.BF_DEEPL_API_KEY }}
          BF_GITHUB_TOKEN: ${{ secrets.BF_GITHUB_TOKEN }}
```

For GitLab, use a pipeline for merge requests and make sure that the checkout is the latest commit of the branch. Otherwise the run stops with the error described under [If a run fails](#if-a-run-fails).

## What is committed

The commit holds these files.

- The translated files.
- The translation memory and the run record in `.babelfishers`, when they changed. They are added even if your `.gitignore` lists them. That way the memory stays current in your repository.

The commit is made by `Babel Fishers <bot@babelfishers.local>`. Git hooks are skipped.

You can change the text with these options.

| Option | What it sets | Default |
|---|---|---|
| `--commit-message` | The message of the commit. | `chore: update translations` |
| `--pull-request-title` | The title of a new pull request. | The commit message. |
| `--pull-request-body` | The description of a new pull request. | `Babel Fishers bot: Localization workflow completed successfully.` |

The title and body options only apply in the new pull request mode.

## When a run is skipped

Some runs end early, without translating. The log says `Skipping the CI run` and gives the reason. This keeps the bot from reacting to its own work.

- The run is on a bot branch.
- The latest commit was made by Babel Fishers.
- The mode is update and the pull request comes from a fork. The token cannot push to a fork.

Two other cases end the run without an error. The message is a warning.

- The run is not on the platform that you named.
- The token variable of that platform is empty or missing.

!!! note "A missing token does not fail the job"

    If `BF_GITHUB_TOKEN` or a similar variable is missing, the command warns and stops. The job still passes. Read the log if no pull request appears.

## If a run fails

| Message | What to do |
|---|---|
| Not running on a platform, with a variable that is not set | You named the wrong platform, or the command does not run inside that CI system. |
| The environment variable is not set | Add the token as a secret and pass it to the step in `env`. |
| This run belongs to a pull request. Opening a new pull request from here would duplicate it | Remove `--pull-request`, or run the job on a branch. |
| This run does not belong to a pull request, so there is nothing to update | Add `--pull-request`, or run the job for pull requests. |
| The checkout is not the latest commit of the branch | Check out the branch of the pull request itself, not the merge result. |
| Could not tell which branch is running | Run the job on a branch, not on a tag. |
| An API call failed with HTTP 401 or 403 | Check that the token is valid and has the scopes listed above. |
| A git push failed | The token may lack write access, or the branch may be protected. |

See the [CLI reference](../reference/cli.md) for every option.
