from pathlib import Path
import shutil
import subprocess
import time

import pytest
from rmount.server import RemoteServer


def test_invalid_parameters(tmp_path: Path):
    with pytest.raises(
        ValueError,
        match="Must provide either `public_key` or `public_key_file`",
    ):
        RemoteServer(tmp_path)
    with pytest.raises(
        ValueError,
        match="Must provide either `public_key` or `public_key_file`",
    ):
        RemoteServer(tmp_path, public_key="x", public_key_file="x")
    with pytest.raises(
        ValueError,
        match="Must provide either `local_path` or `volume_name`",
    ):
        RemoteServer(tmp_path, volume_name="x", public_key="x")
    with pytest.raises(
        ValueError,
        match="Must provide either `local_path` or `volume_name`",
    ):
        RemoteServer(public_key="x")
    with pytest.raises(ValueError, match="Invalid ssh_user='root'"):
        RemoteServer(tmp_path, public_key="x", ssh_user="root")
    server = RemoteServer(tmp_path, public_key="x")
    with pytest.raises(
        RuntimeError,
        match="Container `rmount-ssh-server` is not running.",
    ):
        server.ssh_command


def test_run(tmp_path: Path, public_key_fn, volume_name):
    local_path = tmp_path / "local_path"
    local_path.mkdir(exist_ok=True, parents=True)
    public_key = public_key_fn(local_path)
    if volume_name is not None:
        _local_path = None
        remote_path = Path("/tmp")
    else:
        _local_path = local_path
    server = RemoteServer(
        _local_path,
        volume_name=volume_name,
        remote_path=remote_path,
        public_key=public_key,
    )
    server.start()
    time.sleep(2)
    key_path = local_path / "id_rsa"
    cmd = f"ssh -T -i {key_path}"
    run_cmd = server.ssh_command.replace("ssh", cmd).split(" ")
    run_cmd.append(f"cat {key_path}")
    ssh = subprocess.Popen(
        run_cmd,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    cmd_result = ssh.stdout.read()
    assert key_path.read_bytes() == cmd_result


if __name__ == "__main__":
    from tests.conftest import _public_key

    tmp_path: Path = Path("/tmp/remote-server-test")
    shutil.rmtree(tmp_path)
    tmp_path.mkdir(exist_ok=True, parents=True)

    test_invalid_parameters(tmp_path)
    test_run(
        tmp_path=tmp_path,
        public_key_fn=_public_key,
        pytestconfig=None,
    )
