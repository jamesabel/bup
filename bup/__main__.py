"""
The entry point of bup: the GUI when run without command line arguments, the CLI otherwise.
"""

from ismain import is_main

from bup import arguments
from bup.cli import cli_main
from bup.gui import gui_main


def main():
    """
    Run bup, as the GUI or the CLI.
    """
    args = arguments()
    if args is None:
        gui_main()
    else:
        # there are command line arguments, so this is the CLI
        cli_main(args)


if is_main():
    main()
