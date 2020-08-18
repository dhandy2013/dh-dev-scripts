#!/usr/bin/env python3
"""
Parse a JUnit XML format test output file and print useful info
"""
import argparse
from collections import defaultdict
import os
import sys
import xml.sax
import xml.sax.handler


class JUnitXMLHandler(xml.sax.handler.ContentHandler):
    def __init__(self, args):
        self._args = args
        self._cur_tag = ""
        self._testcase_level = 0  # 0 if outside testcase tag, 1 otherwise
        self._cur_test = None
        self._cur_status = None
        # Form path prefix relative to junit.xml file
        junitxml = self._args.junitxml
        if not os.path.isabs(junitxml) and not self._args.add_prefix:
            # Add path of junit.xml file as prefix to test files
            self._args.add_prefix = os.path.dirname(os.path.normpath(junitxml)) + "/"
        # Attributes used by report():
        self.nonpassing_tests = defaultdict(list)  # {status: test_list}
        self.unhandled_tags = set()
        self.expected_num_errors = None
        self.expected_num_failures = None
        self.expected_num_skips = None
        self.expected_num_tests = None
        self.total_time_sec = None
        self.num_testcases = 0
        self.num_errors = 0
        self.num_failures = 0
        self.num_skips = 0
        # Used only if --show / self._args.show is set
        self.show_attrs = {}  # {attr_name: attr_val}
        self.show_text = defaultdict(list)  # {tag: text_chunk_list}

    def startElement(self, name, attrs):
        self._cur_tag = name
        method_name = f"_start_{name}".replace("-", "_")
        method = getattr(self, method_name, None)
        if method:
            method(attrs)
        else:
            self.unhandled_tags.add(name)

    def endElement(self, name):
        method_name = f"_end_{name}".replace("-", "-")
        method = getattr(self, method_name, None)
        if method:
            method()

    def characters(self, content):
        if self._testcase_level != 1 or self._cur_tag == "testcase" or not content:
            return
        if self._args.show == self._cur_test:
            self.show_text[self._cur_tag].append(content)

    def _pytest_fullname(self, test_file, test_class, test_name):
        test_path = self._pytest_testpath(test_file, test_class)
        if test_class:
            test_path_parts = os.path.splitext(test_file)[0].split("/")
            if test_path_parts == test_class.split("."):
                # It is a test function not a test method, get rid of class name
                test_class = ""
            else:
                # Get rid of package and module in front of test class name
                test_class = test_class.rpartition(".")[-1]
        if self._args.strip_prefix and test_path.startswith(self._args.strip_prefix):
            test_path = test_path[len(self._args.strip_prefix) :]  # noqa: E203
        if self._args.add_prefix and not test_path.startswith(self._args.add_prefix):
            test_path = f"{self._args.add_prefix}{test_path}"
        if test_class:
            return f"{test_path}::{test_class}::{test_name}"
        else:
            return f"{test_path}::{test_name}"

    def _pytest_testpath(self, test_file, test_class):
        test_basename = os.path.basename(test_file)
        if test_basename.startswith("test_"):
            # If it looks like a test file name then use the JUnit file attribute
            return test_file
        # Otherwise, turn the full test class name into a file name
        return "/".join(test_class.split(".")) + ".py"

    def _start_testsuite(self, attrs):
        name = attrs.get("name")
        if name != "pytest":
            print(
                f'WARNING: Testsuite has name {name!r} instead of expected "pytest"',
                file=sys.stderr,
            )
        self.expected_num_errors = int(attrs["errors"])
        self.expected_num_failures = int(attrs["failures"])
        self.expected_num_skips = int(attrs["skips"])  # skips plus xfails
        self.expected_num_tests = int(attrs["tests"])
        self.total_time_sec = float(attrs["time"])

    def _start_testcase(self, attrs):
        self._testcase_level += 1
        assert self._testcase_level == 1  # No nested <testcase> tags!
        self.num_testcases += 1
        test_name = attrs.get("name")
        if test_name:
            test_class = attrs["classname"]
            test_file = attrs["file"]
            self._cur_test = self._pytest_fullname(test_file, test_class, test_name)
        else:
            # Mangled <testcase> element, happens when pressing Ctrl-C during test run
            self._cur_test = None
        self._cur_status = None
        if self._args.show == self._cur_test:
            for attr_name in sorted(attrs.keys()):
                self.show_attrs[attr_name] = attrs[attr_name]

    def _end_testcase(self):
        self._testcase_level -= 1
        if self._cur_status:
            self.nonpassing_tests[self._cur_status].append(self._cur_test)
        self._cur_test = None
        self._cur_status = None

    def _start_error(self, attrs):
        assert self._testcase_level == 1
        self.num_errors += 1
        self._cur_status = "ERROR"

    def _start_failure(self, attrs):
        assert self._testcase_level == 1
        self.num_failures += 1
        self._cur_status = "FAIL"

    def _start_skipped(self, attrs):
        assert self._testcase_level == 1
        self.num_skips += 1
        self._cur_status = "SKIP"

    def _start_system_out(self, attrs):
        assert self._testcase_level == 1

    def _start_system_err(self, attrs):
        assert self._testcase_level == 1

    def report(self):
        if self._args.show:
            print(f"Details for test: {self._args.show}")
            for attr_name, attr_val in self.show_attrs.items():
                print(f"  {attr_name}: {attr_val}")
            for tag_name, text_chunks in self.show_text.items():
                print(f"{tag_name}:")
                print("".join(text_chunks))
        else:
            print(f"Report on JUnit XML file {self._args.junitxml}:")
            print("Stats from the <testsuites> tag:")
            print(f"{self.expected_num_errors} errors")
            print(f"{self.expected_num_failures} failures")
            print(f"{self.expected_num_skips} skips (skips + xfails)")
            print(f"{self.expected_num_tests} tests total.")
            print()
            print("Stats from the body of the report:")
            print(f"Number of errors: {self.num_errors}")
            print(f"Number of failures: {self.num_failures}")
            print(f"Number of skips (skips + xfails): {self.num_skips}")
            print(f"Number of <testcase> tags: {self.num_testcases}")
            print()
            print(f"Total test suite run time: {self.total_time_sec} seconds")
        if self.unhandled_tags:
            print()
            print("Unhandled tags:", sorted(self.unhandled_tags))
        if self._args.errors:
            print()
            failed_tests = self.nonpassing_tests["ERROR"].copy()
            failed_tests.extend(self.nonpassing_tests["FAIL"])
            failed_tests.sort()
            print(f"{len(failed_tests)} tests with status ERROR or FAIL:")
            for test_fullname in failed_tests:
                print(test_fullname)
        if self._args.skips:
            print()
            self.report_status("SKIP")

    def report_status(self, status):
        test_list = self.nonpassing_tests[status]
        print(f"{len(test_list)} tests with status {status}:")
        for test_fullname in test_list:
            print(test_fullname)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("junitxml", help="Name of JUnit XML file")
    parser.add_argument(
        "--errors", action="store_true", help="Report errors and failures"
    )
    parser.add_argument(
        "--skips", action="store_true", help="Report skipped and xfailed tests"
    )
    parser.add_argument(
        "--strip-prefix",
        default="/code/",
        help="Filename prefix to remove if it is there",
    )
    parser.add_argument(
        "--add-prefix",
        default="",
        help=(
            "Filename prefix to add if it is not already there"
            " (after processing --strip-prefix)"
        ),
    )
    parser.add_argument(
        "--show", metavar="TEST-NAME", help="Show details for a particular testcase"
    )
    args = parser.parse_args()
    handler = JUnitXMLHandler(args)
    xml.sax.parse(args.junitxml, handler)
    handler.report()


if __name__ == "__main__":
    sys.exit(main())
