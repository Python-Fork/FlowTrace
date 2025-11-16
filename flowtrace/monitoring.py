from __future__ import annotations

import logging
import sys
import weakref
from collections.abc import Callable
from pathlib import Path

Cb = Callable[..., None]

# Запоминаем активные колбеки на tool_id
_ACTIVE_CALLBACKS: dict[int, dict[str, Cb]] = {}


def start_monitoring(tool_id: int) -> None:
    """
    Включает мониторинг для заданного tool_id и делегирует все события в dispatch.
    """
    events = sys.monitoring.events

    handlers = {
        "PY_START": make_handler("PY_START", _dispatch_event),
        "PY_RETURN": make_handler("PY_RETURN", _dispatch_event),
        "RAISE": make_handler("RAISE", _dispatch_event),
        "RERAISE": make_handler("RERAISE", _dispatch_event),
        "PY_UNWIND": make_handler("PY_UNWIND", _dispatch_event),
        "EXCEPTION_HANDLED": make_handler("EXCEPTION_HANDLED", _dispatch_event),
        "PY_RESUME": make_handler("PY_RESUME", _dispatch_event),
        "PY_YIELD": make_handler("PY_YIELD", _dispatch_event),
    }

    for name, cb in handlers.items():
        ev = getattr(events, name)
        sys.monitoring.register_callback(tool_id, ev, cb)

    sys.monitoring.set_events(
        tool_id,
        events.PY_START
        | events.PY_RETURN
        | events.RAISE
        | events.RERAISE
        | events.PY_UNWIND
        | events.EXCEPTION_HANDLED
        | events.PY_RESUME
        | events.PY_YIELD,
    )

    _ACTIVE_CALLBACKS[tool_id] = handlers


def stop_monitoring(tool_id: int) -> None:
    """
    Полностью выключает мониторинг для tool_id и снимает все колбеки.
    """
    events = sys.monitoring.events

    # отключаем генерацию событий
    sys.monitoring.set_events(tool_id, events.NO_EVENTS)

    handlers = _ACTIVE_CALLBACKS.pop(tool_id, None)

    # даже если по какой-то причине в _ACTIVE_CALLBACKS ничего нет —
    # подчистим callback'и на всякий
    names = (
        "PY_START",
        "PY_RETURN",
        "RAISE",
        "RERAISE",
        "PY_UNWIND",
        "EXCEPTION_HANDLED",
        "PY_RESUME",
        "PY_YIELD",
    )

    for name in names if handlers is None else handlers.keys():
        ev = getattr(events, name)
        sys.monitoring.register_callback(tool_id, ev, None)


def reserve_tool_id(name: str = "flowtrace") -> int:
    for tool_id in range(1, 6):
        current = sys.monitoring.get_tool(tool_id)
        if current is None:
            sys.monitoring.use_tool_id(tool_id, name)
            return tool_id
    raise RuntimeError(
        "[FlowTrace] Failed to register Monitoring API: "
        "all tool IDs are occupied. Close any active debuggers/profilers."
    )


def make_handler(event_label: str, dispatch):
    """Создаёт колбэк sys.monitoring → вызывает наш общий диспетчер."""

    def handler(*args):
        if not args:
            return
        code = args[0]
        try:
            dispatch(event_label, code, args)
        except Exception as e:
            logging.debug("[flowtrace-debug] handler error: %s", e)

    return handler


def _dispatch_event(label: str, code, raw_args):
    from flowtrace.session import CURRENT_SESSION

    sess = CURRENT_SESSION.get()
    if not (sess and sess.active):
        return
    sess.on_raw_event(label, code, raw_args)


def _norm(p: Path) -> str:
    # нормализуем и нижний регистр для кроссплатформенности
    return str(p).replace("\\", "/").lower()


# системные и собственные пути (для фильтрации traceback)
_HERE_STR = _norm(Path(__file__).resolve().parent)
_STD_PREFIXES_STR = tuple(_norm(p) for p in {Path(sys.prefix), Path(sys.base_prefix)} if p.exists())

# слабый кэш для фильтрации кода (ускоряет _is_user_code)
_IS_USER_CODE_CACHE: weakref.WeakKeyDictionary[object, bool] = weakref.WeakKeyDictionary()


def _is_user_code(code) -> bool:
    """Определяет, относится ли код к пользовательскому (а не stdlib/venv/самой FlowTrace)."""
    cached = _IS_USER_CODE_CACHE.get(code)
    if cached is not None:
        return cached
    try:
        p = Path(code.co_filename).resolve()
    except Exception:
        _IS_USER_CODE_CACHE[code] = False
        return False

    sp = _norm(p)

    # Разрешаем примеры внутри FlowTrace/examples
    if sp.startswith(_HERE_STR + "/examples"):
        _IS_USER_CODE_CACHE[code] = True
        return True

    # Скрываем саму либу
    if sp.startswith(_HERE_STR):
        _IS_USER_CODE_CACHE[code] = False
        return False

    # stdlib / venv / site-packages — тоже не показываем
    if any(sp.startswith(pref) for pref in _STD_PREFIXES_STR) or "site-packages/" in sp:
        _IS_USER_CODE_CACHE[code] = False
        return False

    _IS_USER_CODE_CACHE[code] = True
    return True


def _is_user_path(path: str) -> bool:
    """То же самое, но для обычного пути (строки)."""
    try:
        p = Path(path).resolve()
    except Exception:
        return False

    sp = _norm(p)

    if any(sp.startswith(pref) for pref in _STD_PREFIXES_STR) or "site-packages/" in sp:
        return False

    # не показываем саму FlowTrace
    return not sp.startswith(_HERE_STR)
