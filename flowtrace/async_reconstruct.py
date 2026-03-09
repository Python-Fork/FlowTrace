from __future__ import annotations

from collections import defaultdict

from .async_model import AwaitSegment, TaskTrace
from .events import AsyncTransitionEvent, CallEvent, TraceEvent


def build_task_traces(events: list[TraceEvent]) -> dict[int, TaskTrace]:
    """
    Построить TaskTrace для всех asyncio.Task на основе полного списка событий.

    A) Разложить события по таскам.
    B) Построить дерево вызовов (roots + call_children) внутри каждой таски.
    C) Построить await-сегменты: *одна серия await до первого resume = один логический await*.
    D) Привязать дочерние таски к await-окнам.
    """

    tasks: dict[int, TaskTrace] = {}

    # -------------------------
    # A) Разложить события по таскам
    # -------------------------
    for index, ev in enumerate(events):
        ctx = getattr(ev, "context", None)
        if ctx is None:
            continue

        task_id = getattr(ctx, "task_id", None)
        if task_id is None:
            continue  # sync-событие

        if task_id not in tasks:
            tasks[task_id] = TaskTrace(
                task_id=task_id,
                parent_task_id=ctx.task_parent_id,
                task_name=ctx.task_name,
                thread_id=ctx.thread_id,
            )
            tasks[task_id].first_event_index = index

        task = tasks[task_id]
        task.event_ids.append(index)
        task.last_context = ctx

    if not tasks:
        return tasks

    # -------------------------
    # B) Дерево вызовов внутри каждой таски
    # -------------------------
    call_task_by_id: dict[int, int] = {}
    for ev in events:
        if isinstance(ev, CallEvent) and ev.context is not None:
            tid = ev.context.task_id
            if tid is not None:
                call_task_by_id[ev.id] = tid

    for ev in events:
        if not isinstance(ev, CallEvent):
            continue
        if ev.kind != "call":
            continue
        if ev.context is None or ev.context.task_id is None:
            continue

        tid = ev.context.task_id
        current_task = tasks.get(tid)
        if current_task is None:
            continue

        parent_id = ev.parent_id
        if parent_id is None:
            current_task.roots.append(ev.id)
            continue

        parent_tid = call_task_by_id.get(parent_id)
        if parent_tid != tid:
            current_task.roots.append(ev.id)
            continue

        current_task.call_children.setdefault(parent_id, []).append(ev.id)

    # -------------------------
    # Служебное: глобальный стек call_id по индексу события,
    # чтобы знать активную функцию на момент await.
    # -------------------------
    global_call_stack: list[tuple[int, int | None]] = []
    active_call_by_index: dict[int, int] = {}

    for idx, ev in enumerate(events):
        ctx = getattr(ev, "context", None)
        tid = getattr(ctx, "task_id", None)

        if isinstance(ev, CallEvent) and ev.kind == "call":
            global_call_stack.append((ev.id, tid))
        elif isinstance(ev, CallEvent) and ev.kind == "return" and global_call_stack:
            global_call_stack.pop()

        if tid is not None:
            top_call_id = -1
            for cid, stack_tid in reversed(global_call_stack):
                if stack_tid == tid:
                    top_call_id = cid
                    break
            active_call_by_index[idx] = top_call_id

    # -------------------------
    # C) await↔resume по каждой таске (правильная модель CPython)
    #
    # Логика:
    # - первая await в серии открывает сегмент
    # - все последующие await до resume считаются внутренними и игнорируются
    # - первый resume закрывает сегмент
    # -------------------------
    transitions_by_task: dict[int, list[tuple[int, AsyncTransitionEvent]]] = defaultdict(list)

    for index, ev in enumerate(events):
        if ev.context is None or ev.context.task_id is None:
            continue
        tid = ev.context.task_id
        if isinstance(ev, AsyncTransitionEvent):
            transitions_by_task[tid].append((index, ev))

    for tid, task in tasks.items():
        transitions = transitions_by_task.get(tid, [])
        if not transitions:
            continue

        open_seg: AwaitSegment | None = None
        segs: list[AwaitSegment] = []

        for idx, tr in transitions:
            if tr.kind == "await":
                if open_seg is None:
                    call_id = active_call_by_index.get(idx, -1)
                    open_seg = AwaitSegment(
                        call_id=call_id,
                        await_event_id=idx,  # глобальный индекс события await
                        resume_event_id=None,
                        start_ts=None,
                        end_ts=None,
                        duration=None,
                        detail=getattr(tr, "detail", None),
                        children_task_ids=[],
                    )
                # внутренние await в этой же серии игнорируем
                continue

            if tr.kind == "resume":
                if open_seg is not None:
                    open_seg.resume_event_id = idx  # глобальный индекс resume
                    segs.append(open_seg)
                    open_seg = None
                continue

            # kind="yield" и прочие переходы в await-сегменты не входят
            continue

        # если серия await не закрылась resume (редко, но бывает)
        if open_seg is not None:
            segs.append(open_seg)

        # лёгкая нормализация detail (не выкидываем сегменты!)
        for seg in segs:
            if isinstance(seg.detail, str) and (
                seg.detail.startswith("<Future")
                or seg.detail.startswith("<Task")
                or seg.detail.startswith("<coroutine")
            ):
                seg.detail = None

        task.await_segments = segs

    # -------------------------
    # D) Привязываем дочерние таски к await-окнам
    # -------------------------
    for tid, task in tasks.items():
        child_tasks = [c for c in tasks.values() if c.parent_task_id == tid]

        for seg in task.await_segments:
            start_idx = seg.await_event_id
            end_idx = seg.resume_event_id or (len(events) - 1)

            for child in child_tasks:
                if child.first_event_index is None:
                    continue
                if start_idx <= child.first_event_index <= end_idx:
                    seg.children_task_ids.append(child.task_id)

            if seg.children_task_ids:
                seg.children_task_ids = list(dict.fromkeys(seg.children_task_ids))

    return tasks
