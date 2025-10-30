> 🌐 English version: [README.md](README.md)
# 🌀 FlowTrace — трассировка исполнения для Python 3.12+

> FlowTrace — это системный трейссер, построенный на Monitoring API Python (PEP 669).
Он не измеряет время выполнения “по умолчанию” — вместо этого восстанавливает,
что именно произошло в программе: вызовы, возвраты, структуру —
с минимальными накладными расходами и без monkey-patching.

> Статус: экспериментальная альфа-версия. Требуется Python 3.12 и выше.
---
Установка
```
pip install flowtrace
```
---
## Быстрый старт
### 1) Один декоратор
```python
from flowtrace import trace

@trace
def fib(n):
    return n if n < 2 else fib(n-1) + fib(n-2)

fib(3)
```

Вывод:

```
→ fib(3)
  → fib(2)
    → fib(1) → 1
    → fib(0) → 0
  ← fib(2) → 1
  → fib(1) → 1
← fib(3) → 2
```
## 2) Время — когда нужно
```python
from flowtrace import trace

@trace(measure_time=True)
def compute(a, b):
    return a * b

compute(6, 7)
```

Вывод:

```
→ compute(6, 7) [0.000265s] → 42
```
---
## 3) Ручная сессия
```python
from flowtrace import start_tracing, stop_tracing, print_tree

def fib(n):
    return n if n < 2 else fib(n-1) + fib(n-2)

start_tracing()     # по умолчанию — без времени, только структура
fib(3)
events = stop_tracing()
print_tree(events)
```

Результат:

```
→ fib()
  → fib()
    → fib()  → 1
    → fib()  → 0
  ← fib()  → 1
  → fib()  → 1
← fib()  → 2
```
---
## Глобальные настройки
```python
import flowtrace
flowtrace.config(show_args=False, show_result=True, show_timing=True)
```
Управляют тем, какие данные собирать по умолчанию.

| Флаг          | Назначение                                  |
| ------------- | ------------------------------------------- |
| `show_args`   | собирать и отображать аргументы функций     |
| `show_result` | собирать и отображать возвращаемые значения |
| `show_timing` | измерять и отображать время выполнения      |

## Локальные переопределения
```python
@flowtrace.trace(show_args=True)
def foo(x): ...
```

Флаги, указанные в декораторе, действуют только для этой функции
и не влияют на дочерние вызовы.
Пример
```python
import flowtrace

flowtrace.config(show_args=False, show_result=True, show_timing=True)

@flowtrace.trace
def a(x): return b(x) + 1

@flowtrace.trace(show_args=True)
def b(y): return y * 2

a(10)
```
Вывод:
```
→ a() [0.000032s] → 21
  → b(y=10) [0.000010s] → 20
  ← b(y=10)
← a()
```
---
## Почему FlowTrace?

- **Это не профайлер**. Профайлер отвечает на «где сгорело время»,
FlowTrace отвечает на вопрос «что и в каком порядке произошло».

- **Прямая связь с виртуальной машиной**.
Слушает байткод-уровневые события через sys.monitoring (PEP 669).

- **Без вмешательства в код**.
Никакого sys.settrace, monkey-patchей и лишнего вывода в консоль.
---

## API (текущий)
```
from flowtrace import trace, config, start_tracing, stop_tracing, get_trace_data, print_tree
```

- ```@trace(measure_time: bool = True)```
Добавляет функцию в трассировку.
Если ```measure_time=True```, для вызовов этой функции записывается длительность.

- ```start_tracing() / stop_tracing() -> list[CallEvent]```
Запускает или останавливает трассировку процесса.
По умолчанию записывается только структура, без времени.

- ```get_trace_data() -> list[CallEvent]```
Возвращает список последних зафиксированных событий.

- ```print_tree(events)```
Печатает иерархическое дерево вызовов.

Модель события (```CallEvent```)
``` python
id: int
kind: str
func_name: str
parent_id: int | None
args_repr: str | None
result_repr: str | None
duration: float | None
collect_args: bool
collect_result: bool
collect_timing: bool
```
---

## Архитектурные принципы

- **Только ```PY_START``` / ```PY_RETURN```.**
События ```CALL``` не используются — ядро остаётся простым и быстрым.
Аргументы передаёт декоратор прямо перед стартом вызова.

- **Трассировка исключений.**
  FlowTrace отслеживает события исключений (`RAISE`, `RERAISE`, `EXCEPTION_HANDLED`, `PY_UNWIND`).
  Для каждой функции создаётся максимум одно событие исключения, отмеченное как
  `[caught]` (поймано локально) или `[propagated]` (вышло наружу).

- **Измерение времени — только по запросу.**
```perf_counter()``` вызывается лишь при ```measure_time=True```.
Простая сессия ```start```/```stop``` не создаёт временных накладных.

- **Фильтр пользовательского кода.**
Исключаются стандартная библиотека и пакеты из site-packages.

---
## Принципы реализации

- Нулевые накладные расходы при отключённых флагах. Аргументы, результаты и время не вычисляются, если флаги выключены.

- Человеческое отображение аргументов. Имена параметров показываются в виде a=5, b=2, вычисляются один раз при декорации.

- Без каскада настроек. Локальные флаги действуют только на текущую функцию.
---

## План развития

- **Поддержка async/await переходов.**

- **Экспорт трассы в JSON.**

- **Цветной вывод и фильтры include/exclude.**

- **Минимальный CLI-интерфейс.**

---
## Участие

PR приветствуются. Кодовая база специально компактна — это учебный и исследовательский инструмент, позволяющий изучать внутреннее устройство Python 3.12+ и его Monitoring API.