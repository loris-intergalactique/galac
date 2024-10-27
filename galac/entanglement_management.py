#!/usr/bin/env python3

"""
This module is eesponsible for managing the entanglements between the files.

proto:

yntax = "proto3";

import "google/protobuf/timestamp.proto";

enum ChangeType {
  CREATE = 0;
  DELETE = 1;
  UPDATE = 2;
}

message CreationInput {
  string new_file_name    = 1;
  string new_file_content = 2;
}

message DeletionInput {
  string file_name = 1;
}

message UpdateInput {
  string existing_file_name = 1;
  string diff_content       = 2;
}

message ChangeRecord {
  ChangeType type = 1;

  oneof change_data {
    CreationInput create_data = 4;
    DeletionInput delete_data = 5;
    UpdateInput   update_data = 6;
  }
}

message ChangeRecordId {
  string id = 1;
  google.protobuf.Timestamp preparation_time = 2;
  string description = 3;
}

message ChangeRecords {
  ChangeRecordId id                = 1;
  string description               = 2;
  repeated ChangeRecord records    = 3;
  repeated string files_to_index   = 4;
  repeated string files_to_unindex = 5;
}

message ChangeIndex {
  repeated ChangeRecordId ids = 1;
}
"""

__all__ = [
    "Intergalactangled",
]

from dataclasses        import dataclass, field
from fnmatch            import fnmatch
from logging            import getLogger
from pathlib            import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from xxhash             import xxh64

from galac.utils import (
    Diff,
    load_file,
    mytimestamp,
    get_relative_path,
    get_latest_preparation_folder,
)
from galac.models.storages import (
    FileIndex,
    EntanglementIndex,
    Config,
)
from galac.models.diff import (
    DiffedFileType,
    DiffedFile,
    DiffedEntanglement,
    DiffedEntanglementBlock,
    DiffedEntanglementBlockType,
)
from galac.models.errors import (
    FileIndexException,
    EntanglementIndexException,
    NoEntangledWorkspaceError,
)
from galac.utils             import Diff, generate_dummy_name
from galac.parsing           import DocumentParser
from galac.parsing.entangled import EntangledNowebBloodhound

from galac.proto_gen.staging_pb2 import (
    ChangeType,
    CreationInput,
    DeletionInput,
    UpdateInput,
    ChangeRecord,
    ChangeRecords,
    ChangeRecordId,
    ChangeIndex,
)

logger = getLogger(__name__)

