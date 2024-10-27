from __future__ import annotations

"""
The diverse objects and Data classes that are used to represent the entangled
entities during parsing and processing of entangled documents.
"""

__all__ = [
    "EntangledDocument",
    "EntangledCodeBlock",
    "RawCodeBlock",
]

from typing import Optional
from dataclasses import dataclass, field

from galac.proto_gen.entanglement_pb2 import Entanglement

from galac.parsing.parseable import DocumentKind

@dataclass
class ParsedEntanglementBlock:
    index: int
    entanglement: Entanglement
    kind: DocumentKind

@dataclass
class EntangledDocument:
    """
    An EntangledDocument is just a list of code blocks and entangled code blocks
    originating from noweb references.
    """
    children    : list                        = field(default_factory=list)
    parent      : Optional[EntangledDocument] = None
    source_file : str                         = None

    def __repr__(self):
        return f"<{self.__class__.__name__} children={self.children}>"

    def __str__(self):
        def format_children(children):
            for child in children:
                if isinstance(child, NonEntangledCodeBlock):
                    yield "Error: Unresolved Entangled Block."
                elif isinstance(child, EntangledCodeBlock):
                    yield f"{' ' * child.indent}<<{child.ref_name}>>"
                elif isinstance(child, RawCodeBlock):
                    yield from child.children
        return "\n".join(format_children(self.children))

    def entangled(self):
        """
        Traverses the nested structure and returns all entangled code blocks.
        If a cycle is detected, it stops and yields a cycle warning.
        """
        def format_child(child, comment_chars, seen=None):
            if seen is None:
                seen = set()

            if isinstance(child, NonEntangledCodeBlock):
                yield "Error: Unresolved Entangled Block."

            elif isinstance(child, EntangledCodeBlock):
                header, footer = EntangledNowebBloodhound\
                    .generate_entangled_block(child.source, child.ref_name, comment_chars)
                yield header
                if child.ref_name in seen:
                    yield f"{' ' * child.indent}>>>>>>>>"
                    yield f"{' ' * child.indent}Cycle detected: {child.ref_name}"
                    yield f"{' ' * child.indent}<<<<<<<<<<"
                    yield footer
                    return

                seen.add(child.ref_name)
                for grandchild in child.children:
                    yield from format_child(grandchild, comment_chars, seen)
                yield footer

            elif isinstance(child, RawCodeBlock):
                yield from child.children

            elif isinstance(child, EntangledDocument):
                file_header, file_footer = EntangledNowebBloodhound\
                    .generate_entangled_document(self.source_file, comment_chars)
                yield file_header
                for grandchild in child.children:
                    yield from format_child(grandchild, comment_chars, seen)
                yield file_footer

            else:
                yield repr(child)

        return "\n".join(format_child(self, comment_chars))
        
    def flatten(self):
        """ Extract all nested EntangledCodeBlock objects and return them as a flat list. """
        def flatten_children(children):
            for child in children:
                if isinstance(child, EntangledCodeBlock):
                    yield child
                    yield from flatten_children(child.children)
                elif isinstance(child, RawCodeBlock):
                    yield from flatten_children(child.children)
        return list(flatten_children(self.children))

    def remove_child_by_ref_name(self, ref_name):
        """ Delete children that have a specific ref_name, as well as subchildren
        of children that have a specific ref_name. """
        for child in self.children:
            if isinstance(child, EntangledCodeBlock) and child.ref_name == ref_name:
                self.children.remove(child)
            else:
                child.remove_child_by_ref_name(ref_name)

    def create_target_file(self, target_file, comment_chars):
        """ Create a target file from the entangled document. """
        body = self.entangled(comment_chars)
        file.touch()
        with open(file, "w") as f:
            f.write("\n".join(body))

@dataclass
class EntangledCodeBlock(EntangledDocument):
    """
    An EntangledCodeBlock is a code block that is entangled with another code
    block.
    """
    source:   str = None
    ref_name: str = None
    indent:   int = 0

    def __repr__(self):
        return f"<{self.__class__.__name__} ref_name={self.ref_name} source={self.source} indent={self.indent} children={self.children}>"

    def __str__(self):
        def format_children(children):
            for child in children:
                if isinstance(child, EntangledCodeBlock):
                    yield f"{' ' * child.indent}<<{child.ref_name}>>"
                elif isinstance(child, RawCodeBlock):
                    yield from child.children
        return "\n".join(format_children(self.children))

@dataclass
class NonEntangledCodeBlock(EntangledCodeBlock):
    pass
    #    @property
    #def source(self):
    #    return Exception("NonEntangledCodeBlock does not have a source.")

@dataclass
class RawCodeBlock(EntangledDocument):
    """
    A RawCodeBlock is a code block that is not entangled with another code
    block.
    """
    children: list[str] = field(default_factory=list)

    def __repr__(self):
        return f"<{self.__class__.__name__} children={repr(self.__str__())}>"

    def __str__(self):
        return "\n".join(self.children)

    def raw(self):
        return r'{self.__str__}'

