from __future__ import annotations

"""
Binary Parsing
"""

__all__ = [
    "BinaryDocumentParser",
]

class BinaryDocumentParser:
    FORMATS = [
        ".pdf",
        ".bin",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".exe",
        ".zip",
        ".tar",
        ".dll",
        ".so",
        ".dylib",
        ".a",
        ".o",
        ".obj",
        ".lib",
    ]

    def __init__(self, document, parsed_document):
        self.document = document
        self.parsed_document = parsed_document
        self.document_type = DocumentKind.Binary

    @staticmethod
    def is_compatible(file):
        return file.suffix in BinaryDocumentParser.FORMATS

    @classmethod
    def parse(cls, document):
        return cls(document, None)

    def render(self):
        return None

