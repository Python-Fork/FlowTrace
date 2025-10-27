from __future__ import annotations
from typing import List
from .core import CallEvent, get_trace_data

def _format_event(event: CallEvent) -> str:
    if event.kind == "call":
        return f"    call    {event.func_name}"
    elif event.kind == "return":
        res = f" → {event.arg!r}" if event.arg is not None else ""
        dur = f" ({event.duration:.6f}s)" if event.duration is not None else ""
        return f"    return  {event.func_name}{res}{dur}"
    return f"    {event.kind:7} {event.func_name}"

def print_events_debug(events: List[CallEvent] | None = None) -> None:
    """Печатает отладочный список событий FlowTrace.

    Если events не передан, выводятся данные последней трассировки
    через get_trace_data().
    """
    if events is None:
        events = get_trace_data()

    if not events:
        print("[flowtrace] (нет событий — подключите Monitoring API)")
        return

    print("[flowtrace] события:")
    for event in events:
        print(_format_event(event))

def print_summary(events: List[CallEvent] | None = None) -> None:
    """Выводит краткую сводку (кол-во вызовов, время, последняя функция)."""
    if events is None:
        events = get_trace_data()

    if not events:
        print("[flowtrace] (пустая трасса)")
        return

    total = len(events)
    duration = sum((e.duration or 0.0) for e in events)
    last_func = events[-1].func_name if events else "—"
    print(f"[flowtrace] {total} событий, {duration:.6f}s, последняя функция: {last_func}")

def print_tree(events: list[CallEvent]):
    children = {e.id: [] for e in events}
    roots = []
    for e in events:
        if e.parent_id is not None and e.parent_id in children:
            children[e.parent_id].append(e)
        else:
            roots.append(e)

    def walk(node, prefix=""):
        arg_info = f"({node.args_repr})" if node.args_repr else "()"
        dur_info = f" [{node.duration:.6f}s]" if node.duration else ""
        print(f"{prefix}→ {node.func_name}{arg_info}{dur_info}")
        for child in children[node.id]:
            walk(child, prefix + "  ")

    for root in roots:
        walk(root)