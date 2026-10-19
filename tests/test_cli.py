import pytest

from netsy.cli.main import main


def test_unknown_command_is_a_usage_error():
    with pytest.raises(SystemExit) as exit_info:
        main(["synth", "supply"])
    assert exit_info.value.code == 2
