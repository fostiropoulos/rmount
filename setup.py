import shutil
from pathlib import Path
import setuptools
import os


if os.name == "posix":  # Unix-like
    if os.uname().sysname == "Linux":
        shutil.copy(
            "linux/rclone",
            (Path(__file__).parent / "rmount" / "rclone").as_posix(),
        )
else:
    raise NotImplementedError("Unsupported OS")

setuptools.setup(
    name="rmount",
    version="0.0.2",
    author="Iordanis Fostiropoulos",
    author_email="mail@iordanis.me",
    description="A robust file-system mount to a remote storage.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/fostiropoulos/rmount",
    packages=setuptools.find_packages(exclude="linux"),
    include_package_data=True,
    package_data={
        "": ["rclone"],
    },
    python_requires=">=3.10",
    install_requires=[],
    extras_require={
        "server": ["docker>=6.1.3"],
        "dev": [
            "mypy>=1.2.0",
            "pytest>=7.3.0",
            "black>=23.9.1",
            "flake8>=6.0.0",
            "pylint>=2.17.2",
            "mock>=5.0.2",
            "docker>=6.1.3",
            "pydoclint>=0.1.0",
            "paramiko>=3.2.0",
        ],
    },
)
