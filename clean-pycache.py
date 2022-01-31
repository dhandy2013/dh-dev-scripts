#!/usr/bin/env python3
"""
Remove __pycache__ directories and .pyc/.pyo files even if owned by root

Q. Why not use pyclean? https://github.com/bittner/pyclean
A. Try this and you will find out::

    pip install --user pyclean
    sudo pyclean --dry-run .

- On Ubuntu linux an old /usr/bin/pyclean script will get run instead
- If you work around that problem by specifying the full path to the pyclean
  script that you want, pyclean will fail with an ImportError because when
  running as root your ~/.local/lib/python3.x/site-packages/ directory is not
  in PYTHONPATH so the pyclean package won't be found.

Q. Why do you need to run cleanup as user root?
A. I run a certain docker container that mounts my source code directory as an
   external volume. That docker container (that I do not control) unfortunately
   compiles .py files in my source tree into .pyc files owned by user root.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "directory",
        nargs="+",
        help="Directories to search for .pyc/.pyo and __pycache__ files and dirs",
    )
    parser.add_argument(
        "--for-real",
        action="store_true",
        help="Actually delete files and directories instead of printing",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Do not print .pyc/.pyo and __pycache__ files and dirs",
    )
    parser.add_argument(
        "--sudo", action="store_true", help="Restart this script as user root via sudo",
    )
    parser.add_argument(
        "--only-root",
        action="store_true",
        help="Only print/delete .pyc/.pyo and __pycache__ files and dirs owned by root",
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
        print(subprocess.list2cmdline(cmd), file=sys.stderr)
        return subprocess.run(cmd, cwd=cwd).returncode

    for directory in args.directory:
        clean_pycache(args, Path(directory))

    if not args.for_real:
        print(
            "Dry run, nothing was changed. To remove files/dirs pass --for-real",
            file=sys.stderr,
        )


def clean_pycache(args, directory: Path):
    # topdown=False means subdirectories' contents are visited before their parent
    # directories are. So by the time this function sees a __pycache__ directory, its
    # contents should have been deleted (if args.for_real is true).
    for dirpath, dirnames, filenames in os.walk(directory, topdown=False):
        for item in filenames:
            item = Path(dirpath, item)
            if item.suffix not in (".pyc", ".pyo"):
                continue
            if args.only_root and item.owner() != "root":
                continue
            if not args.quiet:
                print(item)
            if args.for_real:
                item.unlink()
        for item in dirnames:
            item = Path(dirpath, item)
            if item.name != "__pycache__":
                continue
            if args.only_root and item.owner() != "root":
                continue
            if not args.quiet:
                print(item)
            if args.for_real:
                # rmdir() could fail if:
                # - A __pycache__ directory contains contents other than .pyc/.pyo files
                #   (which should never happen)
                # - We are only deleting items owned by root, and the __pycache__
                #   directory is owned by root but contains at least one .pyc/.pyo file
                #   *not* owned by root, and therefore not deleted earlier.
                # Either way, print the exception to stderr and keep on going.
                try:
                    item.rmdir()
                except Exception as exc:
                    print(exc, file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
