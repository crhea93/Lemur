from typing import Any

__all__ = ["xsapec", "xsbremss", "xsphabs"]

xsapec: Any
xsbremss: Any
xsphabs: Any

def __getattr__(name: str) -> Any: ...
