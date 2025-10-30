from __future__ import annotations
from typing import List
from .core import CallEvent, get_trace_data

def _format_event(event: CallEvent) -> str:
    if event.kind == "call":
        bits = ["call", event.func_name]
        if event.args_repr is not None:
            bits.append(f"({event.args_repr})")
        return "    " + " ".join(bits)
    elif event.kind == "return":
        bits = ["return", event.func_name]
        if event.result_repr is not None:
            bits.append(f"→ {event.result_repr}")
        if event.duration is not None:
            bits.append(f"({event.duration:.6f}s)")
        return "    " + " ".join(bits)
    elif event.kind == "exception":
        tag = "caught" if event.caught is True else ("propagated" if event.caught is False else "raised")
        msg = event.exc_msg or ""
        if len(msg) > 200:
            msg = msg[:197] + "..."
        return f"    exception {event.func_name} {event.exc_type}: {msg} [{tag}]"
    return f"    {event.kind:7} {event.func_name}"

def print_events_debug(events: List[CallEvent] | None = None) -> None:
    if events is None:
        events = get_trace_data()
    if not events:
        print("[flowtrace] (нет событий — подключите Monitoring API)")
        return
    print("[flowtrace] события:")
    for event in events:
        print(_format_event(event))

def print_summary(events: List[CallEvent] | None = None) -> None:
    if events is None:
        events = get_trace_data()
    if not events:
        print("[flowtrace] (пустая трасса)")
        return
    total = len(events)
    duration = sum((e.duration or 0.0) for e in events)
    last_func = events[-1].func_name if events else "—"
    print(f"[flowtrace] {total} событий, {duration:.6f}s, последняя функция: {last_func}")


def print_tree(events: list | None = None, indent: int = 0, parent_id: int | None = None):
    if events is None:
        events = get_trace_data()

    indent_str = "  " * indent
    calls = [e for e in events if e.kind == "call" and e.parent_id == parent_id]

    for call in calls:
        children = [e for e in events if e.kind == "call" and e.parent_id == call.id]
        excs = [e for e in events if e.kind == "exception" and e.parent_id == call.id]
        ret = next((r for r in events if r.kind == "return" and r.parent_id == call.id), None)

        # собираем строку аккуратно, без лишних пробелов
        head = [f"{indent_str}→ {call.func_name}"]
        if call.args_repr is not None:
            head[-1] += f"({call.args_repr})"
        else:
            head[-1] += "()"

        tail_parts: list[str] = []
        if ret and ret.duration is not None:
            tail_parts.append(f"[{ret.duration:.6f}s]")
        if ret and ret.result_repr is not None:
            tail_parts.append(f"→ {ret.result_repr}")

        print(head[0])
        if children:
            print_tree(events, indent + 1, call.id)
        if excs:
            exc_indent = "  " * (indent + 1)
            for ex in excs:
                tag = " [caught]" if ex.caught is True else (" [propagated]" if ex.caught is False else "")
                msg = ex.exc_msg or ""
                if len(msg) > 200:
                    msg = msg[:197] + "..."
                if call.args_repr is not None:
                    sig = f"{call.func_name}({call.args_repr})"
                else:
                    sig = f"{call.func_name}()"
                print(f"{exc_indent}↯ {sig} {ex.exc_type}: {msg}{tag}")
        end = [f"{indent_str}← {call.func_name}"]
        if call.args_repr is not None:
            end[-1] += f"({call.args_repr})"
        else:
            end[-1] += "()"
        end_line = " ".join([end[0]] + tail_parts) if tail_parts else end[0]
        print(end_line)