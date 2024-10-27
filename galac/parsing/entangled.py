from __future__ import annotations

"""
Entangled Code Parsing Module
"""

import logging
import re
import mawk
from dataclasses import dataclass

import xxhash

from galac.utils import (
    just_read,
)
from galac.models.entangled_entities import (
    EntangledDocument,
    EntangledCodeBlock,
    RawCodeBlock,
)
from galac.proto_gen.entanglement_pb2 import (
    CodeBlock,
    Definition,
    Entanglement,
    Reference,
)
from galac.parsing import ParsedEntanglementBlock
from galac.parsing.parseable import DocumentKind
from galac.version import __version__

logger = logging.getLogger(__name__)

class EntangledDocumentParser:
    """
    """
    document_type = DocumentKind.Entangled

    def __init__(self, document, parsed_document):
        self.document        = document
        self.parsed_document = parsed_document

    def render_entanglement_to_file(self, file, comment_chars):
        return self.render_to_file(file, comment_chars)

    def render_to_file(self, file, comment_chars):
        """
        """
        rendering = self.parsed_document.create_target_file(file, comment_chars)
        with open(file, 'w') as f:
            f.write(rendering)

    def get_hash(self):
        """
        """
        return xxhash.xxh64(str(self.parsed_document)).hexdigest()

    def get_entanglements(self):
        """
        """
        if not self.parsed_document:
            return []

        # Main block
        code = str(self.parsed_document)
        hash = xxhash.xxh64(code).hexdigest()

        entanglement = Entanglement()
        entanglement.block.CopyFrom(CodeBlock(
            hash=hash,
            content=code,
            language=None,
        ))
        entanglement.definition.CopyFrom(Definition(
            name=str(self.document),
            file=self.parsed_document.source,
            target_file=str(self.document),
        ))
        yield ParsedEntanglementBlock(0, entanglement, DocumentKind.Entangled)

        # Nested blocks
        references = enumerate(e for e in self.parsed_document.flatten())
        for node_index, reference in references:
            code = str(reference)
            entanglement = Entanglement()
            entanglement.block.CopyFrom(CodeBlock(
                hash=xxhash.xxh64(code).hexdigest(),
                content=code,
                language=None,
            ))
            entanglement.definition.CopyFrom(Definition(
                name=reference.ref_name,
                file=reference.source,
                indirect_target_file=str(self.document),
            ))
            yield ParsedEntanglementBlock(node_index, entanglement, DocumentKind.Entangled)

    @classmethod
    def parse(cls, document):
        code = just_read(document)
        code = code.split("\n")
        parser = EntangledNowebBloodhound()

        entanglement_data = parser.extract_entanglement(code)
        if not entanglement_data:
            return cls(document, None)

        source, first_line, last_line = entanglement_data

        code = "\n".join(code[first_line+1:last_line])
        parser.run(code)
        parsed_document = parser.document
        parsed_document.source = source
        return cls(document, parsed_document)

    @staticmethod
    def is_compatible(file):
        return file.suffix != '.md'

@dataclass
class EntangledNowebBloodhound(mawk.RuleSet):
    """
    This class searches for entangled blocks in an entangled document.
    Headers and footers are considered already analyzed and confirmed to be present.
    """
    ENTANGLED_FILE_CONTENTS = (
        r"^.*"
        r"Entanglement: This file is entangled with "
        r"\{(?P<source>[^]]*)\}."
    )

    ENTANGLED_FILE_END = (
        r"^.*"
        r"End of file entanglement. Created by Intergalactangled \(Version \d+\.\d+\.\d+ \)\."
    )

    NOWEB_HEADER = (
        r"^(?P<indent>\s*).*"
        r"Entanglement: This block is entangled with"
        r" \{(?P<ref_name>[^]]*)\}@\{(?P<source>[^]]*)\}\."
    )

    NOWEB_FOOTER = (
        r"^(?P<indent>\s*).*"
        r"End of block entanglement."
    )

    def __init__(self):
        self.document = EntangledDocument()
        self.current_parent = self.document

    @mawk.on_match(NOWEB_HEADER)
    def on_header(self, m: re.Match):
        entangled_block = EntangledCodeBlock(
            source=m["source"],
            ref_name=m["ref_name"],
            indent=len(m["indent"]),
        )

        if type(self.current_parent) == EntangledDocument:
            logger.info("Adding entangled block to document")
            self.current_parent.children.append(entangled_block)
            self.current_parent = self.current_parent.children[-1]
            return []

        if type(self.current_parent) == EntangledCodeBlock:
            logger.info("Adding entangled block to code block")
            parent = self.current_parent
            self.current_parent.children.append(entangled_block)
            self.current_parent = self.current_parent.children[-1]
            self.current_parent.parent = parent

        if type(self.current_parent) == RawCodeBlock:
            logger.info("Adding entangled block to raw code block")
            parent = self.current_parent.parent
            self.current_parent = parent

            self.current_parent.children.append(entangled_block)
            self.current_parent = self.current_parent.children[-1]

        return []

    @mawk.on_match(NOWEB_FOOTER)
    def on_footer(self, m: re.Match):
        """
        """
        if type(self.current_parent) == RawCodeBlock:
            self.current_parent = self.current_parent.parent.parent

        if not hasattr(self.current_parent, "parent"):
            self.current_parent = self.document

        return []

    @mawk.always
    def on_line(self, line):
        if type(self.current_parent) in [EntangledDocument, EntangledCodeBlock]:
            self.current_parent.children.append(RawCodeBlock(
                parent=self.current_parent,
            ))
            self.current_parent = self.current_parent.children[-1]

        if type(self.current_parent) == RawCodeBlock:
            self.current_parent.children.append(line)

        return []

    def on_eof(self):
        """
        """
        logger.info("End of file reached.")
        logger.info("Document:")
        logger.info(repr(self.document))
        return []

    @classmethod
    def extract_entanglement(cls, code):
        """
        """
        if len(code) == 1 and len(code[0]) == 0:
            return None

        first_line = 0
        last_line  = -1 if len(code[-1]) > 0 else -2

        match    = re.match(cls.ENTANGLED_FILE_CONTENTS, code[first_line])
        file_end = re.search(cls.ENTANGLED_FILE_END, code[last_line])

        if not (match or file_end):
            return None

        return match.group('source'), first_line, last_line

    @staticmethod
    def generate_entangled_block(source, ref_name, indent=""):
        """
        This function returns blocks that are recognizable by the parser.
        """
        return f"{indent}# Entanglement: This block is entangled with {{{ref_name}}}@{{{source}}}.",\
               f"{indent}# End of block entanglement."

    @staticmethod
    def generate_entangled_document(source):
        """
        This function returns blocks that are recognizable by the parser.
        """
        return f"# Entanglement: This file is entangled with {{{source}}}.",\
               f"# End of file entanglement. Created by Intergalactangled (Version {__version__})."

