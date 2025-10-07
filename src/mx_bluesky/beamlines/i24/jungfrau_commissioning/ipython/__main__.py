import pathlib

import IPython
from traitlets.config import Config

__all__ = [
    "main",
]


def main():
    IPython.start_ipython(colors="neutral", config=setup)


if __name__ == "__main__":
    setup: Config = Config()
    main_dir = pathlib.Path(__file__).parent.resolve()
    setup.InteractiveShellApp.exec_files = [str(main_dir / "setup_ipython.py")]
    main()
