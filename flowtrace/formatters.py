from __future__ import annotations

from .config import get_config
from .core import CallEvent, get_trace_data

_MAX_MSG = 200


def _sig(func_name: str, args_repr: str | None) -> str:
    return f"{func_name}({args_repr})" if args_repr is not None else f"{func_name}()"


def _trim(s: str, n: int = _MAX_MSG) -> str:
    if s is None:
        return ""
    if len(s) <= n:
        return s
    return s[: max(0, n - 3)] + "..."


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
        tag = (
            "caught"
            if event.caught is True
            else ("propagated" if event.caught is False else "raised")
        )
        msg = event.exc_msg or ""
        if len(msg) > 200:
            msg = msg[:197] + "..."
        return f"    exception {event.func_name} {event.exc_type}: {msg} [{tag}]"
    return f"    {event.kind:7} {event.func_name}"


def print_events_debug(events: list[CallEvent] | None = None) -> None:
    if events is None:
        events = get_trace_data()
    if not events:
        print("[flowtrace] (нет событий — подключите Monitoring API)")
        return
    print("[flowtrace] события:")
    for event in events:
        print(_format_event(event))


def print_summary(events: list[CallEvent] | None = None) -> None:
    if events is None:
        events = get_trace_data()
    if not events:
        print("[flowtrace] (пустая трасса)")
        return
    total = len(events)
    duration = sum((e.duration or 0.0) for e in events)
    last_func = events[-1].func_name if events else "—"
    print(f"[flowtrace] {total} событий, {duration:.6f}s, последняя функция: {last_func}")


def print_tree(
    events: list[CallEvent] | None = None,
    indent: int = 0,
    parent_id: int | None = None,
    inline_return: bool | None = None,
) -> None:
    if events is None:
        events = get_trace_data()
    if not events:
        print("[flowtrace] (пустая трасса)")
        return

    cfg = get_config()
    inline = cfg.inline_return if inline_return is None else inline_return
    indent_str = "  " * indent

    calls = [e for e in events if e.kind == "call" and e.parent_id == parent_id]

    for call in calls:
        # Дети и связанные события
        children = [e for e in events if e.kind == "call" and e.parent_id == call.id]
        excs = [e for e in events if e.kind == "exception" and e.parent_id == call.id]
        ret = next((r for r in events if r.kind == "return" and r.parent_id == call.id), None)

        # Условия «листового» однострочного вывода:
        # - нет дочерних вызовов
        # - нет исключений
        # - есть нормальный return (не via_exception)
        is_leaf_normal = inline and not children and not excs and ret and not ret.via_exception

        if is_leaf_normal:
            line = f"{indent_str}→ {_sig(call.func_name, call.args_repr)}"
            if ret and ret.duration is not None:
                line += f" [{ret.duration:.6f}s]"
            if ret and ret.result_repr is not None:
                line += f" → {ret.result_repr}"
            print(line)
            continue  # однострочный узел уже выведен

        # Многострочный стиль (как раньше)
        print(f"{indent_str}→ {_sig(call.func_name, call.args_repr)}")

        if children:
            print_tree(events, indent + 1, call.id, inline_return=inline)

        if excs:
            exc_indent = "  " * (indent + 1)
            for ex in excs:
                tag = (
                    " [caught]"
                    if ex.caught is True
                    else (" [propagated]" if ex.caught is False else "")
                )
                msg = _trim(ex.exc_msg or "")
                print(
                    f"{exc_indent}↯ {_sig(call.func_name, call.args_repr)} {ex.exc_type}: {msg}{tag}"
                )
                if ex.exc_tb:
                    print(f"{exc_indent}   ⤷ {ex.exc_tb}")

        end_arrow = "↯" if (ret and ret.via_exception) else "←"
        end_line = f"{indent_str}{end_arrow} {_sig(call.func_name, call.args_repr)}"

        if ret and ret.duration is not None:
            end_line += f" [{ret.duration:.6f}s]"
        if ret and not ret.via_exception and ret.result_repr is not None:
            end_line += f" → {ret.result_repr}"
        if ret and ret.via_exception:
            end_line += " [exc-return]"

        print(end_line)
