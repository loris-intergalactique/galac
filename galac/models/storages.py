from __future__ import annotations

"""
This module covers files that are used to store data and configurations.
"""

__all__ = [
    "FileIndex",
    "EntanglementIndex",
    "Config",
]

from os          import access, R_OK
from fnmatch     import fnmatch
from logging     import getLogger
from dataclasses import dataclass, field
from enum        import Enum
from pathlib     import Path

import toml
import xxhash

from galac.utils import (
    just_read,
)
from galac.models.errors import (
    FileIndexException,
    EntanglementIndexException,
)
from galac.proto_gen.file_pb2 import (
    File,
    FileIndex as RawFileIndex,
)
from galac.proto_gen.entanglement_pb2 import (
    EntanglementIndex as RawEntanglementIndex,
    Language,
    LanguageComment,
)

logger = getLogger(__name__)

@dataclass
class FileIndex:
    filename: str
    serialized_index: RawFileIndex = field(default_factory=RawFileIndex)

    @staticmethod
    def get_file_hash(file: Path):
        if isinstance(file, str):
            return xxhash.xxh64(file.encode()).hexdigest()
        if isinstance(file, Path):
            return xxhash.xxh64(file.read_bytes()).hexdigest()
        raise TypeError(f"Expected str or Path, got {type(file)}.")

    @staticmethod
    def is_readable(file: Path):
        return access(file, R_OK)

    def indexof_file(self, file: Path):
        for index, pb_file in enumerate(self.serialized_index.files):
            if pb_file.filename == str(file):
                return index
        return None

    def add_file(self, file: Path):
        if not self.is_readable(file):
            raise FileIndexException(f"{file} is not readable.")

        if self.indexof_file(file) is not None:
            logger.warning(f"{file} already exists in the index.")

        pb_file = File()
        pb_file.filename  = str(file)
        pb_file.fast_hash = self.get_file_hash(just_read(file))

        self.serialized_index.files.append(pb_file)

    def remove_file(self, file: Path):
        index = self.indexof_file(file)
        if index is not None:
            return self.serialized_index.files.pop(index)
        else:
            raise FileIndexException(f"{file} does not exist in the index.")

    def update_file(self, file: Path):
        index = self.indexof_file(file)
        if index is not None:
            self.serialized_index.files[index].fast_hash = just_read(file)
        else:
            raise FileIndexException(f"{file} does not exist in the index.")
    
    def generate_file_index(self, files: list[Path]):
        serialized_index = RawFileIndex()
        for file in files:
            logger.info(f"Adding {file} to the index.")
            pb_file = File()

            pb_file.filename  = str(file)
            pb_file.fast_hash = xxhash.xxh64(file.read_bytes()).hexdigest()
            self.file_index.serialized_index.files.append(pb_file)

        with open(self.file_index.filename, "wb") as f:
            return f.write(self.file_index.serialized_index.SerializeToString())

    @classmethod
    def from_file(cls, filename: str):
        file_index = cls(filename)
        with open(filename, "rb") as f:
            file_index.serialized_index.ParseFromString(f.read())
        return file_index

    @staticmethod
    def new_file(filename: str):
        file = File()
        file.filename = filename
        return file

    def save(self):
        with open(self.filename, "wb") as f:
            f.write(self.serialized_index.SerializeToString())

@dataclass
class EntanglementIndex:
    filename         : str
    serialized_index : RawEntanglementIndex = field(default_factory=RawEntanglementIndex)

    @classmethod
    def from_file(cls, filename: str):
        entanglement_index = cls(filename)
        with open(filename, "rb") as f:
            entanglement_index.serialized_index.ParseFromString(f.read())
        return entanglement_index

    def save(self):
        with open(self.filename, "wb") as f:
            f.write(self.serialized_index.SerializeToString())

    def indeof_entanglement_by_target_file(self, target_file: Path):
        for index, pb_entanglement in enumerate(self.serialized_index.entanglements):
            if pb_entanglement.target_file == str(target_file):
                return index
        return -1

    def indexof_entanglement(self, entanglement_name):
        for index, pb_entanglement in enumerate(self.serialized_index.entanglements):
            if pb_entanglement.definition.name == entanglement_name:
                return index
        return -1

    def get_entanglements_to_tangle(self, target_files: set[str]):
        for target_file in target_files:
            index = self.indexof_entanglement_by_target_file(target_file)
            if index != -1:
                yield self.serialized_index.entanglements[index]

    def get_entanglement(self, index: int):
        return self.serialized_index.entanglements[index]

    def add_entanglement(self, entanglement: Entanglement):
        """
        Check if the entanglement is already in the index before adding it.
        """
        if self.indexof_entanglement(entanglement) != -1:
            logger.info(
                f"Entanglement {entanglement} already exists in the index."
            )
        else:
            self.serialized_index.entanglements.append(entanglement)

    def remove_entanglement(self, entanglement: Entanglement):
        index = self.indexof_entanglement(entanglement)
        if index is not None:
            return self.serialized_index.entanglements.pop(index)
        else:
            raise EntanglementIndexException(
                f"Entanglement {entanglement} does not exist in the index."
            )

class Config:
    def __init__(self, filename: str):
        self.filename = filename
        self.ignore = []
        self.languages = []

        with open(self.filename, "r") as f:
            config = toml.load(f)

        self.ignore = config.get("ignore", [])
        self.languages = config.get("languages", [])

    def __str__(self):
        return (
            f"<Config: {self.filename};"
            f" Ignore: {self.ignore};"
            f" Languages: {self.languages}>"
        )

    def __repr__(self):
        return (
            f"<Config: {self.filename};"
            f" Ignore: {self.ignore};"
            f" Languages: {self.languages}>"
        )

    def get_language(self, language_name: str):
        for language in self.languages:
            if language["name"] == language_name:
                return language
        raise ValueError(f"Language {language_name} not found.")

    def get_language_comment(self, language_name: str):
        language = self.get_language(language_name)
        return language["comments"]
