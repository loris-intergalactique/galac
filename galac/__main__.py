#!/usr/bin/env python3

""" Galac
Galac is a tool allowing you to do literate programming, particularly in
Obsidian Markdown files.

I use it as part of a my research workflow, which also uses the following tools:
- Luhmann's slip-box
- Obsidian

This tool was inspired by the work of entangled.py.
"""

__author__ = "Loris Intergalactique"

import logging

from pathlib import Path
from xxhash import xxh64

import coloredlogs
import rich_click as click

from galac.models.diff import (
    DiffedFileType,
    DiffedCodeBlock,
    DiffedCodeBlockType,
)
from galac.utils import (
    Diff,
    GalacTree,
    colored_diff,
    flashy_print,
    alternative_color_print,
    setup_colors,
    setup_logging,
    verbose_levels,
    just_read,
    line_separator,
    generate_dummy_name,
)
from galac.entanglement_management import (
    Intergalactangled,
)
from galac.models.errors import (
    NoEntangledWorkspaceError,
)
from galac.version import __version__

setup_colors()
logger       = logging.getLogger("galac.__main__")
pass_galac   = click.make_pass_decorator(Intergalactangled, ensure = True)
galac_target = click.argument(
    "target",
    default=None,
    required=False,
    type=click.Path(
        exists=True, file_okay=True,
        dir_okay=True, path_type=Path,
    ),
)

def die(message):
    """Print a message and exit the program."""
    click.echo(click.style(message, fg="red"), err=True)
    click.get_current_context().exit(1)

@click.group()
@click.option(
    '-v', '--verbose',
    count=True,
    help="Increase verbosity from -v (error level) to -vvvv (debug level).",
)
@click.version_option(version=__version__, prog_name="Galac")
@pass_galac
def galac(intergalactangled, verbose):
    """
    This is the entrypoint for the Galac tool.

    It sets up logging and the main singleton, used to manage the workspace.
    """
    coloredlogs.install(level=verbose_levels.get(verbose, logging.CRITICAL))
    if click.get_current_context().invoked_subcommand == "init":
        return

    logger.info("Galac is starting.")
    try:
        relative_root     = Intergalactangled.find_workspace()
        intergalactangled = Intergalactangled.from_current_dir(relative_root)
    except NoEntangledWorkspaceError:
        die("Not an entangled workspace (or any of the parent directories)")

    click.get_current_context().obj = intergalactangled
    logger.info("Galac is ready.")
    
@galac.command()
@click.option(
    "-d", "--directory",
    type=click.Path(
        dir_okay=True,
        path_type=Path,
        file_okay=False,
    ),
    default=Path.cwd(),
)
def init(directory):
    """
    Creates an empty galac workspace or reinitializes an existing one.
    This command creates an empty galac workspace - basically a .intergalac
    directory with objects containing structures managing entanglements.

    Running galac init in an existing workspace is safe. It will not overwrite
    things that are already there.
    """
    if Intergalactangled.intergalac_exists(directory):
        if not click.confirm("Reinitialize existing workspace?"):
            die("Aborting workspace initialization.")
        logger.info("Deleting existing workspace.")
        Intergalactangled.delete_workspace(directory)
        init_type = "Reinitialized"
    else:
        init_type = "Initialized"

    logger.info("Creating workspace and indexes.")
    intergalactangled = Intergalactangled.create_workspace(directory)
    intergalactangled.scan_new_workspace()
    intergalactangled.save_indexes()

    for entanglement in intergalactangled.raw_entanglements:
        if entanglement.definition.indirect_target_file:
            logger.info(f"Detected '{entanglement.definition.name}'.")

    click.echo(f"{init_type} entangled workspace in {directory.resolve()}.")

