#!/usr/bin/env python
"""
Script that starts the SSH agent for a connection based on the domain.
If the agent is already running, it won't start another.

Put something like this in your ~/.ssh/config file:

    Match exec ~/bin/start_ssh_agent_by_domain.py --domain=mydomain.com \\
            --control=~/.ssh/agent-mydomain-%l.txt \\
            --identities-dir=~/.ssh/identities/mydomain/ \\
            --socket=/tmp/ssh-%u-mydomain/agent.sock %h
    IdentityAgent /tmp/ssh-%u-mydomain/agent.sock

Every time ssh reads the client config file, it will run this script and
determine if you are trying to connect to mydomain.com or a host in that domain
(e.g. myhost.mydomain.com). If the domain matches, then this script looks for
the control file, and if it exists, reads the agent process ID from that file
and checks if the agent is still running. It will start the agent and create
the control file as necessary. This script will return with exit code 0 if the
domain matched and the agent is running, 1 otherwise.

When this script returns with exit code 0, then ssh will use the next config
line to override the SSH_AUTH_SOCK environment variable (if set) and use the
agent identified by the socket name. This allows you to have a separate agent
for that domain containing only the keys in identities-dir.
"""
from __future__ import print_function
import argparse
import os
import re
import subprocess
import sys


def _read_control_file(filename):
    """
    Example control file contents:

    SSH_AUTH_SOCK=/tmp/ssh-test/agent.sock; export SSH_AUTH_SOCK;
    echo Agent pid 10380;

    Return {'SSH_AUTH_SOCK': <sockfile>, 'SSH_AGENT_PID': <pid>}
    """
    result = {}
    with open(filename) as f:
        for line in f:
            m = re.match(r"SSH_AUTH_SOCK=(.*?);", line)
            if m:
                result['SSH_AUTH_SOCK'] = m.group(1)
                continue
            m = re.match(r"echo Agent pid (\d+);", line)
            if m:
                result['SSH_AGENT_PID'] = m.group(1)
                continue
    for key in ('SSH_AUTH_SOCK', 'SSH_AGENT_PID'):
        if key not in result:
            raise ValueError('Invalid control file "{}": Missing key {}'
                             .format(filename, key))
    return result


def _check_if_agent_running(env, desired_sock):
    # Return True iff the agent is running and we can use it.
    # Raise an exception if it looks like we can't start the agent because of a
    # resource conflict of some kind, or the agent is running but we can't use
    # it.
    # Return False if the agent is not running but we can start it.
    agent_sock = env['SSH_AUTH_SOCK']
    agent_pid = env['SSH_AGENT_PID']
    agent_sock_exists = os.path.exists(agent_sock)
    with open(os.devnull, 'wb') as null:
        rc = subprocess.call(['ps', '-p', agent_pid],
                             stdout=null, stderr=subprocess.STDOUT)
    agent_proc_exists = (rc == 0)
    desired_sock_exists = os.path.exists(desired_sock)
    if (desired_sock_exists
            and desired_sock == agent_sock
            and agent_proc_exists):
        return True
    if agent_proc_exists and agent_sock_exists:
        raise RuntimeError("Some other agent is using the control file.")
    if desired_sock_exists:
        raise RuntimeError("Some other agent is using the socket file.")
    return False


def _parse_key_fingerprint(line):
    parts = line.split()
    if len(parts) < 2:
        return None
    try:
        key_size = int(parts[0])
    except ValueError:
        return None
    return (key_size, parts[1])


def _get_key_fingerprint(key_path):
    """
    Return (key_size, key_hash), or None if there was an error.
    """
    cmd = ['ssh-keygen', '-l', '-E', 'md5', '-f', key_path]
    with open(os.devnull, 'wb') as null:
        try:
            out = subprocess.check_output(cmd, stderr=null)
        except subprocess.CalledProcessError:
            return None
    return _parse_key_fingerprint(out)


