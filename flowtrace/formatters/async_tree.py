from __future__ import annotations

from ..async_model import AwaitSegment, TaskTrace
from ..events import CallEvent, TraceEvent


def print_async_tree(tasks: dict[int, TaskTrace], events: list[TraceEvent]) -> None:
    ordered_tasks = sorted(tasks.values(), key=lambda t: t.first_event_index or 10**9)
    for task in ordered_tasks:
        print_task_tree(task, tasks, events)
        print()


def print_task_tree(task: TaskTrace, tasks: dict[int, TaskTrace], events: list[TraceEvent]) -> None:
    header = f"Task#{task.task_id}"
    if task.task_name:
        header += f" {task.task_name}"
    if task.parent_task_id is not None:
        header += f" (parent={task.parent_task_id})"

    print(header)

    for root_id in task.roots:
        print_call_subtree(root_id, task, tasks, events, indent="  ")


def print_call_subtree(
    call_id: int,
    task: TaskTrace,
    tasks: dict[int, TaskTrace],
    events: list[TraceEvent],
    indent: str,
) -> None:
    ev = _find_call(call_id, events)
    if ev is None:
        return

    print(f"{indent}→ {ev.func_name}()")

    for seg in task.await_segments:
        if seg.call_id == call_id:
            print_await_segment(seg, task, tasks, events, indent + "  ")

    # --- печать детей функций ---
    for child_id in task.call_children.get(call_id, []):
        print_call_subtree(child_id, task, tasks, events, indent + "  ")

    ret = _find_return(call_id, events)
    if ret is not None and ret.result_repr is not None:
        print(f"{indent}← {ev.func_name}() → {ret.result_repr}")
    else:
        print(f"{indent}← {ev.func_name}()")


def print_await_segment(
    seg: AwaitSegment,
    task: TaskTrace,
    tasks: dict[int, TaskTrace],
    events: list[TraceEvent],
    indent: str,
) -> None:
    detail = "await"
    dur = ""

    if seg.duration is not None:
        dur = f" [{seg.duration * 1000:.2f} ms]"

    print(f"{indent}↯ {detail}{dur}")

    # --- дети внутри await ---
    for child_tid in seg.children_task_ids:
        child = tasks.get(child_tid)
        if child is None:
            continue
        print(f"{indent}  Task#{child_tid}")
        for root in child.roots:
            print_call_subtree(root, child, tasks, events, indent + "    ")


def _find_call(call_id: int, events: list[TraceEvent]) -> CallEvent | None:
    for ev in events:
        if isinstance(ev, CallEvent) and ev.id == call_id:
            return ev
    return None


def _find_return(call_id: int, events: list[TraceEvent]) -> CallEvent | None:
    for ev in events:
        if isinstance(ev, CallEvent) and ev.kind == "return" and ev.parent_id == call_id:
            return ev
    return None
