from pathlib import Path
from rmount import RemoteMount, S3


if __name__ == "__main__":
    # secret key guide:
    # https://aws.amazon.com/blogs/security/wheres-my-secret-access-key/
    config = S3(
        provider="AWS",
        region="us-east-2",
        secret_access_key="U1dUEw6Vbp21F7nZFr0+ATu82wNKU0hdmTxyBCkf",
        access_key_id="AKIAU5WVS5VGPAFDELIO",
    )

    local_path = Path("/tmp/s3")  # local directory
    remote_path = "rmount"  # s3://rmount
    mount = RemoteMount(config, remote_path, local_path)
    with mount:
        local_path.joinpath("foo").write_text("bar")
