"""PyInstaller entry point for SIW Generator GUI."""

import matplotlib

matplotlib.use("TkAgg")

from siw_generator.console_encoding import configure_console_encoding

configure_console_encoding()

from siw_generator.gui import main

if __name__ == "__main__":
    main()
