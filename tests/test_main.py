"""
The tests are meant to test:
    1. Whether we can mount with existing files in the mounting folder and the
        files are preserved.
    2. Whether we can handle a dropped connection:
        a. Can we reconnect?
        b. Is there an error when we can not?
    3. Whether we can successfully monitor an actively mounted directory.
    4. Whether we can mount / remount
    5. Bad input, e.g. configuration
    6. Interrupted uploads
"""
import logging
import multiprocessing
import os
import random
import shutil
import time
from pathlib import Path

import pytest

from rmount import RemoteMount, main
from rmount.utils import unmount

main.HEARTBEAT_ERROR_COUNT = 2
main.MISSED_HEARTBEATS_ERROR = 2


logger = logging.getLogger("RMount")
logger.setLevel(logging.INFO)

if os.name != "posix":
    raise NotImplementedError("Unsupported OS.")


def write_bytes(tmp_file: Path):
    tmp_file.parent.mkdir(exist_ok=True)
    _bytes = os.urandom(1024 * 10)
    tmp_file.write_bytes(_bytes)
    return _bytes


def _assert_with_timeout(fn):
    for i in range(10):
        try:
            assert fn()
            return True
        except Exception:
            pass
        time.sleep(1)
    assert False


def test_mount_remount(rmount: RemoteMount, remote_server: "RemoteServer"):
    local_path = rmount.local_path
    remote_path = rmount.remote_path
    lfile = local_path.joinpath("local.txt")
    rfile = remote_path.joinpath("remote.txt")
    remote_bytes = write_bytes(rfile)
    local_bytes = write_bytes(lfile)
    _assert_with_timeout(
        lambda: remote_path.joinpath("local.txt").read_bytes() == local_bytes
    )
    _assert_with_timeout(
        lambda: local_path.joinpath("remote.txt").read_bytes() == remote_bytes
    )

    rmount.unmount()
    assert len(list(local_path.glob("*"))) == 0
    # Test mounting on an existing directory.
    p = local_path.joinpath("test.txt")
    test_bytes = write_bytes(p)

    rmount.mount()
    _assert_with_timeout(
        lambda: local_path.joinpath("local.txt").read_bytes() == local_bytes
    )
    _assert_with_timeout(
        lambda: local_path.joinpath("remote.txt").read_bytes() == remote_bytes
    )
    # test that the existing file "test.txt" is no longer accessible
    _assert_with_timeout(lambda: not p.exists())
    # test that it remains preserved after unmounting
    rmount.unmount()
    _assert_with_timeout(lambda: p.read_bytes() == test_bytes)


def test_reconnection(rmount: RemoteMount, remote_server: "RemoteServer"):
    assert rmount.is_alive()
    remote_server.kill()
    assert not rmount.is_alive(timeout=5)
    remote_server.start()
    for i in range(10):
        if rmount.is_alive(timeout=5):
            break
        time.sleep(1)
    assert rmount.is_alive()


def test_connection_drop(rmount: RemoteMount, remote_server: "RemoteServer"):
    rmount.unmount()
    remote_server.kill()
    is_alive = multiprocessing.Event()
    is_alive.clear()

    def _run_error(is_alive):
        remote_server.start()
        rmount.mount()
        assert rmount.is_alive()
        remote_server.kill()
        assert not rmount.is_alive(timeout=5)
        for i in range(120):
            time.sleep(1)
        is_alive.set()
        return

    p = multiprocessing.Process(target=_run_error, args=(is_alive,))
    p.start()
    while p.is_alive() and not is_alive.is_set():
        p.join(1)
    assert not is_alive.is_set()


def test_no_remote(rmount: RemoteMount, remote_server: "RemoteServer"):
    rmount.unmount()
    remote_server.kill()
    with pytest.raises(AssertionError, match="Could not mount on time."):
        rmount.mount()


def test_context(rmount: RemoteMount, remote_server: "RemoteServer"):
    with rmount:
        assert rmount.is_alive()
    assert not rmount.is_alive()


def test_interupt_upload(rmount: RemoteMount, remote_server: "RemoteServer"):
    def delayed_unmount():
        time.sleep(10)
        rmount.unmount()

    slow_kill = multiprocessing.Process(target=delayed_unmount)
    slow_kill.start()
    n_files = 10
    n_numbers = 10_000_000
    # should be around 100MB of files
    while slow_kill.is_alive():
        name = f"{random.randint(0,n_files):02d}"
        rmount.local_path.joinpath(name).write_bytes(
            bytes(random.randint(n_numbers - 1, n_numbers * 10))
        )
    ints_1 = [
        rmount.local_path.joinpath(f"{i:02d}").read_bytes() for i in range(n_files)
    ]

    def files_equal():
        time.sleep(2)
        ints_2 = [
            rmount.remote_path.joinpath(f"{i:02d}").read_bytes() for i in range(n_files)
        ]
        return all(ints_1[i] == ints_2[i] for i in range(10)) and all(
            ints_2[0] != ints_2[i] for i in range(1, 10)
        )

    _assert_with_timeout(files_equal)


if __name__ == "__main__":
    from tests.conftest import RemoteServer, _config, _remote_server, _rmount

    """
    # NOTE to test the connection to the mock server use:
    $ ssh -p 2222 -i /tmp/rmount/test/id_rsa -o StrictHostKeyChecking=no \
          admin@localhost

    # NOTE To test whether you can mount e.g. there are no RemoteServer errors:
    $ sudo apt-get install sshfs
    $ sshfs -o default_permissions -o ssh_command='ssh -p 2222 -i \
        /tmp/rmount/test/id_rsa -o StrictHostKeyChecking=no' \
        -o cache_timeout=30 admin@localhost:/tmp/rmount/test/remote_path \
        /tmp/rmount/test/mount_path

    # checks if it is still mounted
    $ mountpoint mount_path
    $ unmount fusermount -uz mount_path
    """
    test_fns = [
        test_interupt_upload,
        test_context,
        test_mount_remount,
        test_connection_drop,
        test_no_remote,
        test_reconnection,
    ]
    tmp_path = Path("/tmp/rmount/test")
    unmount(tmp_path.joinpath("mount_path"), timeout=5)
    shutil.rmtree(tmp_path, ignore_errors=True)
    tmp_path.mkdir(parents=True, exist_ok=True)
    config = _config(tmp_path)
    s = _remote_server(tmp_path=tmp_path)
    r = _rmount(tmp_path=tmp_path, config=config)
    for test_fn in test_fns:
        s.start()
        r.mount()
        test_fn(r, s)
        r.unmount()
        s.kill()
