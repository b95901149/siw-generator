import sys

from siw_generator.console_encoding import configure_console_encoding

configure_console_encoding()

from siw_generator.cli import main as cli_main

def _main() -> int:
    if "--gui" in sys.argv:
        from siw_generator.gui import main as gui_main

        gui_main()
        return 0
    return cli_main()


raise SystemExit(_main())
