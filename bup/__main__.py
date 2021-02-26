from ismain import is_main

from bup import arguments
from bup.cli import cli_main
from bup.gui import gui_main

if is_main():
    args = arguments()
    if args is None:
        gui_main()
    else:
        # if we've not been given anything to do on the command line, then it must be CLI
        cli_main(args)
