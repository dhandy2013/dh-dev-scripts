#!/usr/bin/env python3
"""
Find Code

Usage:
    fc.py [options] <search-regex>

Options:
    --debug                 Print debugging info while program is running
    -m --modules            Search for the names of scripts or modules (minus
                            filename extension) instead of for items in files.
    -n --names              Search names
    -c --comments           Search comments
    -s --strings            Search string literals
    -t --text               Search text (the default, turns off -n, -c, and -s)
    -l --list-files         Only print names of files that have at least one match
    --skip-tests            Do not search in test files or directories
    --src-ext-list=SRC_EXT_LIST
                            Comma-separated list of filename extensions that
                            identify source code. [default: .c,.py,.pyx,.js]
    --include-venv          Search Python virtualenv dirs also

Searches source code in the current directory and recursively in all sub-
directories except those that:
- have names beginning with ``.``
- are named ``node_modules``
- look like Python virtual environments (unless --include-venv)
"""
from __future__ import print_function
import os
import re
import sys
import tokenize

import docopt

TOKENIZABLE_SRC_EXTS = ('.py', 'pyx')


def _is_venv_subdir(parent_dir, subdir):
    return os.path.exists(os.path.join(parent_dir, subdir, 'bin', 'python'))


def _walk_source_files(src_ext_set, skip_tests=False, debug=False,
                       include_venv=False):
    """
    For each source file under the current directory, yield (filepath, name, ext) where:
        filepath is the full source filename
        name is the base filename of filepath
        ext is the filename extension
    """
    for dirpath, dirnames, filenames in os.walk(os.curdir):
        if debug:
            print("searching directory:", dirpath, file=sys.stderr)
        # Sort sub-directories, skip names starting with '.'
        dirnames[:] = sorted(name for name in dirnames
                             if not name.startswith('.'))
        subdirs_to_skip = ["node_modules"]
        if skip_tests:
            subdirs_to_skip.extend(('test', 'tests'))
        dirnames[:] = [name for name in dirnames if not name in subdirs_to_skip]
        if not include_venv:
            dirnames[:] = [name for name in dirnames
                           if not _is_venv_subdir(dirpath, name)]
        for name in sorted(filenames):
            base, ext = os.path.splitext(name)
            if not ext in src_ext_set:
                continue
            if skip_tests:
                if base in ('test', 'tests'):
                    continue
                if base.startswith('test_'):
                    continue
            filepath = os.path.join(dirpath, name)
            yield filepath, name, ext


def search_for_src_files(src_ext_set, p, skip_tests=False, debug=False,
                         include_venv=False):
    """
    Search for source code files matching the given pattern.
    Print each matching filename, one per line.
    src_ext_set: Set of filename extensions that identify source files
    p: Regular expression compiled with re.compile()
    Return: number of matching files found
    """
    num_matches = 0
    for filepath, name, _ in _walk_source_files(src_ext_set,
                                                skip_tests=skip_tests,
                                                debug=debug,
                                                include_venv=include_venv):
        if '/' in p.pattern:
            name = filepath
        if not p.search(name):
            continue
        print(filepath)
        num_matches += 1
    return num_matches


def search_text_file(filepath, p, list_files=False):
    num_matches = 0
    with open(filepath) as f:
        for n, line in enumerate(f, 1):
            if p.search(line):
                if list_files:
                    print(filepath)
                    return 1
                print("{}:{}:{}".format(filepath, n, line.rstrip()))
                num_matches += 1
    return num_matches


def search_source_file(filepath, search_types, p, list_files=False):
    num_matches = 0
    with open(filepath) as f:
        for t in tokenize.generate_tokens(f.readline):
            tok, tokstr, (srow, scol), (erow, ecol), line = t
            if tok not in search_types:
                continue
            if p.search(tokstr):
                if list_files:
                    print(filepath)
                    return 1
                print("{}:{}:{}".format(filepath, srow, line.rstrip()))
                num_matches += 1
    return num_matches


def search_in_src_files(src_ext_set, search_types, p, skip_tests=False,
                        debug=False, include_venv=False, list_files=False):
    """
    Search for matching lines in source code files.
    Print each match found, one per line.
    src_ext_set: Set of filename extensions that identify source files
    p: Regular expression compiled with re.compile()
    Return: number of matches found
    """
    num_matches = 0
    for filepath, name, ext in _walk_source_files(src_ext_set,
                                                  skip_tests=skip_tests,
                                                  debug=debug,
                                                  include_venv=include_venv):
        if debug:
            print("searching file:", filepath, file=sys.stderr)
        if not search_types or ext not in TOKENIZABLE_SRC_EXTS:
            num_matches += search_text_file(filepath, p, list_files=list_files)
        else:
            num_matches += search_source_file(filepath, search_types, p,
                                              list_files=list_files)
    return num_matches


def main():
    args = docopt.docopt(__doc__)
    src_ext_set = set(ext.strip() for ext in args['--src-ext-list'].split(',') if ext.strip())
    p = re.compile(args['<search-regex>'])
    if args['--modules']:
        num_matches = search_for_src_files(src_ext_set, p,
                                           skip_tests=args['--skip-tests'],
                                           debug=args['--debug'],
                                           include_venv=args['--include-venv'])
    else:
        search_types = []
        if args['--names']:
            search_types.append(tokenize.NAME)
        if args['--comments']:
            search_types.append(tokenize.COMMENT)
        if args['--strings']:
            search_types.append(tokenize.STRING)
        if args['--text'] or not search_types:
            search_types = None
        num_matches = search_in_src_files(src_ext_set, search_types, p,
                                          skip_tests=args['--skip-tests'],
                                          debug=args['--debug'],
                                          include_venv=args['--include-venv'],
                                          list_files=args['--list-files'])
    if not num_matches:
        return 2
    elif num_matches == 1:
        print("One match found.", file=sys.stderr)
    else:
        print("{} matches found.".format(num_matches), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
