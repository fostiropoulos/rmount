"""``RemoteServe`` that launches a secure Docker SSH server"""
import argparse
import logging
import multiprocessing
import os
import time
from pathlib import Path
import uuid


try:
    import docker
except ImportError as e:
    raise ImportError(
        "You need to install rmount with `server` option i.e. `pip"
        ' install rmount"[server]"`'
    ) from e
from docker.errors import NotFound
from docker.models.containers import Container

logger = logging.getLogger("RMount")

DEFAULT_PUB_KEY = Path.home() / ".ssh" / "id_rsa.pub"
RUNNING = "running"
PROHIBITED_USER_NAME = "root"
PORT = 2222


def _docker_kill_running_containers(
    docker_client: docker.DockerClient, container_name: str
):
    for container in docker_client.api.containers(
        filters={"name": container_name}
    ):
        docker_client.api.kill(container)
    for _ in range(10):
        try:
            docker_client.api.remove_container(container_name)
        except NotFound:
            return
        except Exception:  # pylint: disable=broad-exception-caught
            continue
        time.sleep(1)

    raise RuntimeError(f"Could not remove {container_name}")


def _make_docker_client() -> docker.DockerClient:
    try:
        client = docker.from_env()
    except Exception as exc:
        raise RuntimeError(
            "Could not find a docker installation. Please make sure"
            " docker is in Path and can run be run by the current"
            " system user (non-root) e.g. `docker run hello-world`."
            " Please refer to"
            " https://github.com/fostiropoulos/rmount/blob/main/DEVELOPER.md"
            " for detailed instructions."
        ) from exc
    return client


def _make_container(
    public_key: str,
    local_path: str,
    remote_path: Path | str | None = None,
    docker_client: docker.DockerClient | None = None,
    container_name="rmount-ssh-server",
    ssh_user: str = "admin",
    user_id: int | None = None,
    user_gid: int | None = None,
    **kwargs,
) -> Container:
    if user_id is None:
        user_id = os.getuid()
    if user_gid is None:
        user_gid = os.getgid()
    if docker_client is None:
        docker_client = _make_docker_client()
    if remote_path is None:
        remote_path = str(local_path)

    enviroment_config = {
        "PUBLIC_KEY": public_key,
        "SUDO_ACCESS": "true",
        "PASSWORD_ACCESS": "false",
        "USER_NAME": ssh_user,
        "PUID": user_id,
        "PGID": user_gid,
    }
    enviroment_config.update(**kwargs)
    logger.info(
        "Running SSH-Server Docker with %s", enviroment_config
    )
    return docker_client.containers.run(
        name=container_name,
        image="lscr.io/linuxserver/openssh-server:latest",
        environment=enviroment_config,
        ports={f"{PORT}/tcp": None},
        detach=True,
        volumes={
            str(local_path): {"bind": str(remote_path), "mode": "rw"}
        },
    )


def _handle_pipe(container):
    for log in container.logs(stream=True, stdout=True, stderr=True):
        logger.debug(log)


