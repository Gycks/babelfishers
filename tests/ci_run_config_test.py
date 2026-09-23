import pytest
from pydantic import ValidationError

from babelfishers.core.ci_runners import CIRunnerType
from babelfishers.models.ci import CIRunConfig, bot_branch_name, is_bot_branch


def _config(**overrides) -> CIRunConfig:
    return CIRunConfig(platform=CIRunnerType.GITHUB, pull_request=True, **overrides)


class TestCIRunConfig:
    def test_optional_fields_have_defaults(self):
        config = _config()

        assert config.pull_request_title == ""
        assert config.pull_request_body.startswith("Babel Fishers bot")
        assert config.commit_message == "chore: update translations"

    def test_has_no_base_or_branch_name_option(self):
        for option in ("base_branch", "branch_name"):
            with pytest.raises(ValidationError):
                _config(**{option: "main"})

    def test_config_is_immutable(self):
        with pytest.raises(ValidationError):
            _config().commit_message = "other"


class TestBotBranchName:
    def test_is_derived_from_the_base_branch(self):
        assert bot_branch_name("main") == "babelfishers/translations/main"

    def test_keeps_a_slash_in_the_base_branch_out_of_the_ref_path(self):
        assert bot_branch_name("release/1.0") == "babelfishers/translations/release_2F1.0"

    def test_distinct_base_branches_never_share_a_bot_branch(self):
        bases = ["a/b", "a_b", "a-b", "a_2Fb", "a", "A", "a b", "é", "a/b/c", "a/b_c", "a_b/c"]

        assert len({bot_branch_name(base) for base in bases}) == len(bases)

    def test_bot_branches_never_nest_inside_each_other(self):
        prefix = "babelfishers/translations/"
        names = [bot_branch_name(base) for base in ("a", "a/b", "a/b/c")]

        assert all("/" not in name.removeprefix(prefix) for name in names)

    def test_needs_a_known_base_branch(self):
        with pytest.raises(ValueError, match="base branch"):
            bot_branch_name("")

    def test_is_recognised_as_a_bot_branch(self):
        assert is_bot_branch(bot_branch_name("main"))
        assert not is_bot_branch("main")
        assert not is_bot_branch("babelfishers")


class TestCIRunConfigRepr:
    def test_shows_the_platform_and_the_mode(self):
        assert repr(_config()).startswith("CIRunConfig(platform='github', pull_request=True, ")

    def test_shows_the_title_only_when_it_is_set(self):
        assert "pull_request_title" not in repr(_config())
        assert "pull_request_title='Update translations'" in repr(_config(pull_request_title="Update translations"))

    def test_shows_the_commit_message(self):
        assert "commit_message='feat: translate'" in repr(_config(commit_message="feat: translate"))

    def test_shortens_long_text_so_the_line_stays_readable(self):
        config = _config(pull_request_body="x" * 500)

        assert "pull_request_body='" + "x" * 39 + "…'" in repr(config)
        assert len(repr(config)) < 250

    def test_str_matches_repr_so_f_string_logging_reads_the_same(self):
        assert str(_config()) == repr(_config())
