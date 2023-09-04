import copy
import os
from pathlib import Path
import time
import docker
from docker.errors import NotFound
import paramiko
import pytest
from rmount.config import Remote

from rmount.main import RemoteMount

SSH_USER = "admin"
SSH_PORT = 2222
DOCKER_CONFIG = {
    "PUBLIC_KEY": None,
    "SUDO_ACCESS": False,
    "PASSWORD_ACCESS": False,
    "USER_NAME": SSH_USER,
    "PUID": 1000,
    "PGID": 1000,
}
DOCKER_CONTAINER_NAME = "rmount-test-server"


def docker_kill_running_containers(docker_client: docker.DockerClient):
    for c in docker_client.api.containers(filters={"name": DOCKER_CONTAINER_NAME}):
        docker_client.api.kill(c)
    for i in range(10):
        try:
            docker_client.api.remove_container(DOCKER_CONTAINER_NAME)
        except NotFound:
            return
        except Exception:
            continue
        time.sleep(1)

    raise RuntimeError(f"Could not remove {DOCKER_CONTAINER_NAME}")


def docker_run_cmd(
    docker_client: docker.DockerClient, public_key: str, volume_path: Path
):
    environment = copy.deepcopy(DOCKER_CONFIG)
    environment["PUBLIC_KEY"] = public_key
    docker_kill_running_containers(docker_client)
    volume_path.mkdir(exist_ok=True, parents=True)
    vp = volume_path.as_posix()

    img = docker_client.containers.run(
        name=DOCKER_CONTAINER_NAME,
        image="lscr.io/linuxserver/openssh-server:latest",
        environment=environment,
        ports={SSH_PORT: SSH_PORT},
        detach=True,
        volumes={vp: {"bind": vp, "mode": "rw"}},
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


def _config(tmp_path: Path):
    config = {
        "host": "localhost",
        "user": SSH_USER,
        "port": SSH_PORT,
        "key_file": tmp_path.joinpath("id_rsa"),
        "key_use_agent": False,
    }
    return Remote(**config)


def _rmount(tmp_path: Path, config) -> RemoteMount:
    remote_path = tmp_path / "remote_path"
    remote_path.mkdir(exist_ok=True)
    mount_path = tmp_path / "mount_path"
    rmount = RemoteMount(
        config,
        remote_path=remote_path,
        local_path=mount_path,
        refresh_interval_s=1,
        timeout=10,
    )
    return rmount


def _remote_server(tmp_path: Path) -> "RemoteServer":
    pub_key = _public_key(tmp_path)
    return RemoteServer(pub_key, tmp_path.joinpath("remote_path"))


@pytest.fixture(autouse=True)
def remote_server(tmp_path: Path):
    with _remote_server(tmp_path) as s:
        yield s


@pytest.fixture
def rmount(tmp_path, config):
    with _rmount(tmp_path, config) as r:
        yield r


@pytest.fixture
def config(tmp_path):
    return _config(tmp_path)


class RemoteServer:
    def __init__(self, public_key: str, volume_path: Path | str) -> None:
        self.public_key = public_key
        self.volume_path = Path(volume_path)
        self.img = None
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
        docker_kill_running_containers(self.client)

    def start(self):
        self.img = docker_run_cmd(self.client, self.public_key, self.volume_path)
