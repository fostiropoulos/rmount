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

from rmount import RemoteMount
from rmount.config import Remote
from rmount.server import RemoteServer
from rmount.utils import terminate, unmount

logger = logging.getLogger("RMount")
logger.setLevel(logging.WARN)

if os.name != "posix":
    raise NotImplementedError("Unsupported OS.")


def write_bytes(tmp_file: Path):
    tmp_file.parent.mkdir(exist_ok=True)
    _bytes = os.urandom(1024 * 10)
    tmp_file.write_bytes(_bytes)
    return _bytes


def _assert_with_timeout(fn):
    for i in range(30):
        try:
            assert fn()
            return True
        except Exception:
            pass
        time.sleep(1)
    assert False


def _read_folder_contents(folder_path: Path):
    return [f.read_bytes() for f in sorted(folder_path.glob("[!.]*"), key=lambda x: x.name)]


def test_mount_remount(rmount: RemoteMount, remote_server: RemoteServer):
    """Tests whether the storage is persistent between mounts / unmounts."""
    local_path = rmount.local_path
    remote_path = rmount.remote_path
    lfile = local_path.joinpath("local.txt")
    rfile = remote_path.joinpath("remote.txt")
    remote_bytes = write_bytes(rfile)
    local_bytes = write_bytes(lfile)
    _assert_with_timeout(lambda: remote_path.joinpath("local.txt").read_bytes() == local_bytes)
    _assert_with_timeout(lambda: local_path.joinpath("remote.txt").read_bytes() == remote_bytes)

    rmount.unmount()
    assert len(list(local_path.glob("*"))) == 0
    # Test mounting on an existing directory.
    p = local_path.joinpath("test.txt")
    test_bytes = write_bytes(p)

    rmount.mount()
    _assert_with_timeout(lambda: local_path.joinpath("local.txt").read_bytes() == local_bytes)
    _assert_with_timeout(lambda: local_path.joinpath("remote.txt").read_bytes() == remote_bytes)
    # test that the existing file "test.txt" is no longer accessible
    _assert_with_timeout(lambda: not p.exists())
    # test that it remains preserved after unmounting
    rmount.unmount()
    _assert_with_timeout(lambda: p.read_bytes() == test_bytes)


def test_reconnection(rmount: RemoteMount, remote_server: RemoteServer):
    """Tests what happens when the connection between rmount and a remote
    suddenly drops but is then restored."""
    assert rmount.is_alive()
    remote_server.kill()
    assert not rmount.is_alive(timeout=5)
    remote_server.start()
    for i in range(30):
        if rmount.is_alive(timeout=5):
            return
        time.sleep(1)
    assert False


def test_connection_drop(tmp_path: Path, remote_server: RemoteServer, config: Remote):
    """Tests what happens when the connection between rmount and a remote
    suddenly drops."""
    is_dead = multiprocessing.Event()
    is_dead.clear()

    def _error_callback(is_dead):
        is_dead.set()

    config.host = remote_server.ip_address

    with RemoteMount(
        config,
        remote_path=tmp_path / "remote_path",
        local_path=tmp_path / "mount_path",
        refresh_interval_s=1,
        timeout=20,
        verbose=True,
        error_callback=lambda: _error_callback(is_dead),
    ) as rmount:
        assert rmount.is_alive()
        remote_server.kill()
        if rmount.is_alive(timeout=5):
            assert False, "rmount did not die on connection drop"

        for i in range(120):
            if is_dead.is_set():
                break
            time.sleep(1)
        assert is_dead.is_set()


def test_no_remote(rmount: RemoteMount, remote_server: RemoteServer):
    """Tests what happens when trying to connect to an invalid remote."""
    rmount.unmount()
    remote_server.kill()
    with pytest.raises(RuntimeError, match="Could not mount on time."):
        rmount.mount()


def test_context(rmount: RemoteMount, remote_server: RemoteServer):
    """Tests whether the context manager works as expected."""
    rmount.unmount()
    with rmount:
        assert rmount.is_alive()
    assert not rmount.is_alive()


