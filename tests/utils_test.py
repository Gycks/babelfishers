import pytest

from babelfishers.utils.utils import atomic_write, detect_newline


class TestAtomicWrite:
    def test_writes_the_given_content_to_the_destination(self, tmp_path):
        destination = tmp_path / "out.txt"

        atomic_write(destination, lambda tmp: tmp.write_text("hello", encoding="utf-8"))

        assert destination.read_text(encoding="utf-8") == "hello"

    def test_creates_parent_directories_if_missing(self, tmp_path):
        destination = tmp_path / "nested" / "dir" / "out.txt"

        atomic_write(destination, lambda tmp: tmp.write_text("hello", encoding="utf-8"))

        assert destination.read_text(encoding="utf-8") == "hello"

    def test_does_not_leave_a_temp_file_behind_on_success(self, tmp_path):
        destination = tmp_path / "out.txt"

        atomic_write(destination, lambda tmp: tmp.write_text("hello", encoding="utf-8"))

        assert list(tmp_path.iterdir()) == [destination]

    def test_overwrites_an_existing_file(self, tmp_path):
        destination = tmp_path / "out.txt"
        destination.write_text("original", encoding="utf-8")

        atomic_write(destination, lambda tmp: tmp.write_text("replaced", encoding="utf-8"))

        assert destination.read_text(encoding="utf-8") == "replaced"

    def test_leaves_the_original_file_untouched_when_the_writer_raises(self, tmp_path):
        destination = tmp_path / "out.txt"
        destination.write_text("original", encoding="utf-8")

        def _failing_writer(tmp):
            tmp.write_text("partial", encoding="utf-8")
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            atomic_write(destination, _failing_writer)

        assert destination.read_text(encoding="utf-8") == "original"

    def test_does_not_leave_a_temp_file_behind_when_the_writer_raises(self, tmp_path):
        destination = tmp_path / "out.txt"
        destination.write_text("original", encoding="utf-8")

        def _failing_writer(tmp):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            atomic_write(destination, _failing_writer)

        assert list(tmp_path.iterdir()) == [destination]


class TestDetectNewline:
    def test_detects_crlf(self):
        assert detect_newline("a\r\nb\r\n") == "\r\n"

    def test_detects_lf(self):
        assert detect_newline("a\nb\n") == "\n"

    def test_defaults_to_lf_when_no_newline_is_present(self):
        assert detect_newline("no newline here") == "\n"

    def test_defaults_to_lf_for_empty_text(self):
        assert detect_newline("") == "\n"
