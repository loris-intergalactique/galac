
"""
Utility functions for the project.
"""

__all__ = [
    "setup_logging",
    "setup_colors",
    "flashy_print",
    "alternative_color_print",
    "colored_diff",
    "just_read",
    "GalacTree",
    "Diff",
]

import os
import logging

from subprocess import call
from datetime import datetime
from pathlib import Path

import coloredlogs

from treelib import Tree
from colorama import Back, Fore, init as colorama

verbose_levels = {
    0: logging.CRITICAL,
    1: logging.ERROR,
    2: logging.WARNING,
    3: logging.INFO,
    4: logging.DEBUG,
}

line_separator = "-" * 80

logger = logging.getLogger(__name__)

def setup_logging(name, verbose=0):
    logging.basicConfig(level=verbose_levels[verbose])
    coloredlogs.install(level=verbose_levels[verbose])
    return logging.getLogger(name)

def setup_colors():
    os.environ["COLOREDLOGS_LOG_FORMAT"] = (
            "%(asctime)s %(hostname)s "
            "%(name)s@%(funcName)-10s:%(lineno)-5d "
            "%(levelname)-5s %(message)s")
 
    colorama(autoreset=True)

def flashy_print(text):
    return f"{Back.CYAN+Fore.BLACK}{text}{Fore.RESET+Back.RESET}"

def alternative_color_print(index, text):
    color = Back.CYAN+Fore.BLACK if index % 2 == 0 else Back.BLUE+Fore.YELLOW
    reset = Fore.RESET+Back.RESET
    return f"{Fore.BLACK+Back.BLACK}{index}{color}{text}{reset}"

def colored_diff(diff_status, diff_data):
    colors ={
        "unchanged": Fore.WHITE,
        "modified" : Fore.YELLOW,
        "created"  : Fore.GREEN ,
        "deleted"  : Fore.RED,

        "equal"    : Fore.WHITE,
        "insert"   : Fore.GREEN,
        "delete"   : Fore.RED,
    }

    return f"{colors[diff_status]}{diff_status}:\t{diff_data}{Fore.RESET}"

def just_read(file_path):
    with open(file_path, "r") as file:
        return file.read()

class GalacTree:
    def __init__(self, root_node=None):
        self.tree = Tree()

        if root_node:
            self.tree.create_node(root_node, "root")

    def create_root(self, root_node):
        self.tree.create_node(root_node, "root")

    def create_root_node(self, node, node_id):
        self.tree.create_node(node, node_id, parent="root")

    def create_node(self, node, node_id, parent):
        self.tree.create_node(node, node_id, parent=parent)

    def show(self, stdout=True):
        return self.tree.show(stdout=stdout)

    def contains(self, node_id):
        return self.tree.contains(node_id)

class Diff:
    BLOCK_CHANGE_PROMPT = (
        f"Choose what block will overwrite the blocks:"
        f" The {Back.GREEN+Fore.BLACK}[t]{Back.RESET+Fore.RESET}arget file"
        f", the {Back.BLUE+Fore.BLACK}[b]{Back.RESET+Fore.RESET}ase block"
        f", or a manual {Back.YELLOW+Fore.BLACK}[m]{Back.RESET+Fore.RESET}erge."
    )

    def __init__(self, a, b):
        self.a = a
        self.b = b

    def is_empty(self):
        try:
            next(
                difflib.unified_diff(
                    self.a.content.split("\n"),
                    self.b.split("\n")
                )
            )
        except StopIteration:
            return True
        return False
    

    def get_diff(self):
        for line in difflib.unified_diff(
            self.a.split("\n"),
            self.b.split("\n") if self.b else list(),
        ):
            line = line.strip("\n")

            if line.startswith("+"):
                yield DiffedLine(line, DiffedLineType.Insert)
            elif line.startswith("-"):
                yield DiffedLine(line, DiffedLineType.Delete)
            else:
                yield DiffedLine(line, DiffedLineType.Equal)

    def to_file(self, filename):
        with open(filename, "w") as file:
            for line in self.get_diff():
                file.write(str(line))

    @classmethod
    def deletion(cls, a):
        return cls(a, None)

    @classmethod
    def chose_block(cls, action_prompt, base_block, secondary_block):
        match action_prompt:
            case "m":
                click.echo("Calling vim -d.")
                return Diff.solve_conflict(base_block, secondary_block)
            case "t":
                return secondary_block
            case "b":
                return base_block
        return None

    @staticmethod
    def solve_conflict(target_block, second_block):
        """
        This file aims to make the user manually solve potential conflicts
        between two blocks of code supposed to be the same.
        """
        with tempfile.TemporaryDirectory() as tempdir:
            with tempfile.NamedTemporaryFile(
                "w",
                dir=tempdir,
                delete=False,
                prefix="do_not_touch_",
            ) as second:
                second.write(second_block)

            with tempfile.NamedTemporaryFile(
                "w",
                dir=tempdir,
                delete=False,
                prefix="change_me_",
            ) as target:
                target.write(target_block)

            Diff.vim([target.name, second.name])

        return just_read(target.name)

    @staticmethod
    def vim(file_list):
        if not type(file_list) == list:
            file_list = [file_list]
        call(["vim", "-d"] + file_list)

def load_file(filename, name):
    if not filename.exists():
        raise FileNotFoundError(f"{name} not found.")
    if not os.access(filename, os.R_OK):
        raise PermissionError(f"{name} not readable.")
    return filename

def get_relative_path(base_folder, target_file):
    if base_folder == target_file.parent:
        return Path(target_file.name)

    if target_file.parent.is_relative_to(base_folder):
        return Path(target_file.relative_to(base_folder))

    base_parents = [base_folder] + list(base_folder.parents)
    base_parents.reverse()
    for i, parent in enumerate(base_parents):
        if not parent in target_file.parents:
            common_parent = (len(base_parents) - base_parents.index(parent)) * "../"
            return Path(common_parent + str(target_file.relative_to(base_parents[i-1])))

def mytimestamp():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def get_latest_preparation_folder(folder_names):
    """
    Each file has this format path_to_file:2021-01-01_00-00-00
    """
    files_with_timestamps = []
    for folder_name in folder_names:
        timestamp_str = folder_name.split(":")
        try:
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d_%H-%M-%S")
            files_with_timestamps.append((f, timestamp))
        except ValueError:
            continue  # Skip files that don't match the timestamp format

    if not files_with_timestamps:
        raise FileNotFoundError("No files found in the given folder.")

    files_with_timestamps.sort(key=lambda x: x[1], reverse=True)
    return files_with_timestamps[0][0]

def generate_dummy_name():
    return f"dummy_{mytimestamp()}"