def _scan_identities_dir(identities_dir):
    """
    Scan the identity files found in identities_dir.
    Any file with a matching .pub file is assumed to be a private key.
    Return {key_path: fingerprint}
    """
    file_set = set(os.listdir(identities_dir))
    identity_map = {}
    for filename in sorted(file_set):
        if filename.endswith('.pub'):
            key_file = filename[:-4]
            if key_file in file_set:
                key_path = os.path.join(identities_dir, key_file)
                fingerprint = _get_key_fingerprint(key_path)
                if fingerprint:
                    identity_map[key_path] = fingerprint
    return identity_map


def _list_agent_keys(agent_sock):
    """
    Return a list of key fingerprints current loaded in the agent.
    """
    cmd = ['ssh-add', '-l', '-E', 'md5']
    env = os.environ.copy()
    env['SSH_AUTH_SOCK'] = agent_sock
    with open(os.devnull, 'wb') as null:
        try:
            out = subprocess.check_output(cmd, stderr=null, env=env)
        except subprocess.CalledProcessError:
            return []
    result = []
    for line in out.split(b'\n'):
        fingerprint = _parse_key_fingerprint(line)
        if not fingerprint:
            continue
        result.append(fingerprint)
    return result


def _start_agent(args):
    if os.path.exists(args.socket):
        raise RuntimeError("Agent socket already exists: {}"
                           .format(args.socket))
    cmd = ['ssh-agent', '-s', '-a', args.socket]
    with open(args.control, 'wb') as f:
        subprocess.check_call(cmd, stdout=f)
    # If we reach this point the agent should be running.
    # Load all keys into the agent that haven't already been loaded
    current_key_set = set(_list_agent_keys(args.socket))
    identity_map = _scan_identities_dir(args.identities_dir)
    key_paths_to_add = [i[0] for i in identity_map.items()
                        if i[1] not in current_key_set]
    if key_paths_to_add:
        cmd = ['ssh-add', '-q']
        cmd.extend(key_paths_to_add)
        env = os.environ.copy()
        env['SSH_AUTH_SOCK'] = agent_sock
        subprocess.check_call(cmd, env=env)


def _ensure_agent_running_and_keys_loaded(args):
    try:
        s = os.stat(args.control)
        non_empty_file_exists = (s.st_size > 0)
    except OSError:  # assuming file not found
        non_empty_file_exists = False
    if non_empty_file_exists:
        env = _read_control_file(args.control)
        if not _check_if_agent_running(env, args.socket):
            _start_agent(args)
    else:
        _start_agent(args)


def start_ssh_agent_by_domain(args):
    host_parts = args.hostname.lower().split('.')
    domain_parts = args.domain.lower().split('.')
    if host_parts[-len(domain_parts):] != domain_parts:
        # Domain doesn't match
        return 1
    _ensure_agent_running_and_keys_loaded(args)
    return 0


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--domain', help="Domain name to match")
    parser.add_argument('--control', help="Agent control file")
    parser.add_argument('--identities-dir',
                        help="Directory containing private and public keys")
    parser.add_argument('--socket', help="Agent unix-domain socket")
    parser.add_argument('hostname', metavar='<hostname>',
                        help="SSH destination host name")
    args = parser.parse_args()
    if not args.domain:
        print("Missing --domain argument", file=sys.stderr)
        return 1
    if not args.control:
        print("Missing --control argument", file=sys.stderr)
        return 1
    args.control = os.path.expanduser(args.control)
    if not args.socket:
        print("Missing --socket argument", file=sys.stderr)
        return 1
    if not args.identities_dir:
        print("Missing --identities-dir argument", file=sys.stderr)
        return 1
    args.identities_dir = os.path.expanduser(args.identities_dir)
    if not os.path.isdir(args.identities_dir):
        print("identities-dir does not exist:", args.identities_dir)
        return 1
    return start_ssh_agent_by_domain(args)


if __name__ == '__main__':
    sys.exit(main())