@galac.command()
@galac_target
@click.option(
    "-u", "--show-unchanged",
    is_flag=True,
    help="Show unchanged files."
)
@pass_galac
def status(intergalactangled, target, show_unchanged):
    """
    Shows the workspace status.

    Displays paths that differ from the index file.
    """
    if not target:
        target = intergalactangled.relative_root

    else:
        if not intergalactangled.is_within_workspace(target):
            die(f"Target {target} is outside workspace at"
                f" {intergalactangled.relative_root}.")

    logger.debug(f"Target: {target.resolve()}")
    status_generator = intergalactangled.get_status(target)
    if not show_unchanged:
        status_generator = filter(
            lambda d: d.status != DiffedFileType.Unchanged,
            status_generator,
        )

    logger.info(f"Now checking workspace files status.")
    for diffed_file in status_generator:
        click.echo(colored_diff(
            diffed_file.status.value,
            intergalactangled.relative_path(diffed_file.filename)
            ),
        )

@galac.command()
@galac_target
@click.option(
    "-u", "--show-unchanged",
    is_flag=True,
    help="Show unchanged blocks."
)
@pass_galac
def blocks(intergalactangled, target, show_unchanged):
    """
    Shows the workspace status and goes deeper than `status` by also displaying
    blocks which differ from the index file.
    """
    if not target:
        target = intergalactangled.relative_root
    else:
        if not intergalactangled.is_within_workspace(target):
            die(f"Target {target} is outside workspace at"
                f" {intergalactangled.relative_root}.")

    logger.debug(f"Target: {target.resolve()}")
    status_generator = intergalactangled.get_status(target)
    if not show_unchanged:
        status_generator = filter(
            lambda d: d.status != DiffedFileType.Unchanged,
            status_generator,
        )

    logger.info(f"Now checking the status of the files in {target}.")
    tree = GalacTree(flashy_print(target.resolve()))
    for diffed_file in status_generator:
        relative_path = intergalactangled.relative_path(diffed_file.filename)

        tree.create_root_node(
            colored_diff(diffed_file.status.value, relative_path),
            diffed_file.filename)

        logger.debug(f"File: {relative_path} - Status: {diffed_file.status}")
        if diffed_file.status == DiffedFileType.Deleted:
            blocks = intergalactangled.get_blocks_as_deleted(relative_path)
        else:
            blocks = intergalactangled.get_block_status(relative_path)
        for diffed_entanglement_block in blocks:
            entanglement = diffed_entanglement_block.parsed_entanglement
            name         = entanglement.definition.name
            source       = entanglement.definition.file
            block_value  = diffed_entanglement_block.status.value
            logger.debug(f"Block: [{name}]")
            logger.debug(f"Code: [{repr(entanglement.block.content)}]")
            logger.debug(f"Hash: [{entanglement.block.hash}]")

            if Path(source).resolve() != relative_path.resolve():
                name = "{%s}@{%s}" % (name, source)

            tree.create_node(
                colored_diff(block_value, name),
                f"{diffed_file.filename}-{name}-{block_value}",
                parent=diffed_file.filename)

    click.echo(tree.show(stdout=False))

