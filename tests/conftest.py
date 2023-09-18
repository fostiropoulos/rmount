import os
import time
from pathlib import Path

import paramiko
import pytest
from rmount.config import Remote
from rmount.server import RemoteServer
from rmount.main import RemoteMount

# Used to make sure the permissions between docker and local
# are correct.
DOCKER_CONTAINER_NAME = "rmount-test-server"

SSH_USER = "admin"
CONTAINER_SSH_PORT = 2222


def _public_key(tmp_path: Path):
    pkey_path = tmp_path.joinpath("id_rsa")
    pkey = paramiko.RSAKey.generate(bits=2048)
    with open(
        os.open(
            pkey_path.as_posix(),
            flags=(os.O_WRONLY | os.O_CREAT | os.O_TRUNC),
            mode=0o600,
        ),
        "w",
        encoding="utf-8",
    ) as p:
        pkey.write_private_key(p)
    public_key = f"ssh-rsa {pkey.get_base64()}"
    public_key_path = tmp_path.joinpath("id_rsa.pub")
    public_key_path.write_text(public_key)

    return public_key


def _config(tmp_path: Path, host: str = "localhost"):
    config = {
        "host": host,
        "user": SSH_USER,
        "port": CONTAINER_SSH_PORT,
        "key_file": tmp_path.joinpath("id_rsa"),
        "key_use_agent": False,
    }
    return Remote(**config)


def _rmount(tmp_path: Path, config) -> RemoteMount:
    remote_path = tmp_path / "remote_path"
    mount_path = tmp_path / "mount_path"
    rmount = RemoteMount(
        config,
        remote_path=remote_path,
        local_path=mount_path,
        refresh_interval_s=1,
        timeout=20,
        verbose=True,
    )
    return rmount


def _remote_server(
    tmp_path: Path, volume_name: Path | str | None = None
) -> RemoteServer:
    pub_key = _public_key(tmp_path)

    if volume_name is not None:
        remote_path = Path("/tmp")
        local_path = None
    else:
        remote_path = tmp_path / "remote_path"
        local_path = tmp_path / "remote_path"
    return RemoteServer(
        public_key=pub_key,
        remote_path=remote_path,
        local_path=local_path,
        volume_name=volume_name,
        container_name=DOCKER_CONTAINER_NAME,
        ssh_user=SSH_USER,
    )


def pytest_addoption(parser):
    parser.addoption(
        "--volume-name",
        action="store",
        default=None,
        help=(
            "the volume name to optionally use. "
            "Used only for docker-to-docker tests with shared volumes"
        ),
    )


@pytest.fixture
def volume_name(pytestconfig):
    return pytestconfig.getoption("--volume-name")


@pytest.fixture(autouse=True)
def remote_server(tmp_path: Path, pytestconfig):
    volume_name = pytestconfig.getoption("--volume-name")
    with _remote_server(tmp_path, volume_name) as s:
        yield s


@pytest.fixture
def rmount(tmp_path, config):
    r = _rmount(tmp_path, config)
    r.mount()
    yield r
    r.unmount()
    time.sleep(3)


@pytest.fixture
def config(tmp_path, remote_server: RemoteServer):
    return _config(tmp_path, remote_server.ip_address)


@pytest.fixture
def public_key_fn():
    return _public_key
