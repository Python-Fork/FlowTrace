# flowtrace/formatters/async_tree.py

from __future__ import annotations

from flowtrace.events import AsyncTransitionEvent, CallEvent, TraceEvent


class _AsyncNode:
    """
    Узел дерева async-тасков.
    """

    __slots__ = ("children", "events", "parent_id", "task_id")

    def __init__(self, task_id: int, parent_id: int | None):
        self.task_id = task_id
        self.parent_id = parent_id
        self.events: list[TraceEvent] = []
        self.children: list[_AsyncNode] = []


def _build_async_tree(events: list[TraceEvent]) -> list[_AsyncNode]:
    """
    Строит дерево async-задач.
    Возвращает список корневых тасков.
    """
    by_id: dict[int, _AsyncNode] = {}

    for ev in events:
        ctx = ev.context
        if ctx is None:
            continue

        tid = ctx.task_id
        parent = ctx.task_parent_id

        if tid is None:
            continue

        if tid not in by_id:
            by_id[tid] = _AsyncNode(tid, parent)

        by_id[tid].events.append(ev)

    if not by_id:
        return []

    roots: list[_AsyncNode] = []

    for _tid, node in by_id.items():
        if node.parent_id is None:
            roots.append(node)
        else:
            pnode: _AsyncNode | None = by_id.get(node.parent_id)
            if pnode is not None:
                pnode.children.append(node)
            else:
                roots.append(node)

    return roots


def _print_node(node: _AsyncNode, indent: str = ""):
    """
    Печать одного узла async-задачи.
    """

    print(f"{indent}[A#{node.task_id}]")

    pad = indent + "    "

    for ev in node.events:
        if isinstance(ev, CallEvent):
            # вызов функции
            args = f"({ev.args_repr})" if ev.args_repr else "()"
            print(f"{pad}→ {ev.func_name}{args}")

        elif ev.kind == "return" and isinstance(ev, CallEvent):
            res = ev.result_repr if ev.result_repr is not None else ""
            if res != "":
                print(f"{pad}← {ev.func_name} → {res}")
            else:
                print(f"{pad}← {ev.func_name}")

        elif isinstance(ev, AsyncTransitionEvent):
            if ev.kind == "await":
                print(f"{pad}↯ await")
            elif ev.kind == "resume":
                print(f"{pad}⟳ resume")
            elif ev.kind == "yield":
                detail = f" → {ev.detail}" if ev.detail else ""
                print(f"{pad}yield{detail}")

    # Печатаем дочерние задачи
    for child in node.children:
        _print_node(child, pad)


def print_async_tree(events: list[TraceEvent]) -> None:
    by_id: dict[int, _AsyncNode] = {}
    roots: list[_AsyncNode] = []

    # построение деревьев
    for ev in events:
        ctx = ev.context
        if ctx is None or ctx.task_id is None:
            continue

        tid = ctx.task_id
        parent = ctx.task_parent_id

        node = by_id.get(tid)
        if not node:
            node = _AsyncNode(tid, parent)
            by_id[tid] = node

    # связываем parent → children
    for _tid, node in by_id.items():
        if node.parent_id is None:
            roots.append(node)
        else:
            pnode: _AsyncNode | None = by_id.get(node.parent_id)
            if pnode is not None:
                pnode.children.append(node)
            else:
                roots.append(node)
