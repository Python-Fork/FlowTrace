from importlib.metadata import version as _pkg_version

from .config import config
from .core import get_trace_data, start_tracing, stop_tracing
from .decorators import trace
from .formatters import print_tree

__all__ = ["config", "get_trace_data", "print_tree", "start_tracing", "stop_tracing", "trace"]
__version__ = _pkg_version("flowtrace")
