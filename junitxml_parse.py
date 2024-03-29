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


# pylint: disable=too-many-instance-attributes
class JUnitXMLHandler(xml.sax.handler.ContentHandler):
    """
    Handles "events" (XML tag start, end) for parsed junit.xml files
    """

    def __init__(self, args):
        super().__init__()
        self._show = args.show
        self._junitxml = args.junitxml
        self._strip_prefix = args.strip_prefix
        if args.add_prefix:
            self._add_prefix = args.add_prefix
        elif not os.path.isabs(args.junitxml):
            # Form path prefix relative to junit.xml file
            # Add path of junit.xml file as prefix to test files
            junitxml_dir = os.path.dirname(os.path.normpath(args.junitxml))
            if junitxml_dir:
                junitxml_dir += "/"
            self._add_prefix = junitxml_dir
        else:
            self._add_prefix = ""
        self._report_passing = args.passing
        self._report_errors = args.errors
        self._report_skips = args.skips
        #####
        self._cur_tag = ""
        self._testcase_level = 0  # 0 if outside testcase tag, 1 otherwise
        self._cur_test = None
        self._cur_status = None
        # Attributes used by report():
        self.passing_tests = []
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
        # Used only if --show / self._show is set
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
        if self._show == self._cur_test:
            self.show_text[self._cur_tag].append(content)

    def _pytest_fullname(self, test_class, test_name):
        """
        Given the `classname` and `name` attributes of a testcase XML element,
        return the full pytest test reference in the form:

            <path-to-.py-file>::<class-name>::<test-method-name>

        If the test is a module-level function and not a class method, return:

            <path-to-.py-file>::<test-function-name>

        test_class:
            For a test method, the fully-qualfied class name of the test class,
            e.g. 'tests.test_exceptions.TestTiming'
            For a test function, the full-qualified name of the test module, e.g.
            'tests.test_module'
        test_name:
            The name of the test method or function.  The method or function name may be
            followed by other parameters in square brackets.  Example:
            'test_add_integers[test_option_b]'
        """
        if test_class is not None:
            test_module_parts = test_class.split(".")[:-1]
            # Get rid of package and module in front of test class name
            test_class_name = test_class.rpartition(".")[-1]
        else:
            test_module_parts = []
            test_class_name = ""

        # This is not a 100% accurate way to distinguish a test function from a test
        # method, because pytest can be configured to look for test class names not
        # beginning with "Test". But such non-standard test class names should be
        # discouraged anyway.
        if test_class_name and not test_class_name.startswith("Test"):
            # test_class_name doesn't look like a test class name.
            # Treat it as a test module name.
            test_module_parts.append(test_class_name)
            test_class_name = ""

        path_to_py_file = "/".join(test_module_parts) + ".py"
        if self._strip_prefix and path_to_py_file.startswith(self._strip_prefix):
            path_to_py_file = path_to_py_file[len(self._strip_prefix) :]  # noqa: E203
        path_to_py_file = f"{self._add_prefix}{path_to_py_file}"
        if test_class_name:
            return f"{path_to_py_file}::{test_class_name}::{test_name}"
        return f"{path_to_py_file}::{test_name}"

    def _start_testsuites(self, attrs):
        pass

    def _start_testsuite(self, attrs):
        name = attrs.get("name")
        if name != "pytest":
            print(
                f'WARNING: Testsuite has name {name!r} instead of expected "pytest"',
                file=sys.stderr,
            )
        self.expected_num_errors = int(attrs["errors"])
        self.expected_num_failures = int(attrs["failures"])
        self.expected_num_tests = int(attrs["tests"])
        self.total_time_sec = float(attrs["time"])
        # DH 2024-02-12 junit format changed? skips -> skipped
        expected_num_skips_str = attrs.get("skips")
        if expected_num_skips_str is None:
            expected_num_skips_str = attrs["skipped"]
        self.expected_num_skips = int(expected_num_skips_str)  # skips plus xfails

    def _start_testcase(self, attrs):
        self._testcase_level += 1
        assert self._testcase_level == 1  # No nested <testcase> tags!
        self.num_testcases += 1
        test_name = attrs.get("name")
        if test_name:
            test_class = attrs["classname"]
            self._cur_test = self._pytest_fullname(test_class, test_name)
        else:
            # Mangled <testcase> element, happens when pressing Ctrl-C during test run
            self._cur_test = None
        self._cur_status = None
        if self._show == self._cur_test:
            for attr_name in sorted(attrs.keys()):
                self.show_attrs[attr_name] = attrs[attr_name]

    def _end_testcase(self):
        self._testcase_level -= 1
        if self._cur_status:
            self.nonpassing_tests[self._cur_status].append(self._cur_test)
        else:
            self.passing_tests.append(self._cur_test)
        self._cur_test = None
        self._cur_status = None

    def _start_error(self, _attrs):
        assert self._testcase_level == 1
        self.num_errors += 1
        self._cur_status = "ERROR"

    def _start_failure(self, _attrs):
        assert self._testcase_level == 1
        self.num_failures += 1
        self._cur_status = "FAIL"

    def _start_skipped(self, _attrs):
        assert self._testcase_level == 1
        self.num_skips += 1
        self._cur_status = "SKIP"

    def _start_system_out(self, _attrs):
        assert self._testcase_level == 1

    def _start_system_err(self, _attrs):
        assert self._testcase_level == 1

    def report(self):
        """
        Print report on junit.xml file contents
        """
        if self._show:
            print(f"Details for test: {self._show}")
            for attr_name, attr_val in self.show_attrs.items():
                print(f"  {attr_name}: {attr_val}")
            for tag_name, text_chunks in self.show_text.items():
                print(f"{tag_name}:")
                print("".join(text_chunks))
        else:
            print(f"Report on JUnit XML file {self._junitxml}:")
            print("Stats from the <testsuites> tag:")
            expected_num_errors = self.expected_num_errors + self.expected_num_failures
            print(f"{expected_num_errors} errors (errors + failures)")
            print(f"{self.expected_num_skips} skips (skips + xfails)")
            print(f"{self.expected_num_tests} tests total.")
            print()
            print("Stats from the body of the report:")
            num_errors = self.num_errors + self.num_failures
            print(f"Number of errors: {num_errors} (errors + failures)")
            print(f"Number of skips (skips + xfails): {self.num_skips}")
            print(f"Number of <testcase> tags: {self.num_testcases}")
            print()
            print(f"Total test suite run time: {self.total_time_sec} seconds")
        if self.unhandled_tags:
            print()
            print("Unhandled tags:", sorted(self.unhandled_tags))
        if self._report_passing:
            print()
            print(f"{len(self.passing_tests)} passing tests:")
            for test_fullname in sorted(self.passing_tests):
                print(test_fullname)
        if self._report_skips:
            print()
            test_list = self.nonpassing_tests["SKIP"]
            print(f"{len(test_list)} tests with status SKIP:")
            for test_fullname in sorted(test_list):
                print(test_fullname)
        if self._report_errors:
            print()
            failed_tests = self.nonpassing_tests["ERROR"].copy()
            failed_tests.extend(self.nonpassing_tests["FAIL"])
            failed_tests.sort()
            print(f"{len(failed_tests)} tests with status ERROR or FAIL:")
            for test_fullname in failed_tests:
                print(test_fullname)


# pylint: disable=missing-function-docstring
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
        "--passing", action="store_true", help="Report passing tests",
    )
    parser.add_argument(
        "--strip-prefix",
        default="/code/",
        help="Filename prefix to remove if it is there. Default: /code/",
    )
    parser.add_argument(
        "--add-prefix",
        default="",
        help=(
            "Prefix to add to path to .py file for printing test names"
            " (after processing --strip-prefix.)"
            " Default: use path to directory containing JUnit XML file"
            " if it is not an absolute path, otherwise use empty string."
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
