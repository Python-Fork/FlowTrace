from __future__ import annotations
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, List, Optional

@dataclass
class CallEvent:
    kind: str
    func_name: str
    ts: float
    duration: Optional[float] = None
    # Позже добавим filename, lineno, args_repr, result_repr...

# todo
@dataclass
class TraceSession:
    active: bool = False
    events: List[CallEvent] = field(default_factory=list)
    _stack: List[float] = field(default_factory=list)

    def start(self) -> None:
        # Подключить sys.monitoring и зарегистрировать кэлбэки
        self.active = True

    def stop(self):
        # Отключить sys.monitoring, снять кэлбэки
        self.active = False
        return self.events

    def on_call(self, func_name: str) -> None:
        if not self.active:
            return
        self._stack.append(perf_counter())
        self.events.append(CallEvent(kind="call", func_name=func_name, ts=self._stack[-1]))

    def on_return(self, func_name: str) -> None:
        if not self.active:
            return
        start = self._stack.pop() if self._stack else None
        dur = perf_counter() - start
        self.events.append(CallEvent(kind="return", func_name=func_name, ts=perf_counter(), duration=dur))

# Глобальная текущая сессия. MVP: одна сессия на декоратор
_current: Optional[TraceSession] = None

def _current_session() -> Optional[TraceSession]:
    return _current

def start_tracing() -> None:
    global _current
    _current = TraceSession()
    _current.start()

def stop_tracing() -> List[CallEvent]:
    global _current
    if _current is None:
        return []
    data = _current.stop()
    _current = None
    return data

# todo
def get_trace_data() -> List[CallEvent]:
    # Доступ к последней завершенной сессии пока не храним
    # На MVP вызываем сразу после stop_tracing() и отдаём то, что он вернул
    raise RuntimeError(
        "На этапе MVP вызывать stop_tracing() из декоратора и работать с тем, что случилось."
        "get_trace_data реализуем позже"
    )
