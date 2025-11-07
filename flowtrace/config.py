from __future__ import annotations

from dataclasses import dataclass, replace

_DEFAULT_TB_DEPTH = 2

ShowExc = bool | int


@dataclass(slots=True)
class Config:
    show_args: bool = True
    show_result: bool = True
    show_timing: bool = True
    show_exc: ShowExc = False
    inline_return: bool = False

    def exc_enabled(self) -> bool:
        return bool(self.show_exc)

    def exc_depth(self) -> int:
        if isinstance(self.show_exc, bool):
            return _DEFAULT_TB_DEPTH if self.show_exc else 0
        if isinstance(self.show_exc, int):
            return max(0, self.show_exc)
        return 0


_CONFIG = Config()


def get_config() -> Config:
    return _CONFIG


def config(
    *,
    show_args: bool | None = None,
    show_result: bool | None = None,
    show_timing: bool | None = None,
    show_exc: bool | int | None = None,
    inline_return: bool | None = None,
    exc_tb_depth: int | None = None,
) -> Config:
    global _CONFIG

    if "exc_tb_depth" in locals() and exc_tb_depth is not None and show_exc is None:
        show_exc = int(exc_tb_depth)

    _CONFIG = replace(
        _CONFIG,
        **{k: v for k, v in locals().items() if hasattr(_CONFIG, k) and v is not None},
    )
    return _CONFIG
