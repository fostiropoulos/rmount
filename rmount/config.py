"""
Configuration module that implements default configuration for Google Cloud
S3 and a remote SSH server, with the possibility to extend to other providers.
"""
# pylint: disable=missing-class-docstring
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


# pylint: disable=too-few-public-methods
class RCloneConfig(ABC):
    @abstractmethod
    def to_dict(self) -> dict[str, str]:
        """
        dictionary representation of the configuration
        that can be then parsed to be used for RClone.

        Returns
        -------
        dict[str, str]
            the dictionary representation of the configuration.
        """


# pylint: disable=too-few-public-methods,redefined-builtin
class Remote(RCloneConfig):
    def __init__(
        self,
        host: str,
        user: str,
        port: int,
        key_pem: str | None = None,
        key_file: Path | None = None,
        key_use_agent: bool = False,
        type: str = "sftp",
    ):
        self.key_pem: str
        if not (key_file is None) ^ (key_pem is None):
            raise ValueError(
                "Must only provide either `key_pem` or `key_file`."
            )
        if key_file is not None:
            self.key_pem = key_file.read_text().replace("\n", "\\n")
        elif key_pem is not None:
            self.key_pem = key_pem.replace("\n", "\\n")
        self.host: str = host
        self.user: str = user
        self.port: int = port
        self.key_use_agent: bool = key_use_agent
        self.type: str = type

    def to_dict(self) -> dict[str, str]:
        """
        dictionary representation of the configuration
        that can be then parsed to be used for RClone.

        Returns
        -------
        dict[str, str]
            the dictionary representation of the configuration.
        """
        return {
            "host": self.host,
            "user": self.user,
            "port": str(self.port),
            "key_pem": self.key_pem,
            "key_use_agent": str(self.key_use_agent),
            "type": self.type,
        }


@dataclass
class S3(ABC):
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

    def to_dict(self) -> dict[str, str]:
        """
        dictionary representation of the configuration
        that can be then parsed to be used for RClone.

        Returns
        -------
        dict[str, str]
            the dictionary representation of the configuration.
        """
        _dict = self.__dict__
        return {str(k): str(v) for k, v in _dict.items()}
