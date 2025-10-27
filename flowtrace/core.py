from __future__ import annotations

import os
import sys

from dataclasses import dataclass, field
from time import perf_counter, process_time_ns
from typing import Any, List, Optional
from pathlib import Path

@dataclass
class CallEvent:
    id: int
    kind: str
    func_name: str
    parent_id: Optional[int] = None
    args_repr: Optional[str] = None
    result_repr: Optional[str] = None
    duration: Optional[float] = None
    arg: Any = None


@dataclass
class TraceSession:
    active: bool = False
    events: List[CallEvent] = field(default_factory=list)

    _stack: List[tuple[str, float, int]] = field(default_factory=list)

    _cb_start: Optional[callable] = None
    _cb_return: Optional[callable] = None

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
            sys.monitoring.events.PY_START | sys.monitoring.events.PY_RETURN
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

    def on_call(self, func_name: str, args=None, kwargs = None) -> None:
        if not self.active:
            return

        start_time = perf_counter()
        parent_id = self._stack[-1][2] if self._stack else None

        try:
            args_repr = ", ".join(map(repr, args)) if args else ""
            if kwargs:
                kw_repr = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
                args_repr = f"{args_repr}, {kw_repr}" if args_repr else kw_repr
            if len(args_repr) > 60:
                args_repr = args_repr[:57] + "..."
        except Exception:
            args_repr = "<unrepr>"

        event_id = len(self.events)
        self._stack.append((func_name, start_time, event_id))
        self.events.append(CallEvent(id=event_id,
                                     kind="call",
                                     func_name=func_name,
                                     parent_id=parent_id,
                                     args_repr=args_repr
                                )
                           )

    def on_return(self, func_name: str, result: Any = None) -> None:
        if not self.active:
            return

        end = perf_counter()
        start = None
        event_id = None
        for i in range(len(self._stack) - 1, -1, -1):
            name, s, eid = self._stack.pop()
            if name == func_name:
                start = s
                event_id = eid
                break

        duration = end - start if start else None
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

_current: Optional[TraceSession] = None
_last_data: Optional[List[CallEvent]] = None
_PROJECT_ROOT = Path(os.getcwd()).resolve()
_STD_PREFIXES = {
    Path(sys.prefix).resolve(),
    Path(sys.base_prefix).resolve(),
}
TOOL_ID = _reserve_tool_id()

def _is_user_code(code) -> bool:
    try:
        path = Path(code.co_filename).resolve()
    except Exception:
        return False

    here = Path(__file__).resolve().parent
    if str(path).startswith(str(here / "examples")):
        return True

    if str(path).startswith(str(here)):
        return False

    for prefix in (sys.prefix, sys.base_prefix):
        if str(path).startswith(str(Path(prefix).resolve())):
            return False

    if "site-packages" in str(path):
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
        # raw_args обычно содержит result на позиции 3, но иногда — None
        result = raw_args[-1] if len(raw_args) >= 4 else None
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
            print("[flowtrace-debug] handler error:", e)
    return handler

def start_tracing() -> None:
    global _current
    sess = TraceSession()
    sess.start()
    _current = sess
    setattr(sys.monitoring, "_flowtrace_session", sess)

def is_tracing_active() -> bool:
    sess = getattr(sys.monitoring, "_flowtrace_session", None)
    return bool(sess and sess.active)

def stop_tracing() -> List[CallEvent]:
    global _current, _last_data
    sess = getattr(sys.monitoring, "_flowtrace_session", None)
    if not sess:
        return []
    data = sess.stop()
    _last_data = data
    _current = None
    setattr(sys.monitoring, "_flowtrace_session", None)
    return data

def get_trace_data() -> List[CallEvent]:
    return list(_last_data) if _last_data else []