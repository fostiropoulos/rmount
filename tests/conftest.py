import copy
import os
import time
from pathlib import Path

import docker
import paramiko
import pytest
from docker.errors import NotFound

from rmount.config import Remote
from rmount.main import RemoteMount

SSH_USER = "admin"
SSH_PORT = 2222
# Used to make sure the permissions between docker and local
# are correct.
USER_UID = os.getuid()
DOCKER_CONFIG = {
    "PUBLIC_KEY": None,
    "SUDO_ACCESS": False,
    "PASSWORD_ACCESS": False,
    "USER_NAME": SSH_USER,
    "PUID": USER_UID,
    "PGID": USER_UID,
}
DOCKER_CONTAINER_NAME = "rmount-test-server"


def docker_kill_running_containers(
    docker_client: docker.DockerClient, container_name: str
):
    for c in docker_client.api.containers(filters={"name": container_name}):
        docker_client.api.kill(c)
    for i in range(10):
        try:
            docker_client.api.remove_container(container_name)
        except NotFound:
            return
        except Exception:
            continue
        time.sleep(1)

    raise RuntimeError(f"Could not remove {container_name}")


def docker_run_cmd(
    docker_client: docker.DockerClient,
    public_key: str,
    volume_remote_path: Path,
    volume_mountpoint: str | Path,
    container_name: str,
):
    environment = copy.deepcopy(DOCKER_CONFIG)
    environment["PUBLIC_KEY"] = public_key
    docker_kill_running_containers(docker_client, container_name)
    volume_remote_path.mkdir(exist_ok=True, parents=True)
    vp = volume_remote_path.as_posix()

    img = docker_client.containers.run(
        name=container_name,
        image="lscr.io/linuxserver/openssh-server:latest",
        environment=environment,
        ports={SSH_PORT: SSH_PORT},
        detach=True,
        volumes={volume_mountpoint: {"bind": vp, "mode": "rw"}},
        remove=True,
    )
    return img


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
        "port": SSH_PORT,
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
    tmp_path: Path, volume_mountpoint: Path | str | None = None
) -> "RemoteServer":
    pub_key = _public_key(tmp_path)

    if volume_mountpoint is not None:
        remote_path = Path("/tmp")
    else:
        remote_path = tmp_path.joinpath("remote_path")
    if volume_mountpoint is None:
        volume_mountpoint = remote_path
    return RemoteServer(pub_key, remote_path, volume_mountpoint=volume_mountpoint)


def pytest_addoption(parser):
    parser.addoption(
        "--volume-mountpoint",
        action="store",
        default=None,
        help=(
            "the volume name to optionally use. "
            "Used only for docker-to-docker tests with shared volumes"
        ),
    )


@pytest.fixture(autouse=True)
def remote_server(tmp_path: Path, pytestconfig):
    volume_mountpoint = pytestconfig.getoption("--volume-mountpoint")
    with _remote_server(tmp_path, volume_mountpoint) as s:
        yield s


@pytest.fixture
def rmount(tmp_path, config):
    r = _rmount(tmp_path, config)
    r.mount()
    yield r
    r.unmount()
    time.sleep(3)


@pytest.fixture
def config(tmp_path, remote_server: "RemoteServer"):
    return _config(tmp_path, remote_server.ip_address)


class RemoteServer:
    def __init__(
        self, public_key: str, volume_path: Path | str, volume_mountpoint: Path | str
    ) -> None:
        self.public_key = public_key
        self.volume_path = Path(volume_path)
        self.volume_mountpoint = volume_mountpoint
        self.ip_address = None
        self.img = None
        self.container_name = DOCKER_CONTAINER_NAME
        try:
            self.client = docker.from_env()
        except Exception as e:
            raise RuntimeError(
                "Could not find a docker installation. Please make sure"
                " docker is in Path and can run be run by the current"
                " system user (non-root) e.g. `docker run hello-world`."
                " Please refer to"
                " https://github.com/fostiropoulos/rmount/blob/main/DEVELOPER.md"
                " for detailed instructions."
            ) from e

    def __exit__(self, *args, **kwargs):
        self.kill()

    def __del__(self):
        if hasattr(self, "client"):
            self.kill()

    def __enter__(self):
        self.start()
        return self

    def kill(self):
        docker_kill_running_containers(self.client, self.container_name)

    def start(self):
        self.img = docker_run_cmd(
            self.client,
            self.public_key,
            self.volume_path,
            self.volume_mountpoint,
            container_name=self.container_name,
        )
        self.ip_address = self.client.containers.get(self.img.id).attrs[
            "NetworkSettings"
        ]["IPAddress"]
