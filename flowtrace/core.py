from __future__ import annotations

import logging
import sys

from dataclasses import dataclass
from time import perf_counter
from typing import Any, List, Optional
from pathlib import Path
from collections import defaultdict


@dataclass
class CallEvent:
    id: int
    kind: str
    func_name: str
    parent_id: Optional[int] = None
    args_repr: Optional[str] = None
    result_repr: Optional[str] = None
    duration: Optional[float] = None
    measure_time: bool = False


@dataclass
class TraceSession:
    def __init__(self, default_measure_time: bool = False):
        self.active: bool = False
        self.default_measure_time = default_measure_time
        self.events: list[CallEvent] = []
        self.stack: list[tuple[str, float, int]] = []

        self.pending_args: dict[Any, list[tuple[str, bool]]] = defaultdict(list)

        self._cb_start: Optional[callable] = None
        self._cb_return: Optional[callable] = None

    def start(self) -> None:
        if self.active:
            return
        self.active = True

        self._cb_start = _make_handler("PY_START")
        self._cb_return = _make_handler("PY_RETURN")

        sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.PY_START, self._cb_start)
        sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.PY_RETURN, self._cb_return)

        sys.monitoring.set_events(
            TOOL_ID,
            sys.monitoring.events.PY_START |
            sys.monitoring.events.PY_RETURN
        )

    def stop(self) -> list[CallEvent]:
        if not self.active:
            return self.events

        self.active = False

        current = sys.monitoring.get_events(TOOL_ID)
        if current != sys.monitoring.events.NO_EVENTS:
            sys.monitoring.set_events(TOOL_ID, sys.monitoring.events.NO_EVENTS)

        if getattr(self, "_cb_start", None):
            sys.monitoring.register_callback(
                TOOL_ID, sys.monitoring.events.PY_START, None
            )
            self._cb_start = None

        if getattr(self, "_cb_return", None):
            sys.monitoring.register_callback(
                TOOL_ID, sys.monitoring.events.PY_RETURN, None
            )
            self._cb_return = None

        return self.events

    def on_call(self, func_name: str) -> None:
        if not self.active:
            return

        parent_id = self.stack[-1][2] if self.stack else None

        arg_info = ""
        measure_time = self.default_measure_time
        q = self.pending_args.get(func_name)
        if q:
            arg_info, measure_time = q.pop(0)
            if not q:
                self.pending_args.pop(func_name, None)

        start_time = perf_counter() if measure_time else 0.0

        event_id = len(self.events)
        self.stack.append((func_name, start_time, event_id))
        self.events.append(CallEvent(id=event_id,
                                     kind="call",
                                     func_name=func_name,
                                     parent_id=parent_id,
                                     args_repr=arg_info,
                                     measure_time=measure_time,
                                     )
                           )

    def on_return(self, func_name: str, result: Any = None) -> None:
        if not self.active:
            return

        frame_index = None
        for i in range(len(self.stack) - 1, -1, -1):
            name, _, _ = self.stack[i]
            if name == func_name:
                frame_index = i
                break
        if frame_index is None:
            return

        name, start, event_id = self.stack[frame_index]
        measure_time = self.events[event_id].measure_time
        del self.stack[frame_index:]

        end = perf_counter() if measure_time else None
        duration = (end - start) if (start and measure_time) else None

        result_repr = repr(result)
        if len(result_repr) > 60:
            result_repr = result_repr[:57] + "..."

        self.events.append(CallEvent(id=len(self.events),
                                     kind="return",
                                     func_name=func_name,
                                     parent_id=event_id,
                                     result_repr=result_repr,
                                     duration=duration
                                     )
                           )

    def push_args_for_code(self, func_name, args, kwargs, measure_time: bool = True):
        """Кладёт форматированные аргументы(от декоратора в очередь для данного code(объекта).
        Забираются при ближайшем PY_START этой функции (в порядке вызовов)."""
        if not self.active:
            return
        try:
            parts = []
            if args:
                parts.extend(repr(arg) for arg in args)
            if kwargs:
                parts.extend(f"{k}={v!r}" for k, v in kwargs.items())

            args_repr = ", ".join(parts)

            if len(args_repr) > 200:
                args_repr = args_repr[:197] + "..."
        except Exception:
            args_repr = "<unrepr>"
        self.pending_args[func_name].append((args_repr, measure_time))


def _reserve_tool_id(name: str = "flowtrace") -> int:
    for tool_id in range(1, 6):
        current = sys.monitoring.get_tool(tool_id)
        if current is None:
            sys.monitoring.use_tool_id(tool_id, name)
            return tool_id

    raise RuntimeError(
        "[FlowTrace] Failed to register Monitoring API: "
        "all tool IDs are occupied. "
        "Close any active debuggers or profilers and try again"
    )


_last_data: Optional[List[CallEvent]] = None
TOOL_ID = _reserve_tool_id()


def _is_user_code(code) -> bool:
    try:
        path = Path(code.co_filename).resolve()
    except Exception:
        return False

    str_path = str(path)
    here = Path(__file__).resolve().parent

    if str_path.startswith(str(here / "examples")):
        return True

    if str_path.startswith(str(here)):
        return False

    for prefix in (sys.prefix, sys.base_prefix):
        if str_path.startswith(str(Path(prefix).resolve())):
            return False

    if "site-packages" in str_path:
        return False

    return True


def _on_event(label: str, code, raw_args):
    sess = getattr(sys.monitoring, "_flowtrace_session", None)
    if not (sess and sess.active):
        return

    func = code.co_name

    if label == "PY_START":
        sess.on_call(func)
    elif label == "PY_RETURN":
        result = raw_args[-1]
        sess.on_return(func, result)


def _make_handler(event_label: str):
    def handler(*args):
        if not args:
            return
        code = args[0]
        if not _is_user_code(code):  # фильтр снова активен
            return
        try:
            _on_event(event_label, code, args)
        except Exception as e:
            logging.debug("[flowtrace-debug] handler error:", e)

    return handler


def start_tracing(default_measure_time: bool = False) -> None:
    sess = TraceSession(default_measure_time=default_measure_time)
    sess.start()
    setattr(sys.monitoring, "_flowtrace_session", sess)


def is_tracing_active() -> bool:
    sess = getattr(sys.monitoring, "_flowtrace_session", None)
    return bool(sess and sess.active)


def stop_tracing() -> List[CallEvent]:
    global  _last_data
    sess = getattr(sys.monitoring, "_flowtrace_session", None)
    if not sess:
        return []
    data = sess.stop()
    _last_data = data
    setattr(sys.monitoring, "_flowtrace_session", None)
    return data


def get_trace_data() -> List[CallEvent]:
    return list(_last_data) if _last_data else []
