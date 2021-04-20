#!/usr/bin/env python3
"""
Summarize the distribution of flake8 errors in a python project by folder
"""
import argparse
from collections import defaultdict
from pathlib import PurePath
import re
import sys

LINE_PATTERN = re.compile(r"(?a)(?P<src_file>.*?):\d+:\d+: (?P<err_code>\w+) .*$")


def summarize_flake8_err_distribution(infile):
    """
    infile: text file-like object contining output from flake8 command
    """

    def _create_defaultdict_int():
        return defaultdict(int)

    summary = defaultdict(_create_defaultdict_int)
    for line in infile:
        m = LINE_PATTERN.match(line)
        if m is None:
            continue
        src_file = m.group("src_file")
        err_code = m.group("err_code")
        src_path = PurePath(src_file)
        summary[src_path][err_code] += 1

    total_errors = 0
    per_file_counts = defaultdict(int)
    per_code_counts = defaultdict(int)
    per_subdir_counts = defaultdict(int)
    for src_path, err_code_counts in summary.items():
        if len(src_path.parts) == 1:
            subdir = ""
        else:
            subdir = src_path.parts[0]
        for err_code, err_count in err_code_counts.items():
            total_errors += err_count
            per_file_counts[src_path] += err_count
            per_code_counts[err_code] += err_count
            per_subdir_counts[subdir] += err_count

    top_number_to_show = 10

    worst_src_files = sorted(
        ((err_count, src_path) for src_path, err_count in per_file_counts.items()),
        reverse=True,
    )[:top_number_to_show]
    print("Top", top_number_to_show, "worst source files:")
    for err_count, src_path in worst_src_files:
        print(err_count, src_path)
    print()

    worst_err_codes = sorted(
        ((err_count, err_code) for err_code, err_count in per_code_counts.items()),
        reverse=True,
    )[:top_number_to_show]
    print("Top", top_number_to_show, "worst error codes:")
    print("https://flake8.pycqa.org/en/latest/user/error-codes.html")
    for err_count, err_code in worst_err_codes:
        print(err_count, err_code)
    print()

    worst_subdirs = sorted(
        ((err_count, subdir) for subdir, err_count in per_subdir_counts.items()),
        reverse=True,
    )[:top_number_to_show]
    print("Top", top_number_to_show, "worst subdirs:")
    for err_count, subdir in worst_subdirs:
        print(err_count, subdir)
    print()

    print("Total errors:", total_errors)
    return total_errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "flake8_output_filename",
        help="Name of file containing stdout from flake8 command",
    )
    args = parser.parse_args()

    if args.flake8_output_filename == "-":
        infile = sys.stdin
    else:
        infile = open(args.flake8_output_filename)
    try:
        summarize_flake8_err_distribution(infile)
    finally:
        if args.flake8_output_filename != "-":
            infile.close()


if __name__ == "__main__":
    main()
