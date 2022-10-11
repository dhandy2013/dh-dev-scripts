#!/usr/bin/env python3
"""
Remove __pycache__ directories, .pyc/.pyo and cython artifacts

Remove these even if they are owned by user root.

Q. Why do you have .pyc files and other Python artifacts owned by root?
A. A certain docker container mounts the source directory as an external volume
   but then builds and installs the code as user root, creating a bunch of
   artifacts that are owned by root. The docker image should obviously be
   fixed, but it isn't controlled by me so it will take time to make that
   happen. In the mean time this script is a workaround to some problems.
"""
import argparse
import fnmatch
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
        help="Directories to recursively search for "
        ".pyc/.pyo and __pycache__ files and dirs",
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
    parser.add_argument(
        "--skip",
        action="append",
        default=[],  # Mutable default object, Ok in this limited case
        help="Glob pattern of sub-directory names to not process. "
        "You can specify this multiple times.",
    )
    parser.add_argument(
        "--also-venv",
        action="store_true",
        help="Also recurse into virtual environments (marked by pyvenv.cfg)",
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
    pycache_dirs_to_delete = []
    for dirpath_str, dirnames, filenames in os.walk(directory):
        dirpath = Path(dirpath_str)
        # Clean up Python built artifacts
        items_to_delete = []
        compiled_python_modules = []
        for filename in filenames:
            item = dirpath / filename
            if item.suffix in (".pyc", ".pyo"):
                items_to_delete.append(item)
                continue
            # Check for Cython artifacts. Examples:
            # common.c
            # common.cpython-36m-x86_64-linux-gnu.so
            # common.html
            # common.py <- This is the Cython source file, could also be .pyx
            if item.suffix == ".so" and item.suffixes[0].startswith(".cpython-"):
                # Compiled Python extension
                compiled_python_modules.append(item.stem)
                items_to_delete.append(item)
                continue

        # Clean up Cython built artifacts in addition to the .so file
        for module_name in compiled_python_modules:
            for ext in (".c", ".html"):
                item = dirpath / (module_name + ext)
                if item.exists():
                    items_to_delete.append(item)

        # Delete the files that should be deleted
        for item in items_to_delete:
            if args.only_root and item.owner() != "root":
                continue
            if not args.quiet:
                print(item)
            if args.for_real:
                item.unlink()

        # Clean up Python cache directories
        for dirname in list(dirnames):
            if any(fnmatch.fnmatch(dirname, pattern) for pattern in args.skip):
                dirnames.remove(dirname)
                continue
            item = Path(dirpath, dirname)
            if not args.also_venv and Path(item, "pyvenv.cfg").exists():
                # Skip virtual environment directory
                dirnames.remove(dirname)
                continue
            if item.name != "__pycache__":
                continue
            if args.only_root and item.owner() != "root":
                continue
            if not args.quiet:
                print(item)
            if args.for_real:
                pycache_dirs_to_delete.append(item)

    if args.for_real:
        for item in pycache_dirs_to_delete:
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
