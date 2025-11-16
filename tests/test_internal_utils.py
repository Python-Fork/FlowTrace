import sys

import flowtrace
from flowtrace.monitoring import _is_user_code, _is_user_path


def test_is_user_code_and_path_filters_work():
    # 1. код библиотеки должен быть "внутренним"
    code = flowtrace.start_tracing.__code__
    assert _is_user_code(code) is False

    # 2. путь стандартного Python точно не "user"
    assert _is_user_path(sys.executable) is False

    # 3. сам файл теста должен считаться "user"
    assert _is_user_path(__file__) is True
