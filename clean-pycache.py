#!/usr/bin/env python3
"""
Remove __pycache__ directories and .pyc/.pyo files

Q. Why not use pyclean? https://github.com/bittner/pyclean
A. Try this and you will find out::

    pip install --user pyclean
    sudo pyclean --dry-run .

- On Ubuntu linux an old /usr/bin/pyclean script will get run instead
- If you work around that problem, pyclean will fail with an ImportError
  because when running as root your ~/.local/lib/python3.x/site-packages/
  directory is not in PYTHONPATH so the pyclean package won't be found.

Q. Why do you need to run cleanup as user root?
A. Because someone else's Docker setup script that I need to run unnecessarily
   compiles a bunch of .py files into .pyc files as user root in a volume
   containing my source code.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "directory",
        nargs="+",
        help="Directories to search for __pycache__ and .pyc/.pyo",
    )
    parser.add_argument(
        "--for-real",
        action="store_true",
        help="Actually delete files and directories instead of printing",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Do not print the __pycache__ and .pyc/.pyo directories and files",
    )
    parser.add_argument(
        "--sudo",
        action="store_true",
        help="Restart this script as user root via sudo",
    )
    args = parser.parse_args()

    # Only run sudo if we are not already effectively root
    if args.sudo and os.geteuid() != 0:
        argv = list(sys.argv)
        # *Must* remove --sudo from argv to avoid infinite spawn loop!
        argv.remove("--sudo")
        # Make sure we execute in *this* current directory, not root home dir.
        cwd = os.getcwd()
        # Adding -B to Python options to avoid the irony of creating .pyc files
        # as user root when that is the very problem this script mitigates.
        cmd = ["sudo", sys.executable, "-B"] + argv
        print(subprocess.list2cmdline(cmd))
        return subprocess.run(cmd, cwd=cwd).returncode

    for directory in args.directory:
        _recursive_clean(args, Path(directory))


def _recursive_clean(args, directory: Path):
    for item in directory.iterdir():
        if item.is_file():
            if item.suffix in (".pyc", ".pyo"):
                if not args.quiet:
                    print(item)
                if args.for_real:
                    item.unlink()
        elif item.is_dir():
            _recursive_clean(args, item)
            if item.name == "__pycache__":
                if not args.quiet:
                    print(item)
                if args.for_real:
                    item.rmdir()


if __name__ == "__main__":
    sys.exit(main())
