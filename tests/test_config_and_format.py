import pytest

from flowtrace.config import Config, config, get_config
from flowtrace.core import CallEvent
from flowtrace.formatters import print_tree


@pytest.fixture(autouse=True)
def reset_config():
    config(
        show_args=True,
        show_result=True,
        show_timing=True,
        show_exc=False,
        inline_return=False,
    )


def test_config_update_and_aliases():
    # базовая проверка обновления
    cfg1 = config(show_exc=3, inline_return=True)
    assert isinstance(cfg1, Config)
    assert cfg1.show_exc == 3
    assert cfg1.inline_return is True

    # alias: exc_tb_depth
    cfg3 = config(exc_tb_depth=5)
    assert cfg3.show_exc == 5


def test_exc_depth_resolution():
    config(show_exc=True)
    cfg = get_config()
    assert cfg.exc_enabled() is True
    assert cfg.exc_depth() == 2

    config(show_exc=4)
    cfg = get_config()
    assert cfg.exc_depth() == 4

    config(show_exc=False)
    cfg = get_config()
    assert cfg.exc_enabled() is False


def test_inline_return_output(capsys):
    events = [
        CallEvent(id=0, kind="call", func_name="foo"),
        CallEvent(id=1, kind="return", func_name="foo", parent_id=0, result_repr="'ok'"),
    ]
    config(inline_return=True)
    print_tree(events)
    output = capsys.readouterr().out.strip()
    assert "foo()" in output and "→ 'ok'" in output


def test_multiline_return_output(capsys):
    events = [
        CallEvent(id=0, kind="call", func_name="bar"),
        CallEvent(id=1, kind="return", func_name="bar", parent_id=0, result_repr="'ok'"),
    ]
    config(inline_return=False)
    print_tree(events)
    output = capsys.readouterr().out.strip()
    # в многострочном стиле две строки
    lines = output.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("→ bar()")
    assert lines[-1].startswith("← bar()")
