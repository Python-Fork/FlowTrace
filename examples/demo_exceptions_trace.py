"""
FlowTrace demo: ловим все типы исключений.
Цель — увидеть события RAISE / RERAISE / PY_UNWIND / EXCEPTION_HANDLED / C_RAISE в действии.
"""

from flowtrace import trace


# --- 1. Простое необработанное исключение ---
@trace
def uncaught_division_by_zero():
    # типичный RAISE → PY_UNWIND
    return 10 / 0


# --- 2. Исключение, пойманное локально ---
@trace
def handled_value_error():
    try:
        int("xyz")  # C_RAISE → RAISE → EXCEPTION_HANDLED
    except ValueError as e:
        print(f"[handled_value_error] caught: {e}")
    finally:
        pass
    return "done"


# --- 3. Перевыброс исключения ---
@trace
def re_raise_example():
    try:
        bad_operation()
    except Exception as e:
        print(f"[re_raise_example] rethrowing: {e}")
        raise  # RERAISE событие


def bad_operation():
    raise RuntimeError("boom!")  # RAISE → PY_UNWIND


# --- 4. Исключение, пойманное выше ---
@trace
def propagate_example():
    try:
        fail_inside()
    except Exception:
        print("[propagate_example] caught propagated error")


def fail_inside():
    deeper()


def deeper():
    raise ValueError("deep fail")  # RAISE → PY_UNWIND → EXCEPTION_HANDLED


# --- 5. Исключение в finally ---
@trace
def finally_raises():
    try:
        print("→ try block")
    finally:
        raise KeyError("raised in finally")  # RAISE + PY_UNWIND (finally unwind)


# --- 6. Комбинированный сценарий ---
@trace
def combined():
    try:
        handled_value_error()
        re_raise_example()
    except Exception as e:
        print(f"[combined] caught outer exception: {e}")
    finally:
        print("[combined] cleanup done")


if __name__ == "__main__":
    print("=== FlowTrace Exception Demo ===")

    # каждый вызов независим, чтобы дерево было читаемым
    # try:
    #     handled_value_error()
    # except Exception as e:
    #     print("Should not happen:", e)

    # try:
    #     uncaught_division_by_zero()
    # except Exception as e:
    #     print(f"[main] caught top-level: {type(e).__name__}: {e}")

    # try:
    #     propagate_example()
    # except Exception as e:
    #     print("[main] unexpected:", e)
    #
    # try:
    #     re_raise_example()
    # except Exception as e:
    #     print(f"[main] reraised: {e}")

    # try:
    #     finally_raises()
    # except Exception as e:
    #     print(f"[main] finally raised: {e}")

    print("\n=== Combined scenario ===")
    combined()