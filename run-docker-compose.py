#!/usr/bin/python3
"""
Convenience wrapper for running docker-compose

Unless CONFIG is an absolute file path, it is taken as relative to this script
file *after* following symbolic links.

The DH_EXTRA_OVERRIDES environment variable, if set, is treated as a comma-
separated list of docker compose override files, evaluated before the ones
specified by any -f options (and therefore taking lower precedence.) The -t
option disables this environment variable to avoid conflicting docker-compose
configuration versions (yes, this is a mess and needs cleanup as of 2020-05-06).
"""
import argparse
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-t",
        dest="run_testrunner",
        action="store_true",
        help="Start the testrunner instead of the full stack",
    )
    parser.add_argument(
        "-f",
        dest="extra_overrides",
        metavar="CONFIG",
        action="append",
        default=[],  # Ugh! I hate mutable params. But it is kind of a singleton.
        help="Extra override config file(s)",
    )
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    script_file = sys.argv[0]
    if os.path.islink(script_file):
        temp_script_file = os.readlink(script_file)
        if os.path.isabs(temp_script_file):
            script_file = temp_script_file
        else:
            script_file = os.path.join(os.path.dirname(script_file), temp_script_file)
        script_file = os.path.normpath(script_file)
    script_dir = os.path.dirname(script_file)
    override_file = "docker-compose.override.yml"

    cmd = ["docker-compose"]
    if args.run_testrunner:
        cmd.extend(["-f", "docker-compose.testing.yml"])
    else:
        cmd.extend(["-f", "docker-compose.yml"])
        if os.path.isfile(override_file):
            cmd.extend(["-f", override_file])

    # Add the "extra" docker-compose override files, if any.
    # Evaluate the environment variable first, then command-line options.
    extra_overrides = []
    if not args.run_testrunner and "DH_EXTRA_OVERRIDES" in os.environ:
        extra_overrides.extend([
            item.strip() for item in
            os.environ["DH_EXTRA_OVERRIDES"].split(",")
            if item.strip()
        ])
    extra_overrides.extend(args.extra_overrides)
    for extra_override in extra_overrides:
        if not os.path.isabs(extra_override):
            extra_override = os.path.join(script_dir, extra_override)
        cmd.extend(["-f", extra_override])
    cmd.extend(args.args)

    # Make sure COMPOSE_PROJECT_NAME is set
    # If you have a line like this in a docker-compose.yml file:
    #   image: ${COMPOSE_PROJECT_NAME:-zoom_}cr.testrunner:latest
    # then you *must* explicitly set COMPOSE_PROJECT_NAME or it will be treated
    # as empty and we won't get the default behavior of using the current
    # directory's base name as the project name. This will prevent you from
    # running testrunner on different branches of code in different directories.
    env = None
    if "COMPOSE_PROJECT_NAME" not in os.environ:
        env = os.environ.copy()
        env["COMPOSE_PROJECT_NAME"] = os.path.basename(os.getcwd()) + "_"

    if env:
        print(
            "COMPOSE_PROJECT_NAME='{}' {}".format(
                env["COMPOSE_PROJECT_NAME"], subprocess.list2cmdline(cmd)
            )
        )
    else:
        print(subprocess.list2cmdline(cmd))
    sys.stdout.flush()
    return subprocess.run(cmd, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
