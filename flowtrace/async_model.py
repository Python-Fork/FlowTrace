from __future__ import annotations

from dataclasses import dataclass, field

from .events import ExecutionContext


@dataclass(slots=True)
class AwaitSegment:
    """
    Описывает один 'await'-интервал внутри таски.

    Это не исходное событие из sys.monitoring, а реконструированная сущность:
    - где (в каком вызове) мы ждали,
    - по каким событиям (await/resume),
    - сколько это заняло времени,
    - какие дочерние таски/работа прошли внутри окна ожидания.
    """

    # ID CallEvent, внутри которого случился await (если удалось определить).
    # Может быть -1, если мы не смогли однозначно привязаться к вызову.
    call_id: int

    # ID AsyncTransitionEvent с kind="await"
    await_event_id: int

    # ID AsyncTransitionEvent с kind="resume" (если был найден),
    # иначе None – незакрытый await (например, корутина не успела возобновиться).
    resume_event_id: int | None = None

    # Временные метки.
    start_ts: float | None = None
    end_ts: float | None = None

    duration: float | None = None

    # Дополнительная информация об ожидании:
    # - repr ожидаемого объекта
    # - текстовое описание источника ожидания
    detail: str | None = None

    # Вложенная работа, пришедшаяся на этот await-интервал.
    children_task_ids: list[int] = field(default_factory=list)


@dataclass(slots=True)
class TaskTrace:
    """
    Реконструированное представление выполнения одной asyncio.Task.

    Это "второй слой" над сырыми событиями:
    - дерево вызовов внутри таски (по CallEvent'ам),
    - список await-интервалов,
    - связь с родительской таской,
    - быстрый доступ к ExecutionContext'у.
    """

    # Идентификатор таски (совпадает с ExecutionContext.task_id).
    task_id: int

    # Родительская таска, если известна (по ExecutionContext.task_parent_id).
    parent_task_id: int | None

    # Человекочитаемое имя таски (ExecutionContext.task_name).
    task_name: str | None

    # Поток, в котором выполняется эта таска (ExecutionContext.thread_id).
    thread_id: int

    # "Корни" дерева вызовов внутри таски:
    # CallEvent.id, у которых либо parent_id is None,
    # либо родитель относится к другой таске.
    roots: list[int] = field(default_factory=list)

    # Дети для каждого вызова: call_id -> [child_call_id, ...]
    call_children: dict[int, list[int]] = field(default_factory=dict)

    # Все await-интервалы внутри этой таски
    await_segments: list[AwaitSegment] = field(default_factory=list)

    # ID всех событий (CallEvent / ExceptionEvent / AsyncTransitionEvent),
    # которые принадлежат этой таске (по context.task_id).
    # Порядок – как в исходном логе событий TraceSession.
    event_ids: list[int] = field(default_factory=list)

    # Индекс (по глобальному списку событий), где эта таска "появилась" впервые.
    first_event_index: int | None = None

    # ExecutionContext последнего события этой таски.
    last_context: ExecutionContext | None = None
