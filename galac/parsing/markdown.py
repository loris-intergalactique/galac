from __future__ import annotations

"""
Markdown Parsing Utilities
"""

__all__ = [
    "MarkdownDocumentParser",
    "MarkdownExtra",
    "NowebBloodhound",
]

import logging
import re
import marko
import mawk

from dataclasses import dataclass

import xxhash

from marko import md_renderer

from galac.utils import (
    just_read,
)
from galac.proto_gen.entanglement_pb2 import (
    CodeBlock,
    Definition,
    Entanglement,
    Reference,
)
from galac.parsing.parseable import DocumentKind
from galac.models.entangled_entities import (
    ParsedEntanglementBlock,
    EntangledDocument,
    RawCodeBlock,
    NonEntangledCodeBlock,
)

logger = logging.getLogger(__name__)

class MarkdownDocumentParser:
    """
    This parser will parse Markdown files to understand their entanglement.
    """
    def __init__(self, document, parsed_document):
        self.document                  = document
        self.parsed_document           = parsed_document
        self.document_type             = DocumentKind.Markdown
        self.non_entangled_code_blocks = {}

    def render(self):
        m = md_renderer.MarkdownRenderer()
        return m.render(self.parsed_document)

    def render_to_file(self, file):
        with open(file, 'w') as f:
            f.write(self.render())

    def render_entanglement_to_file(self, file, comment_chars):
        """
        """
        raise NotImplementedError("Rendering entanglements to file is not supported for Markdown files.")

    def get_hash(self):
        return xxhash.xxh64(str(self.parsed_document)).hexdigest()

    @property
    def indexed_elements(self):
        yield from enumerate(self.parsed_document.children)

    def entanglement_filter(self, inode):
        node = inode[1]
        if not hasattr(node, "extra"):
            return False
        extra = MarkdownExtra(node.extra)
        return node.get_type() == "FencedCode" \
            and not extra.ignore() \
            and (extra.get_id() or extra.get_target_file()) \
            and len(node.children) > 0

    def entanglement_map(self, node):
        return {
            "code": node.children[0].children,
            "lang": node.lang,
            "extra": MarkdownExtra(node.extra),
        }

    def get_entanglements(self):
        """
        Find entanglements in the parsed document
        """
        filtered_children = filter(
            self.entanglement_filter,
            self.indexed_elements,
        )
        entanglement_map = map(
            lambda inode: (inode[0], self.entanglement_map(inode[1])),
            filtered_children,
        )
        for node_index, node_map in entanglement_map:
            logger.info(
                f"Found a code block with lang={node_map['lang']}"
                f" and extras={node_map['extra']}"
            )
            code = node_map["code"].rstrip()
            hash = xxhash.xxh64(code).hexdigest()

            entanglement = Entanglement()
            entanglement.block.CopyFrom(CodeBlock(
                hash=hash,
                content=code,
                language=node_map["lang"],
            ))
            if node_map["extra"].get_target_file():
                logger.info(f"-> Target file: {node_map['extra'].get_target_file()}")
                entanglement.definition.CopyFrom(Definition(
                    name=node_map["extra"].get_target_file(),
                    file=str(self.document.resolve()),
                    attributes=str(node_map["extra"].data),
                    target_file=node_map['extra'].get_target_file(),
                ))
            else:
                logger.info(f"-> Block ID: {node_map['extra'].get_id()}")
                entanglement.definition.CopyFrom(Definition(
                    name=node_map["extra"].get_id(),
                    file=str(self.document.resolve()),
                    attributes=str(node_map["extra"].data),
                ))

            if entanglement.definition.name in self.non_entangled_code_blocks.keys():
                logger.info(f"Entanglement {entanglement.definition.name} is already defined.")
                continue

            logger.info("Now searching for noweb references.")
            noweb_parser = NowebBloodhound()
            noweb_parser.run(code)
            self.non_entangled_code_blocks[entanglement.definition.name] = noweb_parser.document
            for reference in noweb_parser.noweb_references:
                logger.info(f"Found a noweb reference: {reference.reference}")
                entanglement.references_to.append(reference)

            yield ParsedEntanglementBlock(node_index, entanglement, DocumentKind.Markdown)

    """
    # This is replacing the children "str" of the children RawText from the Marko FencedCode.
    base_block_parser.parsed_document.children[diffed_code_block.index].children[0] = new_base_block
    """
    def update_md_block(self, diffed_code_block, new_base_block):
        self.parsed_document.children[diffed_code_block.index].children[0] = new_base_block

    @classmethod
    def parse(cls, document):
        return cls(document, marko.parse(just_read(document)))

    @staticmethod
    def is_compatible(file):
        return file.suffix == '.md'

class MarkdownExtra:
    """
    The Markdown files that Interglactangled is interested in can have extra
    informations in the fenced code blocks. These informations can be either
    attributes, or key-value pairs.
    """
    EXTRA_PATTERN = r'(?P<kv>(?:\S+)=(?:".*?"|\S+))|(?P<attr>(?:\S+))'

    def __init__(self, extra):
        self.extra = extra
        self.data = {}
        if not self.extra:
            return
        for kv, attr in re.findall(self.EXTRA_PATTERN, extra):
            if kv:
                key, value = kv.split("=")
                self.data[key] = value
            elif attr:
                if attr.startswith("#"):
                    self.data["id"] = attr[1:]
                else:
                    self.data[attr] = True

    def get_id(self):
        return self.data.get("id", None)

    def get_target_file(self):
        return self.data.get("file", None)

    def ignore(self):
        return self.data.get("ignore-markdown", False) \
            or self.data.get("ignore", False)

    def has_noweb(self):
        return self.data.get("noweb", False)

    def __str__(self):
        return f"<{self.data}>"

    def __repr__(self):
        return self.__str__()

class NowebBloodhound(mawk.RuleSet):
    """
    This class searches for 'noweb' references in a document.
    A 'noweb' reference typically includes markers or specific patterns used in literate programming.
    """
    NOWEB_REFERENCE = r"^(?P<indent>[\r\t\f ]*)<<(?P<ref_name>[\w-]+)>>[\r\t\f ]*$"

    def __init__(self):
        self.noweb_references = []
        self.line_number = 0
        self.document = EntangledDocument()
        self.current_parent = self.document

    @mawk.always
    def on_line(self, line):
        self.line_number += 1

    @mawk.on_match(NOWEB_REFERENCE)
    def on_noweb_reference(self, m: re.Match):
        reference             = Reference()
        reference.reference   = m["ref_name"]
        reference.indent      = m["indent"]
        #reference.line_number = self.line_number
        self.noweb_references.append(reference)

        entangled_block = NonEntangledCodeBlock(
            ref_name=m["ref_name"],
            indent=len(m["indent"]),
        )
        if type(self.current_parent) == EntangledDocument:
            self.current_parent.children.append(entangled_block)
        elif type(self.current_parent) == RawCodeBlock:
            parent = self.document
            self.current_parent.children.append(entangled_block)
        return []

    @mawk.always
    def get_line(self, line):
        if type(self.current_parent) == EntangledDocument:
            self.current_parent.children.append(RawCodeBlock(
                parent=self.current_parent,
            ))
            self.current_parent = self.current_parent.children[-1]
        if type(self.current_parent) == RawCodeBlock:
            self.current_parent.children.append(line)
        return []

