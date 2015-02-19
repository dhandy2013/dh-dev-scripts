#!/usr/bin/python
"""
Gather statistics on the length of fully-qualified class names in a python
source tree.

Usage: ./classname_size.py top-dir-name
"""
from __future__ import print_function

import glob
import os
import re
import sys


class CodeInfo:

    def __init__(self, topdir):
        self.topdir = topdir
        self.classnames = set()

    def process_file(self, filepath, module_name):
        with open(filepath, 'r') as f:
            for line in f:
                m = re.match(r'class\s+(\w+)\s*(\(.*\))?\s*:', line)
                if m:
                    classname = m.group(1)
                    self.classnames.add(module_name + '.' + classname)

    def process(self):
        for dirpath, dirnames, filenames in os.walk(self.topdir):
            if '.git' in dirnames:
                dirnames.remove('.git')
            # Get package name for current dir based on topdir
            package_name = None
            if dirpath.startswith(self.topdir):
                package_name = dirpath[len(self.topdir):].replace('/', '.')
                package_name = package_name.lstrip('.')
            for filename in filenames:
                if not filename.endswith('.py'):
                    continue
                if package_name:
                    module_name = package_name + '.' + filename[:-3]
                else:
                    module_name = filename[:-3]
                filepath = os.path.join(dirpath, filename)
                self.process_file(filepath, module_name)

    def report_classnames(self):
        classnames = sorted(self.classnames)
        for classname in classnames:
            print(classname)

    def report_classname_size_histogram(self):
        sizes_names = sorted((len(classname), classname)
                             for classname in self.classnames)
        min_size = 2**32
        max_size = 0
        tot_size = 0
        for size, classname in sizes_names:
            if size < min_size:
                min_size = size
            if size > max_size:
                max_size = size
            tot_size += size
            print("{0} {1}".format(size, classname))
        print()
        print("min", min_size)
        if len(sizes_names) > 0:
            print("ave", float(tot_size) / len(sizes_names))
        print("max", max_size)


def classname_sizes_report(topdir):
    info = CodeInfo(topdir)
    info.process()
    info.report_classname_size_histogram()


def main():
    if len(sys.argv) < 2 or sys.argv[1].lower() in ('-h', '--help'):
        print(__doc__)
        return 1
    topdir = sys.argv[1]
    classname_sizes_report(topdir)


if __name__ == '__main__':
    sys.exit(main())
