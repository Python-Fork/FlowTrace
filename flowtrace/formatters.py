from __future__ import annotations
from typing import List
from .core import CallEvent, get_trace_data

def _format_event(event: CallEvent) -> str:
    if event.kind == "call":
        return f"    call    {event.func_name}"
    elif event.kind == "return":
        res = f" → {event.result_repr}" if event.result_repr is not None else ""
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


def print_tree(events: list, indent: int = 0, parent_id: int | None = None):
    indent_str = "  " * indent

    calls = [e for e in events if e.kind == "call" and e.parent_id == parent_id]

    for call in calls:
        children = [e for e in events if e.kind == "call" and e.parent_id == call.id]
        ret = next((r for r in events if r.kind == "return" and r.parent_id == call.id), None)

        args = f"({call.args_repr})" if call.args_repr else "()"
        dur = f"[{ret.duration:.6f}s]" if (ret and ret.duration) else ""
        result = f"→ {ret.result_repr}" if (ret and ret.result_repr) else ""

        if not children:
            print(f"{indent_str}→ {call.func_name}{args} {dur} {result}")
        else:
            # иначе — раскрываем полностью
            print(f"{indent_str}→ {call.func_name}{args}")
            print_tree(events, indent + 1, call.id)
            print(f"{indent_str}← {call.func_name}{args} {dur} {result}")
