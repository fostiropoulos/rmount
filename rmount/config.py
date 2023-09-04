"""
Configuration module that implements default configuration for Google Cloud
S3 and a remote SSH server, with the possibility to extend to other providers.
"""
# pylint: disable=missing-class-docstring
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Remote:
    host: str
    user: str
    port: int
    key_file: Path
    key_use_agent: bool = False
    type: str = "sftp"


@dataclass
class S3:
    provider: str
    access_key_id: str
    secret_access_key: str
    region: str = ""
    endpoint: str = ""
    # `env_auth` get the access key and secret key from the environment
    # variables. Must set `access_key_id`  and `secret_access_key`
    # to empty.
    env_auth: str = "false"
    # `location_constraint` used only when creating buckets.
    # must remain empty otherwise.
    location_constraint: str = ""
    acl: str = "private"
    server_side_encryption: str = ""
    storage_class: str = ""
    type: str = "s3"
