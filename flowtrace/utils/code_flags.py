import inspect


def is_async_gen_code(code) -> bool:
    """True, если это async-генератор (async def + yield)."""
    try:
        return bool(code.co_flags & inspect.CO_ASYNC_GENERATOR)
    except Exception:
        return False


def is_coroutine_code(code) -> bool:
    """True, если это "чистая" корутина (async def без async-yield)."""
    try:
        flags = code.co_flags
        return bool(flags & inspect.CO_COROUTINE) and not bool(flags & inspect.CO_ASYNC_GENERATOR)
    except Exception:
        return False