@dataclass
class Intergalactangled :
    config             : Config            = None
    file_index         : FileIndex         = None
    entanglement_index : EntanglementIndex = None
    staging_index      : ChangeIndex       = None
    relative_root      : Path              = None
    staging_context    : list              = ChangeRecords
    workspace_folder   : str               = field(init=False, default=".intergalac")
    glob_pattern       : str               = field(init=False, default="**/*")
    ignored_folders    : list              = field(init=False, default_factory=lambda: [
        ".intergalac/*.pbin",
        "**/.obsidian/*",
        "**/.obsidian/**/*",
    ])

    def get_target_files(self, base_path: Path = None):
        """
        """
        ignored_folders = [
            self.relative_root.resolve() / folder
            for folder in self.ignored_folders
        ] + \
        [
            self.relative_root.resolve() / folder
            for folder in self.config.ignore
        ]
        logger.debug(f"Ignored folders: {ignored_folders}")

        is_ignored = lambda path: any(
            (
                path.resolve().match(str(ignored))
                or fnmatch(path.resolve(), str(ignored))
            )
            for ignored in ignored_folders
        )

        if base_path:
            if base_path.is_file():
                if not is_ignored(base_path):
                    yield base_path

        for file_path in base_path.glob(self.glob_pattern):
            if not is_ignored(file_path):
                if file_path.is_file():
                    yield file_path

    def update_workspace_references(self, max_workers: int = 4):
        """
        Scans the workspace to update all entanglements. When this function
        ends, all entanglements have up-to-date referenced_by and references_to
        attributes.
        """
        futures = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for diffed_file in self.get_status(self.relative_root / '**/*'):
                logger.debug(f"--> Processing {file}.")
                if diffed_file.status == DiffedFileType.Unchanged:
                    continue
                futures.append(executor.submit(self.scan_file, unparsed_file))
        
        for future in as_completed(futures):
            for parsed_entanglement_block in future.result():
                # Update the original entanglement with the new references.
                original_entanglement = self.entanglement_index.indexof_entanglement(
                        parsed_entanglement_block.entanglement.definition.name)
                if original_entanglement == -1:
                    # This means the entanglement is new.
                    # The appending happens in the tangling process, not now.
                    # Let's still add its pointer to the referenced_by attributes
                    # if it references other entanglements.
                    logger.info(f"Entanglement {parsed_entanglement_block.entanglement.definition.name} not found in the index.")
                else:
                    original_entanglement = self.entanglement_index.get_entanglement(original_entanglement)
                    original_entanglement.referenced_to = parsed_entanglement_block.entanglement.references_to

                for new_referencer in parsed_entanglement.entanglement.references_to:
                    referencee = self.entanglement_index.indexof_entanglement(new_referencer.referencee)
                    if referencee == -1:
                        logger.info(f"Entanglement {referencer} not found in the index.")
                        continue
                    # Remove any reference of the new referencer in the referencee.
                    referencee.referenced_by = [
                        reference for reference in referencee.referenced_by
                        if reference.name != new_referencer.name
                    ]
                    referencee.referenced_by.append(new_referencer)
                    logger.info(f"'{entanglement.definition.name}' is now set to reference '{referencee.definition.name}'.")

    def scan_new_workspace(self, glob_pattern, max_workers: int = 4):
        """
        Scans the newly-initialized workspace, indexes the files and the already
        existing entanglements. Finishes by making sure that the references are
        correctly set.
        """
        logger.info("Scanning the newly-created workspace.")
        futures = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for file in self.get_target_files():
                logger.debug(f"Processing {file} in a thread executor.")
                self.file_index.add_file(file)
                unparsed_file = DocumentParser(file)
                futures.append(executor.submit(self.scan_file, unparsed_file))
        
        for future in as_completed(futures):
            for parsed_entanglement_block in future.result():
                entanglement = parsed_entanglement_block.entanglement
                logger.info(f"--> Indexing {entanglement.definition.name}.")
                self.entanglement_index.add_entanglement(entanglement)

        logger.info("Now processing the references.")
        for entanglement in self.entanglement_index.serialized_index.entanglements:
            for referencer in entanglement.references_to:
                referencee = self.entanglement_index.indexof_entanglement(referencer.reference)
                if referencee == -1:
                    logger.info(f"Entanglement {referencer} not found in the index.")
                    self.entanglement_index.add_entanglement(entanglement)
                    continue
                referencee = self.entanglement_index.get_entanglement(referencee)
                referencee.referenced_by.append(referencer)
                logger.info(f"'{entanglement.definition.name}' is now set to reference '{referencee.definition.name}'.")

    def scan_file(self, unparsed_file: DocumentParser):
        parsed_file = unparsed_file.parse()
        yield from parsed_file.get_entanglements()

    def get_related_target_files(self, entanglement):
        """
        This function traverses the referenced_by attributes of an entanglement
        recursively to find all target files that are related to it.
        """
        processed_references = []
        references = entanglement.referenced_by
        while len(references) != 0:
            reference = references.pop()

            if reference.name in processed_references:
                logger.error(f"Cyclic Reference: {reference.name} already processed.")
                continue

            processed_references.append(reference)

            corresponding_definition = self.entanglement_index.indexof_entanglement(reference.name)
            if corresponding_definition == -1:
                logger.error(f"Entanglement {reference.name} not found.")
                continue

            corresponding_definition = self.entanglement_index.get_entanglement(corresponding_definition)
            if corresponding_definition.definition.target_file:
                logger.info(f"Found a target file: {corresponding_definition.definition.target_file}.")
                yield corresponding_definition.definition.target_file 

            if corresponding_definition.referenced_by:
                references += corresponding_definition.referenced_by

        if references:
            logger.error(f"References {references} not found.")

    def save_indexes(self):
        self.file_index.save()
        self.entanglement_index.save()

    def get_relative_file_name(self, file: Path):
        return file.resolve().relative_to(self.relative_root)

    def get_entanglement_by_target_file_name(self, target: Path):
        if isinstance(target, str):
            target = Path(target)

        logger.info(f"Looking for the entanglement with target file {target}.")
        logger.info(f"Relative root: {self.relative_root}")
        relative_filename = target.resolve().relative_to(self.relative_root)

        index = self.entanglement_index.indexof_entanglement(str(relative_filename))
        if index == -1:
            logger.error(f"Entanglement with target file {target} not found.")
            return

        return self.entanglement_index.get_entanglement(index)

    def get_status(self, target: Path):
        """
        Retrieves File status, as well as the status of its entanglements.
        """
        if target.is_file():
            indexed_files = [
                file for file in self.raw_files
                if Path(file.filename).resolve() == target.resolve()
            ]
        else:
            indexed_files = [
                file for file in self.raw_files
                if (self.relative_root / file.filename).is_relative_to(target.resolve())
            ]

        for file in self.get_target_files(target):
            logger.debug(f"--> Checking candidate file {file.resolve()}.")
            found = False
            for i, f in enumerate(indexed_files):
                relative_target_file = file.resolve().relative_to(self.relative_root)
                relative_indexed_file = (self.relative_root / f.filename).relative_to(self.relative_root)
                if relative_target_file != relative_indexed_file:
                    logger.debug(f"Skipping {relative_target_file} as it is not {relative_indexed_file}.")
                    continue
                logger.debug(f"Found {f.filename} in the index.")
                found = True

                if f.fast_hash == FileIndex.get_file_hash(file):
                    yield DiffedFile(
                        filename=self.get_relative_file_name(file),
                        status=DiffedFileType.Unchanged)
                else:
                    yield DiffedFile(
                        filename=self.get_relative_file_name(file),
                        status=DiffedFileType.Modified)
                break
            if found:
                indexed_files.remove(f)
                continue

            if not found:
                yield DiffedFile(
                    filename=self.get_relative_file_name(file),
                    status=DiffedFileType.Created)

        for file in indexed_files:
            yield DiffedFile(
                filename=self.get_relative_file_name(Path(file.filename)),
                status=DiffedFileType.Deleted)

    def get_file_blocks(self, file: Path):
        yield from filter(
            lambda x: x.definition.file == str(file) \
                   or x.definition.target_file == str(file) \
                   or x.definition.indirect_target_file == str(file),
            self.raw_entanglements,
        )

    def remove_block_mention(self, entanglement, file):
        """
        This function removes the mention of an entanglement from a file.
        """
        logger.info(f"Removing {entanglement_name} from {file}.")
        parsed_file = DocumentParser(file).parse()

        for parsed_entanglement_block in parsed_file.get_entanglements():
            parsed_entanglement = parsed_entanglement_block.entanglement

            if entanglement.definition.name == parsed_entanglement.definition.name:
                parsed_file.parsed_document.remove_child_by_ref_name(
                    parsed_entanglement.definition.name)

        try:
            comment_chars = self.config.get_language_comment(
                parsed_entanglement.block.language)

        except ValueError:
            die(f"Comment characters for {entanglement.block.language} not found.")

        comment_chars = comment_chars.comment_characters
        return parsed_file.parsed_document.render(comment_chars),

    def modified_indirect_blocks(self, entanglement):
        other_target_files = self.get_related_files(entanglement.definition.name)

        for other_target_file in other_target_files:
            parsed_file = DocumentParser(other_target_file).parse()

            for parsed_entanglement_block in parsed_file.get_entanglements():
                parsed_entanglement = parsed_entanglement_block.entanglement

                if parsed_entanglement.definition.name == entanglement.definition.name:
                    parsed_entanglement_hash = parsed_entanglement.block.hash

                    if parsed_entanglement_hash != entanglement.block.hash:
                        parser = DocumentParser(other_target_file)
                        parser.parse()
                        yield parser.parsed_document

    def get_current_entanglement_blocks(self, entanglement):
        base_block_parser = DocumentParser(entanglement.definition.file)
        base_block_parser.parse()

        new_base_block = base_block_parser.non_entangled_code_blocks.get(
            entanglement.definition.name
        )

        if not new_base_block:
            raise Exception(
                f"Block {entanglement.definition.name}"
                f" not found in its supposed definition file.")
        return new_base_block

    def target_file_has_changed(self, entanglement, target_file):
        target_file_parser = DocumentParser(target_file)
        target_file_parser.parse()

        return entanglement.block.hash != target_file_parser.get_hash()


    def get_block_status(self, file: Path):
        parsed_file = DocumentParser(file).parse()
        non_processed_entanglements = set(
            map(
                lambda x: x.definition.name, 
                self.get_file_blocks(file),
            )
        )
        for parsed_entanglement_block in parsed_file.get_entanglements():
            entanglement = parsed_entanglement_block.entanglement
            logger.debug(f"Checking {entanglement.definition.name}.")
            index = self.entanglement_index.indexof_entanglement(entanglement.definition.name)

            if index == -1:
                entanglement.definition.name += "*"
                yield DiffedEntanglementBlock(entanglement, DiffedEntanglementBlockType.Created)
                continue

            indexed_entanglement = self.entanglement_index.get_entanglement(index)
            logger.info(f"Entanglement {indexed_entanglement.definition.name} found in the index.")
            if indexed_entanglement.definition.name in non_processed_entanglements:
                non_processed_entanglements.remove(indexed_entanglement.definition.name)

            logger.debug(f"Checking for potential {file} modified blocs.")
            logger.debug(f"Hashes: {entanglement.block.hash} {indexed_entanglement.block.hash}")
            if entanglement.block.hash == indexed_entanglement.block.hash:
                yield DiffedEntanglementBlock(entanglement, DiffedEntanglementBlockType.Unchanged)

            else:
                yield DiffedEntanglementBlock(entanglement, DiffedEntanglementBlockType.Modified)

        logger.debug(f"Checking for potential {file} deleted blocs.")
        for entanglement_name in non_processed_entanglements:
            logger.info(f"Entanglement {indexed_entanglement.definition.name} not found in the file.")
            index = self.entanglement_index.indexof_entanglement(entanglement_name)
            if index == -1:
                logger.error(f"Entanglement {entanglement_name} not found in the index.")
                continue
            entanglement = self.entanglement_index.get_entanglement(index)
            yield DiffedEntanglementBlock(entanglement, DiffedEntanglementBlockType.Deleted)

    def get_blocks_as_deleted(self, file: Path):
        for entanglement in self.get_file_blocks(file):
            yield DiffedEntanglementBlock(entanglement, DiffedEntanglementBlockType.Deleted)

    def create_entangled_code_block(self, entanglement):
        """
        This is pseudo code for now. The Markdown Parser needs to have 
        a method that can create a new entangled block out of a given code
        block.
        This is going to use the configuration file to determine the block
        comment characters.
        --- idea
        To make this agnostic, parse the file with the parser
        and just use render(). In any case both MarkdownKind and EntangledKind
        are represented with a Markdown representation. So in any case
        there's going to be a need to go from a Markdown representation to
        an entangled code representation.
        """
        comment_chars = self.config.get(entanglement.block.language, None)

        if not comment_chars:
            logger.error(f"Comment characters for {entanglement.block.language} not found.")
            return
        comment_chars = comment_chars.comment_characters
        parsed_file = DocumentParser(entanglement.definition.file).parse()
        parsed_file.save(comment_chars)

    def resolve_non_entangled_document(self, entangled_document_children, seen=None):
        """
        This function is supposed to resolve the non-entangled blocks by
        creating a new entangled block out of them. The goal is to change all
        the NonEntangledCodeBlocks to EntangledCodeBlocks
        
        What differencies a Newly resolved EntangledCodeBlock from a regular
        EntangledCodeBlock is that the former's children are lists, while
        the latter's children are generators.
        """
        if not seen:
            seen = set()
        for child in entangled_document_children:
            if isinstance(child, EntangledCodeBlock):
                yield child
                continue
            elif isinstance(child, RawCodeBlock):
                yield from child.children
                continue
            elif isinstance(child, NonEntangledCodeBlock):
                if child.ref_name in seen:
                    logger.error(f"Cycle detected: {child.ref_name}")
                    continue
                seen.add(child.ref_name)
                entanglement = self.entanglement_index.get_entanglement(child.ref_name)
                if entanglement == -1:
                    logger.warning(f"Entanglement {child.ref_name} not found.")
                    continue
                ref_name = child.ref_name
                indent   = child.indent
                source   = entanglement.definition.file
                entangled_code_block = EntangledCodeBlock(
                    ref_name=ref_name,
                    source=source,
                    indent=indent,
                )
                md_parser = DocumentParser(source)
                md_parser.parse()
                if not ref_name in md_parser.non_entangled_blocks.keys():
                    logger.warning(f"Entanglement {ref_name} not found in the source file.")
                    continue

                new_entanglement = md_parser.non_entangled_code_blocks[ref_name]
                entangled_code_block.children = self.resolve_non_entangled_document(
                    new_entanglement.children, seen)
                yield entangled_code_block

    def attach_preparation_file(self, diff):
        """
        This function creates a preparation file for a given diff.
        This means:
        1. Adding the file to the preparation_files list.
        2. Creating the patch file
        """
        self.preparation_files.append(diff)
        if not self.preparation_context:
            self.preparation_context = self.relative_root / f"preparation_files:{mytimestamp()}"
            self.preparation_context.mkdir()

        patch_file = self.preparation_context / f"{diff.filename}.patch"
        with open(patch_file, "w") as f:
            f.write(diff.patch)

    def get_latest_preparation_context(self):
        """
        This function returns the latest preparation context.
        This will be used by the "apply" command to apply the latest
        preparation context.
        """
        if not self.preparation_context:
            preparation_contexts = list(self.relative_root.glob("preparation_files:*"))
            if not preparation_contexts:
                raise FileNotFoundError("No preparation context found.")
            self.preparation_context = self.relative_root / get_latest_preparation_file(preparation_contexts)
        return get_latest_preparation_folder(preparation_contexts)

    def is_within_workspace(self, file: Path):
        return file.resolve().is_relative_to(self.relative_root)

    def relative_path(self, filename):
        return get_relative_path(Path.cwd(), self.relative_root / filename)

    def initialize_staging_context(self, description):
        self.staging_context = ChangeRecords()
        self.staging_context.id.hash = str(xxh64(mytimestamp()).digest())
        self.staging_context.id.preparation_time.FromDatetime(mytimestamp())
        self.staging_context.id.description = description
        self.staging_index.ids = set()

    def stage_file_indexation(self, filename):
        self.staging_context.files_to_index.append(filename)

    def stage_file_unindexation(self, filename):
        self.staging_context.files_to_unindex.append(filename)

    def stage_file_creation(self, filename, content):
        # Index the file first.
        self.stage_file_indexation(filename)

        # Then create the file.
        creation = CreationInput()
        creation.new_file_name = filename
        creation.new_file_content = content
        record = ChangeRecord()
        record.type = ChangeType.CREATE
        record.create_data = creation
        self.staging_context.records.append(record)

    def stage_file_deletion(self, filename):
        # Unindex the file first.
        self.stage_file_unindexation(filename)

        # Then delete the file.
        deletion = DeletionInput()
        deletion.file_name = filename
        record = ChangeRecord()
        record.type = ChangeType.DELETE
        record.delete_data = deletion
        self.staging_context.records.append(record)

    def stage_file_update(self, filename, diff):
        update = UpdateInput()
        update.existing_file_name = filename
        update.diff_content = diff
        record = ChangeRecord()
        record.type = ChangeType.UPDATE
        record.update_data = update
        self.staging_context.records.append(record)

    def save_staging_context(self, filename):
        with open(filename, "wb") as f:
            f.write(self.staging_context.SerializeToString())

    def get_staging_index(self):
        return self.staging_index.ids

    def create_dummy_entanglement(self, name=None):
        if not name:
            name = generate_dummy_name()

        py_file = Path(name + ".py")
        md_file = Path(name + ".md")
        ref_name = f"dummy_ref_name_{name}"

        header, footer = EntangledNowebBloodhound\
            .generate_entangled_block(md_file, ref_name)
        body = [
            header,
            "if __name__ == '__main__':",
            "    print('hello world')",
            footer
        ]
        if py_file.exists():
            mode = "a"
        else:
            py_file.touch()
            file_header, file_footer = EntangledNowebBloodhound\
                .generate_entangled_document(md_file)
            file_header = [file_header, "print('prelude')"]
            file_footer = ["print('epilogue')", "", file_footer]
            body = file_header + body + file_footer
            mode = "w"

        with open(py_file, mode) as f:
            f.write("\n".join(body))

        body = [
            "# Dummy Markdown File",
            "This is a dummy markdown file.",
            "",
            f"```python file={name}.py noweb",
            "print('prelude')",
            f"<<{ref_name}>>",
            "print('epilogue')",
            "```",
            "",
            "## Dummy noweb block",
            f"```python #{ref_name}",
            "if __name__ == '__main__':",
            "    print('hello world')",
            "```",
            "This is the end of the dummy markdown file."
        ]
        with open(md_file, "w") as f:
            f.write("\n".join(body))

    @classmethod
    def from_current_dir(cls, current_dir: Path = Path.cwd()):
        root_dir = current_dir.resolve() / cls.workspace_folder
        config_file             = root_dir / "config.toml"
        file_index_file         = root_dir / "file_index.pbin"
        entanglement_index_file = root_dir / "entanglement_index.pbin"
        staging_index_file      = root_dir / "staging_index.pbin"
        return cls(
            config             = cls.load_config(config_file),
            file_index         = cls.load_file_index(file_index_file),
            entanglement_index = cls.load_entanglement_index(entanglement_index_file),
            staging_index      = cls.load_staging_index(staging_index_file),
            relative_root      = current_dir.resolve(),
        )
    @classmethod
    def create_workspace(cls, root_directory: Path):
        logger.info(f"Creating Intergalactangled workspace.")
        workspace = root_directory / cls.workspace_folder
        workspace.mkdir()
        file_index_file         = workspace / "file_index.pbin"
        entanglement_index_file = workspace / "entanglement_index.pbin"
        config_file             = workspace / "config.toml"
        staging_index_file      = workspace / "staging_index.pbin"
        file_index_file.touch()
        entanglement_index_file.touch()
        config_file.touch()
        staging_index_file.touch()
        return cls(
            config             = cls.load_config(config_file),
            file_index         = cls.load_file_index(file_index_file),
            entanglement_index = cls.load_entanglement_index(entanglement_index_file),
            staging_index      = cls.load_staging_index(staging_index_file),
            relative_root      = cls.find_workspace(),
        )

    @classmethod
    def intergalac_exists(cls, root_directory):
        return (root_directory / cls.workspace_folder).exists()

    @staticmethod
    def load_config(filename: str):
        logger.debug(f"Loading {filename}.")
        return Config(filename=load_file(filename,"configuration file"))

    @staticmethod
    def load_file_index(filename: str):
        logger.debug(f"Loading {filename}.")
        file_index_file = load_file(filename, "file index")
        return FileIndex.from_file(file_index_file)

    @staticmethod
    def load_entanglement_index(filename: str):
        logger.debug(f"Loading {filename}.")
        entanglement_index_file = load_file(filename, "entanglement index")
        return EntanglementIndex.from_file(entanglement_index_file)

    @staticmethod
    def load_staging_index(filename: str):
        logger.debug(f"Loading {filename}.")
        staging_index_file = load_file(filename, "staging index")
        with open(filename, "rb") as f:
            staging_index_file = ChangeIndex()
            staging_index_file.ParseFromString(f.read())
        return staging_index_file

    @classmethod
    def find_workspace(cls):
        """
        """
        current_dir = Path.cwd()
        if not Path(cls.workspace_folder).exists():
            logger.info("Intergalactangled workspace not found in the current dir.")
            logger.info("Searching for the workspace in parent directories.")
            while str(current_dir) != current_dir.anchor:
                if (current_dir / cls.workspace_folder).exists():
                    logger.debug(f"Found Intergalactangled workspace at {current_dir}.")
                    return current_dir
                current_dir = current_dir.parent
            if current_dir == current_dir.anchor:
                logger.info("Intergalactangled workspace not found at all.")
                raise NoEntangledWorkspaceError
        logger.debug(f"Using relative root {current_dir}.")
        return current_dir.resolve()

    @classmethod
    def delete_workspace(cls, workspace: Path):
        logger.info(f"Deleting Intergalactangled workspace.")
        workspace = workspace / cls.workspace_folder
        for file in workspace.iterdir():
            logger.debug(f"Deleting {file}.")
            file.unlink()
        workspace.rmdir()

    @property
    def raw_files(self):
        """Shortcut to the file index."""
        return self.file_index.serialized_index.files

    @property
    def raw_entanglements(self):
        """Shortcut to the entanglement index."""
        return self.entanglement_index.serialized_index.entanglements

