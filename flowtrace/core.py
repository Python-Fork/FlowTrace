from __future__ import annotations

import logging
import sys

from dataclasses import dataclass
from time import perf_counter
from typing import Any, List, Optional
from pathlib import Path
from collections import defaultdict

from flowtrace.config import get_config


@dataclass
class CallEvent:
    id: int
    kind: str
    func_name: str
    parent_id: Optional[int] = None

    # payload (заполняются строго по флагам)
    args_repr: Optional[str] = None
    result_repr: Optional[str] = None
    duration: Optional[float] = None

    # флаги того, что ДОЛЖНО было собираться для этого вызова
    collect_args: bool = False
    collect_result: bool = False
    collect_timing: bool = False


class TraceSession:
    def __init__(
        self,
        default_collect_args: bool = True,
        default_collect_result: bool = True,
        default_collect_timing: bool = True,
    ):
        self.active: bool = False

        self.default_collect_args = default_collect_args
        self.default_collect_result = default_collect_result
        self.default_collect_timing = default_collect_timing

        self.events: list[CallEvent] = []
        self.stack: list[tuple[str, float, int]] = []

        # очередь метаданных от декоратора для КОНКРЕТНОГО следующего вызова функции
        # func_name -> list of (args_repr, collect_args, collect_result, collect_timing)
        self.pending_meta: dict[Any, list[tuple[str | None, bool, bool, bool]]] = defaultdict(list)

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

        collect_args = self.default_collect_args
        collect_result = self.default_collect_result
        collect_timing = self.default_collect_timing
        args_repr: str | None = None

        q = self.pending_meta.get(func_name)
        if q:
            # данные только для ЭТОГО вызова; на детей не «протекают»
            args_repr, collect_args, collect_result, collect_timing = q.pop(0)
            if not q:
                self.pending_meta.pop(func_name, None)

        start_time = perf_counter() if collect_timing else 0.0

        event_id = len(self.events)
        self.stack.append((func_name, start_time, event_id))
        self.events.append(
            CallEvent(
                id=event_id,
                kind="call",
                func_name=func_name,
                parent_id=parent_id,
                args_repr=args_repr if collect_args else None,
                collect_args=collect_args,
                collect_result=collect_result,
                collect_timing=collect_timing,
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
        call_ev = self.events[event_id]
        collect_timing = call_ev.collect_timing
        collect_result = call_ev.collect_result

        del self.stack[frame_index:]

        end = perf_counter() if collect_timing else None
        duration = (end - start) if (start and collect_timing) else None

        result_repr: str | None = None
        if collect_result:
            try:
                r = repr(result)
                if len(r) > 60:
                    r = r[:57] + "..."
                result_repr = r
            except Exception:
                result_repr = "<unrepr>"

        self.events.append(
            CallEvent(
                id=len(self.events),
                kind="return",
                func_name=func_name,
                parent_id=event_id,
                result_repr=result_repr,
                duration=duration,
            )
        )

    def push_meta_for_func(
        self,
        func_name: str,
        *,
        args_repr: str | None,
        collect_args: bool,
        collect_result: bool,
        collect_timing: bool,
    ):
        """Кладём готовые метаданные ДЛЯ СЛЕДУЮЩЕГО вызова данной функции."""
        if not self.active:
            return
        self.pending_meta[func_name].append((args_repr, collect_args, collect_result, collect_timing))


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
        if not _is_user_code(code):
            return
        try:
            _on_event(event_label, code, args)
        except Exception as e:
            logging.debug("[flowtrace-debug] handler error:", e)

    return handler



def start_tracing(
    default_show_args: bool | None = None,
    default_show_result: bool | None = None,
    default_show_timing: bool | None = None,
) -> None:
    cfg = get_config()

    sess = TraceSession(
        default_collect_args=cfg["show_args"] if default_show_args is None else default_show_args,
        default_collect_result=cfg["show_result"] if default_show_result is None else default_show_result,
        default_collect_timing = cfg["show_timing"] if default_show_timing is None else default_show_timing
    )
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
