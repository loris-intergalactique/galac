from __future__ import absolute_import

"""
Parsing Utilities for Intergalactangled
"""

from galac.parsing.markdown import (
    MarkdownDocumentParser,
    MarkdownExtra,
    NowebBloodhound,
    ParsedEntanglementBlock,
)

from galac.parsing.entangled import (
    EntangledDocumentParser,
    EntangledNowebBloodhound,
)

from galac.parsing.binary import (
    BinaryDocumentParser,
)

from galac.parsing.parseable import (
    DocumentKind,
)

from galac.proto_gen.entanglement_pb2 import (
    Entanglement,
)

__all__ = [
    "DocumentKind",
    "DocumentParser",
    "MarkdownDocumentParser",
    "MarkdownExtra",
    "NowebBloodhound",
    "EntangledDocumentParser",
    "EntangledNowebBloodhound",
    "BinaryDocumentParser",
    "ParsedEntanglementBlock",
]

from pathlib import Path

class DocumentParser:
    """
    This parser will provide a filetype-agnostic parser that will use the
    appropriate parser for the filetype.
    """
    PARSERS = [
        MarkdownDocumentParser,
        BinaryDocumentParser,
        EntangledDocumentParser,
    ]

    def __init__(self, file: Path):
        self.file   = file
        self.parser = None
        for parser in self.PARSERS:
            if parser.is_compatible(self.file):
                self.parser = parser
                break

    def parse(self):
        return self.parser.parse(self.file)

    def render(self):
        return self.parser.render

    def get_blocks(self):
        return self.parser.get_blocks

    def get_entanglements(self):
        return self.parser.get_entanglements()

    def get_document_type(self):
        return self.parser.document_type

    def save(self, comment_chars=None):
        if not self.parser.parsed_document:
            return
        self.parser.render_to_file(self.file, comment_chars)

    def save_entanglement(self, target_file, comment_chars):
        if not self.parser.parsed_document:
            return
        self.parser.render_entanglement_to_file(self.file, comment_chars)

    def get_hash(self):
        return self.parser.get_hash()

