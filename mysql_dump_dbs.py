#!/usr/bin/env python3
"""
Dump MySQL databases, specifying database names with using glob patterns.

Usage:
    mysql_dump_dbs.py [options] <db-name-pattern> ...

Options:
    --host=HOST             MySQL server host
    --port=PORT             MySQL server port
    --user=USER             MySQL user
    --password=PASSWORD     MySQL password to use
    --result-file=FILENAME  Output file name

Example:
    # Dump all databases whose names begin with "abc"
    # Note: Remember to put quote marks around names containing "*", etc.
    mysql_dump_dbs.py --user=$MYSQL_USER --password="$MYSQL_PASSWORD" "abc*"

Note:
    The databases are dumped in text format to standard output.
    To save the output, redirect to a file using "> filename.dump"
"""

from collections import OrderedDict
import fnmatch
import os
import subprocess
import sys

import docopt

common_mysql_passthru_opts = (
    '--host', '--port', '--user', '--password')

mysqldump_passthru_opts = ('--result-file',)


class CommandLine:

    def __init__(self, cmd, extra_env=None):
        self.cmd = cmd[:]
        self.visible_cmd = self.cmd[:]
        self.extra_env = extra_env.copy() if extra_env else {}

    def add_opts(self, args, optnames):
        for optname in optnames:
            if optname not in args:
                continue
            arg = args[optname]
            if not arg:
                continue
            if optname == '--password':
                self.extra_env['MYSQL_PWD'] = arg
            else:
                item = "{}={}".format(optname, arg)
                self.cmd.append(item)
                self.visible_cmd.append(item)

    def add_args(self, args):
        self.cmd.extend(args)
        self.visible_cmd.extend(args)

    def __str__(self):
        return subprocess.list2cmdline(self.visible_cmd)

    def _prep_env(self):
        env = None
        if self.extra_env:
            env = os.environ.copy()
            env.update(self.extra_env)
        return env

    def check_call(self):
        subprocess.check_call(self.cmd, env=self._prep_env())

    def check_output(self):
        return subprocess.check_output(self.cmd, env=self._prep_env())


def main():
    args = docopt.docopt(__doc__)
    list_cmd = CommandLine(['mysql', '--silent', '--raw',
                            '-e', 'show databases'])
    list_cmd.add_opts(args, common_mysql_passthru_opts)
    output = list_cmd.check_output()
    db_names = output.split()
    db_dict = OrderedDict()  # ordered set: {db_name: True}
    for db_name_pattern in args['<db-name-pattern>']:
        for db_name_bytes in db_names:
            db_name = db_name_bytes.decode('utf-8')
            if fnmatch.fnmatchcase(db_name, db_name_pattern):
                db_dict[db_name] = True
    final_db_names = list(db_dict)
    if not final_db_names:
        print("Error: No matching databases.", file=sys.stderr)
        return 1
    dump_cmd = CommandLine(['mysqldump',
        '--add-drop-table',
        '--create-options',
        '--databases'])
    dump_cmd.add_opts(args, common_mysql_passthru_opts)
    dump_cmd.add_opts(args, mysqldump_passthru_opts)
    dump_cmd.add_args(final_db_names)
    dump_cmd.check_call()


if __name__ == '__main__':
    sys.exit(main())
