from typing import Any

__all__ = ["print_window"]

print_window: Any

def __getattr__(name: str) -> Any: ...
