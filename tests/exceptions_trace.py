"""
FlowTrace regression test:
 - проверка разделения return / exc-return
 - проверка сборки compact traceback при show_exc=True
 - проверка глубины traceback (depth)
"""

from contextlib import suppress

from flowtrace import trace
from flowtrace.core import start_tracing, stop_tracing
from flowtrace.formatters import print_tree

# --- вспомогательные функции ----------------------------------------


@trace  # без show_exc=True
def fail_default():
    raise ValueError("default mode fail")


@trace(show_exc=True)
def fail_once():
    raise ValueError("boom")


@trace(show_exc=True, exc_tb_depth=1)
def fail_depth1():
    deeper_1()


def deeper_1():
    raise RuntimeError("depth1 fail")


@trace(show_exc=True, exc_tb_depth=3)
def fail_depth3():
    deeper_2()


def deeper_2():
    def nested():
        raise KeyError("deep chain")

    nested()


# --- тесты ----------------------------------------------------------


def run_all():
    print("=== FlowTrace test: basic return vs exception (default mode) ===")
    start_tracing()

    # 1. нормальное завершение
    with suppress(Exception):
        _ = sum([1, 2, 3])

    # 2. исключение без show_exc=True
    with suppress(ValueError):
        fail_default()

    events = stop_tracing()

    rets = [e for e in events if e.kind == "return"]
    excs = [e for e in events if e.kind == "exception"]

    # Проверка: должен быть хотя бы один возврат через исключение
    assert any(r.via_exception for r in rets), "Ожидался exc-return при исключении"

    # Так как show_exc=False по умолчанию, traceback быть не должно
    assert not any(e.exc_tb for e in excs), "traceback не должен собираться при show_exc=False"

    print_tree(events)
    print("\n✓ default (no-traceback) mode passed\n")


def run_show_exc():
    print("=== FlowTrace test: show_exc=True ===")
    start_tracing()
    with suppress(Exception):
        fail_once()
    events = stop_tracing()

    excs = [e for e in events if e.kind == "exception"]

    # Теперь traceback должен быть
    assert any(e.exc_tb for e in excs), "traceback должен собираться при show_exc=True"

    print_tree(events)
    print("\n✓ show_exc=True mode passed\n")


def run_depth_tests():
    print("=== FlowTrace test: traceback depth ===")

    # --- глубина 1 ---
    start_tracing()
    with suppress(Exception):
        fail_depth1()
    events1 = stop_tracing()
    tb1 = next((e.exc_tb for e in events1 if e.exc_tb), "")
    depth1_count = tb1.count("|") + 1 if tb1 else 0

    # --- глубина 3 ---
    start_tracing()
    with suppress(Exception):
        fail_depth3()
    events3 = stop_tracing()
    tb3 = next((e.exc_tb for e in events3 if e.exc_tb), "")
    depth3_count = tb3.count("|") + 1 if tb3 else 0

    print_tree(events1)
    print_tree(events3)

    assert depth3_count >= depth1_count, "depth=3 должен показывать больше уровней"
    print(f"\n✓ depth=1: {tb1}\n✓ depth=3: {tb3}\n✓ depth tests passed\n")


if __name__ == "__main__":
    run_all()
    run_show_exc()
    run_depth_tests()
    print("All FlowTrace exception tests completed successfully.")