class RemoteServer:
    """
    A Remote SSH server that can be used for testing or as a safe way to store
    experiment artifacts without exposing the entire file system to a third party,
    aka an ABLATOR dashboard.

    Parameters
    ----------
    local_path : Path | str | None
        The local path that can be used to access the contents of the ``RemoteServer``. Must be set
        if `volume_name` is None
    volume_name : str | None
        The volume to  use to mount the docker container that can be used to access the contents of
        the ``RemoteServer``. Must be set if `local_path` is None
    public_key : str | None
        The public key which allows access to the ``RemoteServer``.
        Must be set if `public_key_file` is None
    public_key_file : str | Path | None
        The path to the public key which allows access to the ``RemoteServer``.
        Must be set if `public_key` is None
    remote_path : Path | str | None, optional
        The remote path that can be used to map to the local_path and access
        the contents of the ``RemoteServer``. When unspecified, it will be set
        the same as the local_path e.g.
        `local_path:remote_path` -> `local_path:local_path`, by default None
    ssh_user : str, optional
        the ssh-user that can be used to access the RemoteServer, by default "admin"
    container_name : str | None, optional
        The unique name of the container. RemoteServer will kill any other container
        by the same name to avoid network conflicts, by default "rmount-ssh-server"
    verbose : bool, optional
        Whether to print the output of the container to stdout, by default False

    Attributes
    ----------
    ip_address : None | str
        The local network IP address of the container.
    ssh_command : str
        The ssh command that can be used to connect to the container through the local network.

    Examples
    ----------
    Connect to the SSH server
    >>> DEFAULT_PUB_KEY = Path.home() / ".ssh" / "id_rsa.pub"
    >>> server = RemoteServer(public_key_file=DEFAULT_PUB_KEY, local_path = "/tmp")
    >>> server.start()
    >>> assert server.is_alive()
    >>> server.ssh_command
    ... ssh -p 2222 -o StrictHostKeyChecking=no admin@172.17.0.2

    To connect and test the server (while the script is running):
    `$ ssh -p 2222 -o StrictHostKeyChecking=no admin@172.17.0.2`


    Raises
    ------
    ValueError
        If incorrect arguments are provided.
    RuntimeError
        If the `volume_name` does not exist.

    """

    def __init__(
        self,
        local_path: Path | str | None = None,
        volume_name: str | None = None,
        public_key: str | None = None,
        public_key_file: str | Path | None = None,
        remote_path: Path | str | None = None,
        ssh_user: str = "admin",
        container_name: str | None = None,
        verbose: bool = False,
    ) -> None:
        self._remote_path = remote_path
        self.ip_address: None | str = None
        self.port = PORT
        self._container: None | Container = None
        if not (public_key is None) ^ (public_key_file is None):
            raise ValueError(
                "Must provide either `public_key` or"
                " `public_key_file`, but not both."
            )
        if not (local_path is None) ^ (volume_name is None):
            raise ValueError(
                "Must provide either `local_path` or `volume_name`,"
                " but not both."
            )
        self._public_key: str
        if public_key_file is not None:
            self._public_key = Path(public_key_file).read_text(
                encoding="utf-8"
            )
        elif public_key is not None:
            self._public_key = public_key
        if verbose:
            logger.setLevel(logging.DEBUG)
        self._verbose = verbose
        if ssh_user == PROHIBITED_USER_NAME:
            raise ValueError(
                f"Invalid ssh_user='{PROHIBITED_USER_NAME}'"
            )
        self.user: str = ssh_user
        if container_name is None:
            self._container_name: str = str(uuid.uuid4())
        else:
            self._container_name = container_name
        self._client: docker.DockerClient = _make_docker_client()
        if volume_name is not None and not self._client.volumes.get(
            volume_name
        ):
            raise RuntimeError(
                f"Volume: '{volume_name}' does not exist."
            )
        if local_path is not None:
            local_path = Path(local_path).absolute()
            self._local_path = str(local_path)
            # This allows for permissions
            logger.info("Using a local-path")
            local_path.mkdir(exist_ok=True, parents=True)
        else:
            self._local_path = str(volume_name)

    def __exit__(self, *args, **kwargs):
        self.kill()

    def __del__(self):
        self.kill()

    def __enter__(self):
        return self.start()

    def kill(self):
        """
        kill the currently running container.
        """
        if hasattr(self, "_client"):
            _docker_kill_running_containers(
                self._client, self._container_name
            )

    def start(self) -> "RemoteServer":
        """
        Starts the docker container configured by the `RemoteServer`
        object's properties.

        Returns
        -------
        RemoteServer
            The RemoteServer object.

        Raises
        ------
        RuntimeError
            If the container can not start succesfully.
        """
        _docker_kill_running_containers(
            self._client, self._container_name
        )
        self._container = _make_container(
            public_key=self._public_key,
            local_path=self._local_path,
            remote_path=self._remote_path,
            docker_client=self._client,
            container_name=self._container_name,
            ssh_user=self.user,
        )
        self.ip_address = self._client.containers.get(
            self._container.id
        ).attrs["NetworkSettings"]["IPAddress"]

        if self._verbose:
            multiprocessing.Process(
                target=_handle_pipe, args=(self._container,)
            ).start()

        for _ in range(5):
            if self.is_alive():
                return self
            time.sleep(1)
        raise RuntimeError(
            f"Could not start container `{self._container_name}`"
        )

    def is_alive(self) -> bool:
        """
        Is used to check whether the container is active and running.

        Returns
        -------
        bool
            Whether the container is alive.
        """
        if self._container is None:
            return False
        try:
            return (
                self._client.containers.get(self._container.id).status
                == RUNNING
            )
        except:  # pylint: disable=bare-except # noqa: E722
            return False

    @property
    def ssh_command(self) -> str:
        """
        The ssh command that can be used to connect to the container through the local network.

        Returns
        -------
        str
            A command that can be run on the terminal.

        Raises
        ------
        RuntimeError
            If the container has died.
        """
        if not self.is_alive():
            raise RuntimeError(
                f"Container `{self._container_name}` is not running."
            )
        return (
            f"ssh -p {self.port} -o StrictHostKeyChecking=no"
            f" {self.user}@{self.ip_address}"
        )


def run_server(local_path: Path, public_key_file: Path):
    """
    Runs a `RemoteServer` locally that can be used for testing.

    Parameters
    ----------
    local_path : Path
        Path to the local directory to map inside the RemoteServer
    public_key_file : Path
        The path to the public_key_file to use for accessing the server.
    """
    logger.info("Running RemoteServer on the background.")

    server = RemoteServer(
        local_path=local_path, public_key_file=public_key_file
    )
    server.start()
    logger.info("You can connect via `%s`", {server.ssh_command})
    while server.is_alive():
        logger.info("RemoteServer is alive. Heartbeat.")
        time.sleep(5)


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--local-path", type=Path, required=True)
    arg_parser.add_argument(
        "--public-key-file",
        type=Path,
        required=False,
        default=DEFAULT_PUB_KEY,
    )
    logger.setLevel(logging.INFO)
    run_kwargs = vars(arg_parser.parse_args())
    run_server(**run_kwargs)
