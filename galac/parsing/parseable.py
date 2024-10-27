from __future__ import annotations

"""
Parseable types of files.
"""

from enum import Enum

__all__ = [
    'DocumentKind',
]

class DocumentKind(Enum):
    Markdown  = 1
    Entangled = 2
    Binary    = 3

