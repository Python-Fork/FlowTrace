from __future__ import annotations

import os
import sys

from dataclasses import dataclass, field
from time import perf_counter, process_time_ns
from typing import Any, List, Optional
from pathlib import Path

@dataclass
class CallEvent:
    kind: str
    func_name: str
    ts: float
    duration: Optional[float] = None
    arg: Any = None
    # Позже добавим filename, lineno, args_repr, result_repr...

@dataclass
class TraceSession:
    active: bool = False
    events: List[CallEvent] = field(default_factory=list)

    _stack: List[tuple[str, float]] = field(default_factory=list)

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

    def on_call(self, func_name: str) -> None:
        if not self.active:
            return
        start_time = perf_counter()
        self._stack.append((func_name, start_time))
        self.events.append(CallEvent(kind="call", func_name=func_name, ts=start_time))

    def on_return(self, func_name: str, result: Any = None) -> None:
        if not self.active:
            return
        end = perf_counter()
        start = None
        if self._stack:
            # снимаем только совпадающую функцию (безопасно при рекурсии)
            while self._stack:
                name, s = self._stack.pop()
                if name == func_name:
                    start = s
                    break
        duration = end - start if start else None
        self.events.append(CallEvent(kind="return", func_name=func_name, ts=end, duration=duration, arg=result))

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

# Глобальная текущая сессия. MVP: одна сессия на декоратор
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