def test_interupt_upload(rmount: RemoteMount, remote_server: RemoteServer):
    write_lock = multiprocessing.Lock()

    def delayed_unmount(queue: multiprocessing.Queue, write_lock):
        time.sleep(5)
        if not write_lock.acquire(block=True, timeout=10):
            queue.put([])
            raise RuntimeError
        rmount.refresh()
        time.sleep(1)
        queue.put(_read_folder_contents(rmount.local_path))
        terminate()
        rmount._is_alive.clear()
        rmount._is_alive.wait(timeout=5)
        rmount._heart.kill()
        rmount._is_alive.set()
        unmount(rmount.local_path, timeout=rmount._timeout)

    q = multiprocessing.Queue()
    slow_kill = multiprocessing.Process(target=delayed_unmount, args=(q, write_lock))
    slow_kill.start()
    n_numbers = 10_000
    # should be around 100MB of files
    while True:
        try:
            if not write_lock.acquire(block=True, timeout=1):
                break
            name = 0
            data = bytes(random.randint(n_numbers - 1, n_numbers * 10))
            with rmount.local_path.joinpath(f"{name:02d}").open("ab+") as f:
                f.write(data)
            name += 1
            write_lock.release()
            time.sleep(0.1)
        except:  # noqa: E722
            write_lock.release()
    ints_1 = q.get()
    ints_2 = _read_folder_contents(rmount.remote_path)
    n_files = len(ints_1)
    assert len(ints_2) == n_files
    assert all(ints_1[i] == ints_2[i] for i in range(n_files)) and all(
        ints_2[0] != ints_2[i] for i in range(1, n_files)
    )


if __name__ == "__main__":
    """
    NOTE Because the tests need to recover from an error to run again, it can
    be the case that the tests fail when run one after the other but pass when run
    independently. As long as they pass when run independently it should be sufficient.


    NOTE to test the connection to the mock server use:

    $ ssh -p 2223 -i /tmp/rmount/test/id_rsa -o StrictHostKeyChecking=no \
          admin@localhost

    NOTE To test whether you can mount e.g. there are no RemoteServer errors:

    $ sudo apt-get install sshfs
    $ sshfs -o default_permissions -o ssh_command='ssh -p 2223 -i \
        /tmp/rmount/test/id_rsa -o StrictHostKeyChecking=no' \
        -o cache_timeout=30 admin@localhost:/tmp/rmount/test/remote_path \
        /tmp/rmount/test/mount_path

    checks if it is still mounted

    $ mountpoint mount_path
    $ unmount fusermount -uz mount_path
    """
    from tests.conftest import (
        _config,
        _remote_server,
        _rmount,
    )

    logger.setLevel(logging.DEBUG)
    tmp_path = Path("/tmp/rmount/test")
    unmount(tmp_path.joinpath("mount_path"), timeout=5)
    shutil.rmtree(tmp_path, ignore_errors=True)
    tmp_path.mkdir(parents=True, exist_ok=True)
    s = _remote_server(tmp_path=tmp_path)
    s.start()

    config = _config(tmp_path, s.ip_address)
    test_connection_drop(tmp_path, s, config)
    s.kill()

    test_fns = [
        test_mount_remount,
        test_interupt_upload,
        test_reconnection,
        test_context,
        test_no_remote,
    ]
    for test_fn in test_fns:
        tmp_path = Path("/tmp/rmount/test")
        unmount(tmp_path.joinpath("mount_path"), timeout=5)
        shutil.rmtree(tmp_path, ignore_errors=True)
        tmp_path.mkdir(parents=True, exist_ok=True)
        s = _remote_server(tmp_path=tmp_path)
        s.start()
        config = _config(tmp_path, s.ip_address)
        r = _rmount(tmp_path=tmp_path, config=config)
        r.mount()
        logger.info(f"Testing {test_fn}.")
        test_fn(tmp_path, s)
        logger.info("Passed.")
        r.unmount()
        s.kill()
        time.sleep(1)

    print("finished.")
