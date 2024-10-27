
"""
Diff Models
"""

__all__ = [
    "DiffedObjectType",
    "DiffedLineType",
    "DiffedCodeBlockType",
    "DiffedFileType",
    "DiffedEntanglement",
    "DiffedEntanglementBlockType",
    "DiffedEntanglementBlock",
    "DiffedCodeBlock",
    "DiffedFile",
    "DiffedLine",
    "Diff"
]

from enum import Enum
from subprocess import call 
from dataclasses import dataclass

import difflib

from galac.parsing import ParsedEntanglementBlock

class DiffedObjectType(Enum):
    Modified   = "modified"
    Created    = "created"
    Deleted    = "deleted"
    Unchanged  = "unchanged"
    Inexistent = "inexistent"

class DiffedLineType(Enum):
    Equal  = "equal"
    Insert = "insert"
    Delete = "delete"
    
DiffedCodeBlockType         = DiffedObjectType
DiffedFileType              = DiffedObjectType
DiffedEntanglement          = DiffedObjectType
DiffedEntanglementBlockType = DiffedObjectType

@dataclass
class DiffedEntanglementBlock:
    parsed_entanglement: ParsedEntanglementBlock
    status: DiffedEntanglementBlockType
    #diff: list[DiffedCodeBlock]

@dataclass
class DiffedCodeBlock:
    code: str
    status: DiffedCodeBlockType
    #diff: list[DiffedLine]

@dataclass
class DiffedFile:
    filename: str
    status: DiffedFileType
    #diff: list[DiffedLine]

@dataclass
class DiffedLine:
    line: str
    status: DiffedLineType