@galac.command()
@galac_target
@click.option(
    "-d", "--description",
    prompt="Description",
    help="A description of the changes being prepared.",
    default="No Message",
)
@pass_galac
def prep(intergalactangled, target, description):
    """
    Creates change records using the current content found in the workspace, to
    prepare changes to the entangled files.

    This function creates a snapshot of changes required to be made to the
    entangled files, and saves them in a preparation context to be applied
    later.

    Apply the patch files with the `apply` command.
    """
    logger.info(
        f"Resolving workspace-wide references for potentially new"
        " references to take into account.")

    intergalactangled.update_workspace_references()

    logger.info("Setting up the preparation context.")
    target_files_to_tangle = set()
    intergalactangled.initialize_staging_context(description)

    logger.info(f"Now checking the status of the files in {target}.")
    for diffed_file in intergalactangled.get_status(target):

        logger.info(f"File {diffed_file.filename} - {diffed_file.status}")
        relative_path = intergalactangled.relative_path(diffed_file.filename)

        if diffed_file.status == DiffedFileType.Unchanged:
            continue

        elif diffed_file.status == DiffedFileType.Created:
            logger.info(f"Staging addition of {relative_path} to the index.")
            intergalactangled.stage_file_indexation(diffed_file.filename)

        elif diffed_file.status == DiffedFileType.Deleted:
            logger.info(f"Staging removal of {relative_path} to the index.")
            intergalactangled.stage_file_unindexation(diffed_file.filename)

            logger.info(f"Preparing {relative_path}'s blocks for deletion.")
            status_generator = intergalactangled.get_blocks_as_deleted(
                relative_path)
        else:
            logger.info(f"Preparing {relative_path}'s blocks for update.")
            status_generator = intergalactangled.get_block_status(relative_path)

        logger.info(f"Looping over the blocks.")
        for diffed_entanglement_block in status_generator:
            status            = diffed_entanglement_block.status
            entanglement      = diffed_entanglement_block.parsed_entanglement
            diffed_definition = entanglement.definition

            logger.info(f"Entanglement {diffed_definition.name} - {status}")
            if diffed_entanglement_block.status == DiffedCodeBlockType.Deleted:

                """
                Deleting a definition file deletes all target files created
                from its blocks.

                Deleting a "target file" does not delete the block from the
                definition file.
                """
                if (
                    diffed_file.filename == diffed_definition.file
                    and diffed_file.status == DiffedFileType.Deleted
                ):
                    logger.info("Definition file is being deleted.")
                    logger.info("Looking for the block's target file.")
                    target_file = entanglement.definition.target_file
                    if not target_file:
                        logger.info("No target file found for the block.")

                    else:
                        logger.info(f"Preparing {target_file} for deletion.")
                        intergalactangled.stage_file_deletion(
                            intergalactangled.relative_root / target_file)

                logger.info("Looking all files using the entanglement.")
                other_target_files = intergalactangled\
                    .get_related_files(diffed_definition.name)

                for other_target_file in other_target_files:
                    logger.info(f"Preparing {other_target_file} for update.")
                    intergalactangled.stage_file_update(
                        other_target_file,
                        Diff(
                            other_target_file,
                            intergalactanged.remove_block_mention(
                                entanglement,
                                other_target_file,
                            ),
                        )
                    )

            if (
                diffed_entanglement_block.status == DiffedCodeBlockType.Modified
                or
                diffed_entanglement_block.status == DiffedCodeBlockType.Created
            ):
                """
                Blocks that are created or modified can either create new
                target files or modify existing ones.
                """

                target_file = entanglement.definition.target_file

                logger.info("Getting the most up-to-date block data")
                new_base_block = intergalactangled\
                    .get_current_entanglement_blocks(entanglement)

                new_base_block = str(new_base_block)

                if not target_file:
                    logger.info("No target file found for the block.")
                    logger.info("Only indirect target files will be checked.")

                target_file = intergalactangled.relative_root / target_file

                logger.info("The block has a target file.")
                if not target_file.exists():
                    logger.error(f"Target {target_file} will be created.")
                    intergalactangled.stage_file_creation(
                        target_file,
                        new_base_block,
                    )

                elif (
                    target_file.exists()
                    and intergalactangled\
                        .target_file_has_changed(entanglement, target_file)
                ):
                    logger.info("Block has changed.")
                    action_prompt = click.prompt(
                        Diff.BLOCK_CHANGE_PROMPT,
                        type=click.Choice(["t", "b", "m"]),
                    )
                    new_base_block = Diff.chose_block(
                        action_prompt,
                        new_base_block,
                        str(target_file_parser.parsed_document),
                    )

                logger.info("Looking all files using the entanglement.")
                for parsed_indirect_document in intergalactangled\
                    .modified_indirect_blocks(entanglement):

                    action_prompt = click.prompt(
                        Diff.BLOCK_CHANGE_PROMPT,
                        type=click.Choice(["t", "b", "m"]),
                    )
                    other_base_block = Diff.chose_block(
                        action_prompt,
                        new_base_block,
                        str(parsed_indirect_document),
                    )

                logger.info("Updating the block.")
                base_block_parser.update_md_block(
                    diffed_code_block, 
                    new_base_block
                )

                final_block = base_block_parser.parsed_document.render()

                logger.info("Staging the block.")
                intergalactanged.stage_file_update(
                    entanglement.definition.file,
                    Diff(
                        entanglement.definition.file,
                        final_block,
                    )
                )

