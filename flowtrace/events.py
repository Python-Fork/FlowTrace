from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class ExecutionContext:
    """
    Общий контекст исполнения (поток/таска и т.п.).
    Пока можем использовать только thread_id, но оставляем
    поля под future-async.
    """

    thread_id: int
    task_id: int | None = None
    task_parent_id: int | None = None
    task_name: str | None = None


@dataclass
class CallEvent:
    id: int
    kind: str
    func_name: str
    parent_id: int | None = None

    # payload (заполняются строго по флагам)
    args_repr: str | None = None
    result_repr: str | None = None
    duration: float | None = None

    # для exception
    exc_type: str | None = None
    exc_msg: str | None = None
    caught: bool | None = None  # None = "открытое", True = "поймано", False = "ушло наружу"
    via_exception: bool = False
    exc_tb: str | None = None  # компактный срез traceback (если собирали)

    # флаги того, что ДОЛЖНО было собираться для этого вызова
    collect_args: bool = False
    collect_result: bool = False
    collect_timing: bool = False

    context: ExecutionContext | None = None


@dataclass
class AsyncTransitionEvent:
    """
    Событие перехода в async-мире:
    - 'await'   — корутина ушла в ожидание
    - 'resume'  — корутина возобновилась
    - 'yield'   — async-генератор отдал значение
    """

    id: int
    kind: Literal["await", "resume", "yield"]
    func_name: str

    # связь с async-контекстом
    async_id: int | None = None
    parent_async_id: int | None = None

    # Доп. инфа (например, что именно ждём / значение yield)
    detail: str | None = None

    # Привязка к ExecutionContext
    context: ExecutionContext | None = None


@dataclass
class ExceptionEvent:
    """
    Отдельное событие исключения.
    На следующих шагах постепенно заменим использование
    exception-полей в CallEvent на этот тип.
    """

    id: int
    kind: Literal["exception"] = "exception"
    func_name: str = ""
    parent_id: int | None = None

    exc_type: str | None = None
    exc_msg: str | None = None
    caught: bool | None = None  # None – неизвестно, True – поймано, False – ушло наружу
    via_exception: bool = False
    exc_tb: str | None = None  # компактный traceback

    # опционально маппимся на ExecutionContext:
    context: ExecutionContext | None = None


TraceEvent = CallEvent | AsyncTransitionEvent | ExceptionEvent
