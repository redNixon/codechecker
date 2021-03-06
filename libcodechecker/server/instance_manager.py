# -------------------------------------------------------------------------
#                     The CodeChecker Infrastructure
#   This file is distributed under the University of Illinois Open Source
#   License. See LICENSE.TXT for details.
# -------------------------------------------------------------------------
"""
Instance manager handles the state keeping of running CodeChecker instances
for a particular user on the local machine.
"""
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

import getpass
import json
import os
import psutil
import socket
import stat

import portalocker

from libcodechecker.util import load_json_or_empty


def __get_instance_descriptor_path(folder=None):
    if not folder:
        folder = os.path.expanduser("~")

    return os.path.join(folder, ".codechecker.instances.json")


def __make_instance_descriptor_file(folder=None):
    descriptor = __get_instance_descriptor_path(folder)
    if not os.path.exists(descriptor):
        with open(descriptor, 'w') as f:
            json.dump([], f)
        os.chmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)


def __check_instance(hostname, pid):
    """Check if the given process on the system is a valid, running CodeChecker
    for the current user."""

    # Instances running on a remote host with a filesystem shared with us can
    # not usually be checked (/proc is rarely shared across computers...),
    # so we consider them "alive" servers.
    if hostname != socket.gethostname():
        return True

    try:
        proc = psutil.Process(pid)

        return "CodeChecker.py" in proc.cmdline()[1] and \
               proc.username() == getpass.getuser()
    except psutil.NoSuchProcess:
        # If the process does not exist, it cannot be valid.
        return False


def __rewrite_instance_file(append, remove, folder=None):
    """
    This helper method reads the user's instance descriptor and manages it
    eliminating dead records, appending new ones and re-serialising the file.
    """
    __make_instance_descriptor_file(folder)

    append_pids = [i['pid'] for i in append]

    # After reading, check every instance if they are still valid and
    # make sure PID does not collide accidentally with the
    # to-be-registered instances, if any exists in the append list as it
    # would cause duplication.
    #
    # Also, we remove the records to the given PIDs, if any exists.
    instances = [i for i in get_instances(folder)
                 if i['pid'] not in append_pids and
                 (i['hostname'] + ":" + str(i['pid'])) not in remove]

    with open(__get_instance_descriptor_path(folder), 'w') as instance_file:
        portalocker.lock(instance_file, portalocker.LOCK_EX)

        instances = instances + append

        instance_file.seek(0)
        instance_file.truncate()
        json.dump(instances, instance_file, indent=2)
        portalocker.unlock(instance_file)


def register(pid, workspace, port, folder=None):
    """
    Adds the specified CodeChecker server instance to the user's instance
    descriptor.
    """

    __rewrite_instance_file([{"pid": pid,
                              "hostname": socket.gethostname(),
                              "workspace": workspace,
                              "port": port}],
                            [],
                            folder)


def unregister(pid, folder=None):
    """
    Removes the specified CodeChecker server instance from the user's instance
    descriptor.
    """

    __rewrite_instance_file([],
                            [socket.gethostname() + ":" + str(pid)],
                            folder)


def get_instances(folder=None):
    """Returns the list of running servers for the current user."""

    # This method does NOT write the descriptor file.

    descriptor = __get_instance_descriptor_path(folder)
    instances = load_json_or_empty(descriptor, {}, lock=True)

    return [i for i in instances if __check_instance(i['hostname'], i['pid'])]