@galac.command()
@pass_galac
def log(intergalactangled):
    """
    Show preparation logs.

    List change records that have been prepared.
    """
    for record in intergalactangled.get_staging_index():
        click.echo(click.style(f"Hash ID: {record.id}", fg="yellow"))
        click.echo(f"Date: {record.preparation_time}")
        click.echo(f"Description: {record.description}")

@galac.command()
@galac_target
@pass_galac
def diff(intergalactangled, target):
    """
    This function takes the tangled data and create a ready-for-tangle state.
    Then, it shows all the changes that will be made to the workspace.
    """
    try:
        patch_files = intergalactangled.get_latest_preparation_context()
    except FileNotFoundError:
        die("No preparation context found. Please run `prep` first.")
    for patch_file in patch_files:
        logger.info(f"Patch file {patch_file}.")
        patch = just_read(patch_file)
        for line in patch.splitlines():
            click.echo(line)

@galac.command()
@pass_galac
def apply(intergalactangled):
    """
    This function retrieves the latest generated patches.
    After applying the patch files, all changed markdown files are then entangled
    to create the new entangled files.
    So:
    1. Retrieve the patch files
    2. Apply the patch files
    3. Entangle the files
    4. Save the indexes
    """
    # 1. Retrieve the patch files
    patch_files = intergalactangled.get_latest_preparation_context()
    # 2. Apply the patch files
    for patch_file in patch_files:
        logger.info(f"Applying patch file {patch_file}.")
        patch = just_read(patch_file)
        Diff.apply_patch(patch)
        logger.info(f"Patch file {patch_file} applied.")

    # 3. Entangle the files
    entanglements_to_tangle = intergalactangled.entanglement_index\
        .get_entanglements_to_tangle(target_files_to_tangle)
    for entanglement in entanglements_to_tangle:
        # This should be in a intergalactangled.tangle_entanglement(entanglement)
        # method.
        logger.info(f"Entanglement {entanglement.definition.name} to tangle.")
        parsed_file = DocumentParser(entanglement.definition.file)
        parsed_file.parse()
        entanglement_block = parsed_file.parsed_document.non_entangled_code_blocks.get(entanglement.definition.name)
        if not entanglement_block:
            logger.error(f"Block {entanglement.definition.name} not found in its supposed definition file.")
            continue

        new_document = intergalactangled.resolve_non_entangled_document(parsed_file.parsed_document)

        # save will render the parsed document and
        # save it to the target file
        comment_chars = self.config.get(entanglement.block.language, None)
        if not comment_chars:
            logger.error(f"Comment characters for {entanglement.block.language} not found.")
            return

        comment_chars = comment_chars.comment_characters
        rendering = new_document.create_target_file(
            entanglement.definition.target_file,
            comment_chars
        )
        logger.info(f"Entanglement {entanglement.definition.name} saved to {entanglement.definition.target_file}.")
        logger.info(f"Updating the indexes to reflect the changes.")
        entanglement.block.CopyFrom(CodeBlock(
            hash=xxhash.xxh64(entanglement_block).hexdigest(),
            content=entanglement_block,
            language=entanglement.block.language,
        ))
        intergalactangled.entanglement_index.add_entanglement(entanglement)
        target_file_index = self.intergalactangled.file_index.indexof_file(entanglement.definition.target_file)
        if target_file_index == -1:
            logger.info(f"{entanglement.definition.target_file} not found in the index, adding it.")
            intergalactangled.file_index.add_file(entanglement.definition.target_file)
        else:
            logger.info(f"{entanglement.definition.target_file} found in the index.")
            intergalactangled.file_index.update_file(entanglement.definition.target_file)

    # 4. Save the indexes
    intergalactangled.save_indexes()
    logger.info("Indexes updated.")

