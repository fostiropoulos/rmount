from pathlib import Path
from rmount import RemoteMount, Remote, S3


if __name__ == "__main__":
    # secret key guide:
    # https://aws.amazon.com/blogs/security/wheres-my-secret-access-key/
    config = S3(
        provider="AWS",
        region="us-east-1",
        secret_access_key="xxx",
        access_key_id="xxx",
    )

    # secret key guide:
    # https://cloud.google.com/storage/docs/authentication/managing-hmackeys
    config = S3(
        provider="GCS",
        secret_access_key="xxx",
        access_key_id="xxx",
        endpoint="https://storage.googleapis.com",
    )

    # You will need to set-up ssh access to the server
    # https://ubuntu.com/server/docs/service-openssh
    config = Remote(
        host="localhost",
        user="root",
        port=22,
        key_file=Path.home() / ".ssh" / "id_rsa",
    )

    local_path = Path("/tmp/s3")  # local directory
    remote_path = "rmount"  # s3://rmount
    mount = RemoteMount(config, remote_path, local_path)
    with mount:
        local_path.joinpath("foo").write_text("bar")

    # equivalent
    mount.mount()
    local_path.joinpath("foo").write_text("bar")
    mount.unmount()
