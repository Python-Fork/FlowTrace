from __future__ import annotations

from flowtrace.config import get_config
from flowtrace.core import get_trace_data
from flowtrace.events import (
    AsyncTransitionEvent,
    CallEvent,
    ExceptionEvent,
    TraceEvent,
)

_MAX_MSG = 200


def _sig(func_name: str, args_repr: str | None) -> str:
    return f"{func_name}({args_repr})" if args_repr else f"{func_name}()"


def _trim(s: str | None, n: int = _MAX_MSG) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[: n - 3] + "..."


def _format_event(event: TraceEvent) -> str:
    # ---- CallEvent ----
    if isinstance(event, CallEvent):
        if event.kind == "call":
            bits = ["call", event.func_name]
            if event.args_repr is not None:
                bits.append(f"({event.args_repr})")
            return "    " + " ".join(bits)

        if event.kind == "return":
            bits = ["return", event.func_name]
            if event.result_repr is not None:
                bits.append(f"→ {event.result_repr}")
            if event.duration is not None:
                bits.append(f"({event.duration:.6f}s)")
            return "    " + " ".join(bits)

    # ---- ExceptionEvent ----
    if isinstance(event, ExceptionEvent):
        tag = (
            "caught"
            if event.caught is True
            else ("propagated" if event.caught is False else "raised")
        )
        msg = _trim(event.exc_msg)
        return f"    exception {event.func_name} {event.exc_type}: {msg} [{tag}]"

    # ---- AsyncTransitionEvent ----
    if isinstance(event, AsyncTransitionEvent):
        detail = f" {event.detail}" if event.detail else ""
        return f"    {event.kind:7} {event.func_name}{detail}"

    # ---- fallback ----
    return f"    {event.kind:7} {event.func_name}"


def print_events_debug(events: list[TraceEvent] | None = None) -> None:
    if events is None:
        events = get_trace_data()

    if not events:
        print("[flowtrace] (нет событий — подключите Monitoring API)")
        return

    print("[flowtrace] события:")
    for ev in events:
        print(_format_event(ev))

    # async-tree только если есть task_id
    if any(ev.context and ev.context.task_id is not None for ev in events):
        print()
        from flowtrace.formatters.async_tree import print_async_tree

        print_async_tree(events)


def print_summary(events: list[TraceEvent] | None = None) -> None:
    if events is None:
        events = get_trace_data()

    if not events:
        print("[flowtrace] (пустая трасса)")
        return

    # учитывать duration можно только у CallEvent(return)
    total = len(events)
    duration = sum(
        (e.duration or 0.0) for e in events if isinstance(e, CallEvent) and e.duration is not None
    )

    # последняя функция — логично брать из последнего CallEvent или ExceptionEvent
    last = next(
        (e.func_name for e in reversed(events) if isinstance(e, (CallEvent, ExceptionEvent))), "—"
    )

    print(f"[flowtrace] {total} событий, {duration:.6f}s, последняя функция: {last}")


def print_tree(
    events: list[TraceEvent] | None = None,
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

    # берем только CallEvent с нужным parent_id
    calls = [
        e
        for e in events
        if isinstance(e, CallEvent) and e.kind == "call" and e.parent_id == parent_id
    ]

    for call in calls:
        # дети = CallEvent
        children = [
            e
            for e in events
            if isinstance(e, CallEvent) and e.kind == "call" and e.parent_id == call.id
        ]

        # исключения = ExceptionEvent
        excs = [e for e in events if isinstance(e, ExceptionEvent) and e.parent_id == call.id]

        # return = CallEvent(kind="return")
        ret = next(
            (
                r
                for r in events
                if isinstance(r, CallEvent) and r.kind == "return" and r.parent_id == call.id
            ),
            None,
        )

        # условие однострочного листа
        is_leaf_normal = (
            inline and not children and not excs and ret is not None and not ret.via_exception
        )

        if is_leaf_normal:
            line = f"{indent_str}→ {_sig(call.func_name, call.args_repr)}"

            if ret is not None and ret.duration is not None:
                line += f" [{ret.duration:.6f}s]"

            if ret is not None and ret.result_repr is not None:
                line += f" → {ret.result_repr}"

            print(line)
            continue

        # многострочный вывод
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
                msg = _trim(ex.exc_msg)
                print(
                    f"{exc_indent}↯ {_sig(call.func_name, call.args_repr)} {ex.exc_type}: {msg}{tag}"
                )
                if ex.exc_tb:
                    print(f"{exc_indent}   ⤷ {ex.exc_tb}")

        # хвостовая стрелка
        end_arrow = "↯" if (ret and ret.via_exception) else "←"
        end_line = f"{indent_str}{end_arrow} {_sig(call.func_name, call.args_repr)}"

        if ret and ret.duration is not None:
            end_line += f" [{ret.duration:.6f}s]"
        if ret and not ret.via_exception and ret.result_repr is not None:
            end_line += f" → {ret.result_repr}"
        if ret and ret.via_exception:
            end_line += " [exc-return]"

        print(end_line)