@galac.command()
@click.option(
    "-h", "--hash",
    is_flag=True,
    help="Show the hash of the file.",
)
@pass_galac
def files(intergalactangled, hash):
    """
    Use this to understand which files are in the index.
    """
    tree = GalacTree("File Index")
    for index, file in enumerate(intergalactangled.raw_files):
        file = file.filename if not hash else f"{file.filename} - {file.hash}"
        file = alternative_color_print(index, file)
        tree.create_root_node(file, file)
    click.echo_via_pager(tree.show(stdout=False))

@galac.command()
@click.option(
    "-s", "--show-files",
    is_flag=True,
    help="Show the referencing files.",
)
@pass_galac
def tree(intergalactangled, show_files):
    """
    Show a tree of the entanglements, with definition details
    """
    logger.info("Creating the tree showing the entanglement index.")
    tree = GalacTree("Entanglement Index")
    for entanglement in intergalactangled.raw_entanglements:
        logger.debug(f"Entanglement: {entanglement.definition.name}")
        entanglement_name     = entanglement.definition.name + "-" + entanglement.definition.indirect_target_file
        entanglement_file     = entanglement.definition.file
        entanglement_language = entanglement.block.language

        try:
            relative_path = Path(entanglement_file).resolve().relative_to(intergalactangled.relative_root)
        except ValueError:
            # Not finding the relative path means that the file is declared in
            # an entangled file, but not in a Markdown file.
            relative_path = Path(entanglement.definition.indirect_target_file).resolve().relative_to(intergalactangled.relative_root)
        tree.create_root_node(flashy_print(entanglement_name),entanglement_name)

        node = "Block"
        tree.create_node(node, f"{entanglement_name}-block", parent=entanglement_name)

        node = "Language"
        tree.create_node(f"{node}: {entanglement_language}", f"{entanglement_name}-language", parent=f"{entanglement_name}-block")

        node = "Source File"
        tree.create_node(f"{node}: {relative_path}", f"{entanglement_name}-src", parent=f"{entanglement_name}")

        node = "Attributes"
        tree.create_node(node, f"{entanglement_name}-attributes", parent=entanglement_name)
        tree.create_node(entanglement.definition.attributes, f"{entanglement_name}-attributes-content", parent=f"{entanglement_name}-attributes")

        node = "Referenced By"
        if entanglement.referenced_by:
            tree.create_node(
                node, f"{entanglement_name}-references",
                parent=entanglement_name)

        for reference in entanglement.referenced_by:
            logger.info(reference)
            if show_files:
                tree.create_node(f"{reference.name} ({reference.file})", f"{entanglement_name}-{reference.name}", parent=f"{entanglement_name}-references")
            else:
                tree.create_node(
                    reference.referenced_by, f"{entanglement_name}-{reference.referenced_by}", parent=f"{entanglement_name}-references")
    click.echo_via_pager(tree.show(stdout=False))
        
@galac.command()
@pass_galac
def vi(intergalactangled):
    """
    Open the configuration file in vim.
    """
    initial_content = just_read(intergalactangled.config.filename)
    Diff.vim(intergalactangled.config.filename)
    new_content = just_read(intergalactangled.config.filename)
    if initial_content == new_content:
        click.echo("Configuration file unchanged.")
        return

    for diff_line in Diff(initial_content, new_content).get_diff():
        click.echo(colored_diff(diff_line.type.value, diff_line.line))

@galac.command()
@galac_target
@pass_galac
def dummy(intergalactangled, target):
    """
    Create a dummy entanglement
    """
    intergalactangled.create_dummy_entanglement(target)
    logger.info(f"Dummy entanglement created for {target}.")

if __name__ == "__main__":
    galac()
