import random
import subprocess
import time
from pathlib import Path

from rmount import Remote, RemoteMount, RemoteServer

if __name__ == "__main__":
    public_key = (Path.home() / ".ssh" / "id_rsa.pub").read_text()
    local_path = Path("/tmp/rmount-example")
    remote_path = Path("/tmp/test")

    # If not using RemoteServer
    # You will need to set-up ssh access to an external server
    # https://ubuntu.com/server/docs/service-openssh
    with RemoteServer(
        local_path=local_path,
        public_key=public_key,
        remote_path=remote_path,
    ) as s:


        config = Remote(
            host=s.ip_address,
            user=s.user,
            port=s.port,
            key_file=Path.home() / ".ssh" / "id_rsa",
        )
        mount = RemoteMount(config, remote_path, local_path)

        with mount:
            local_path.joinpath("A").write_bytes(random.randbytes(100_000_000))
            # wait until the file synchronizes
            time.sleep(1)
            subprocess.Popen(s.ssh_command + f" ls -la {remote_path}", shell=True)
    """
    If all goes well you should see something like:

        -rw-r--r-- 1 admin users      19 .rmount
        -rw-r--r-- 1 admin users 100000000 A

    "A" is the file that we just wrote and `.rmount` is the aux file used by rmount.
    """
