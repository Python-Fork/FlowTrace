from __future__ import annotations
from typing import List
from .core import CallEvent

def print_events_debug(events: List[CallEvent]) -> None:
    # MVP: показываем сколько событий и какие типы.
    # Позже сделаем вывод дерева
    if not events:
        print("[flowtrace] (нет событий - дальше подключим мониторинг)")
    else:
        print("[flowtrace] события:")
        for event in events:
            if event.duration is None:
                print(f"    {event.kind:7} {event.func_name}")
            else:
                print(f"    {event.kind:7} {event.func_name} {event.duration:.6f}s")
