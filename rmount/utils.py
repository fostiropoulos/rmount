"""
Utilities, globals and helper functions for ``RemoteMount``
"""
# pylint: disable=missing-function-docstring
import logging
import multiprocessing
import subprocess
import tempfile
import time
import traceback
import typing
from pathlib import Path

logger = logging.getLogger("RMount")

CFG_NAME = "RMount"
CFG_TEMPLATE = """[{name}]\n{settings}"""
TIMEOUT = 30

RCLONE_PATH: Path = Path(__file__).parent.joinpath("rclone")


def _parse_args(args: tuple[typing.Any, ...]) -> list[str]:
    parsed_args = [str(arg) for arg in args]
    logger.debug("Invoking : %s", " ".join(parsed_args))
    return parsed_args


def _handle_pipe(pipe, verbose: bool):
    with pipe:
        while True:
            msg = pipe.readline().decode().strip("\n")
            if verbose:
                logger.error(msg)


def parse_pipes(
    process, verbose
) -> tuple[multiprocessing.Process, multiprocessing.Process]:
    pipes = (
        multiprocessing.Process(target=_handle_pipe, args=(process.stderr, verbose)),
        multiprocessing.Process(target=_handle_pipe, args=(process.stdout, verbose)),
    )
    for pipe in pipes:
        pipe.start()
    return pipes


def _execute(*args: typing.Any, timeout: int | None = None) -> tuple[str, str]:
    arg_list = _parse_args(args)
    try:
        proc = subprocess.run(
            arg_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )

        std_out = proc.stdout.decode("utf-8")
        error_out = proc.stderr.decode("utf-8")
        return std_out, error_out
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Could not execute command `{' '.join(arg_list)}`") from exc


def _execute_async(
    *args, stdout=subprocess.PIPE, stderr=subprocess.PIPE
) -> subprocess.Popen:
    cmd = _parse_args(args)
    process = subprocess.Popen(  # pylint: disable=consider-using-with
        cmd, stdout=stdout, stderr=stderr
    )
    return process


def unmount(local_path: Path | str, timeout: int):
    try:
        # Pre-emptive unmount of the directory
        _execute("fusermount", "-uz", f"{local_path}", timeout=timeout)
        for _ in range(timeout):
            if not is_mounted(local_path, timeout=timeout):
                return True
            time.sleep(1)
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    raise RuntimeError(f"Could not unmount {local_path}")


def mount(
    config_path: Path,
    remote_path: Path,
    local_path: Path,
    refresh_interval: int,
) -> subprocess.Popen:
    # files are cached based on read and writes
    # https://rclone.org/commands/rclone_mount/#vfs-cache-mode-writes
    command_with_args = [
        RCLONE_PATH,
        "mount",
        "--config",
        config_path,
        remote_path,
        local_path,
        "--vfs-cache-mode",
        "writes",
        "--allow-non-empty",
        "--poll-interval",
        f"{refresh_interval:d}s",
        "--vfs-cache-poll-interval",
        f"{refresh_interval:d}s",
        "--rc",
        "-vvvv",
    ]
    return _execute_async(*command_with_args)


def is_mounted(local_path, timeout: int):
    mountpoint_flag = False
    try:
        message, _ = _execute("mountpoint", local_path, timeout=timeout)
        mountpoint_flag = message.strip("\n").endswith("is a mountpoint")
    except Exception:  # pylint: disable=broad-exception-caught
        exc = traceback.format_exc()
        logger.error(exc)
    return mountpoint_flag


def make_config(settings):
    cfg = CFG_TEMPLATE.format(
        name=CFG_NAME,
        settings="\n".join(f"{k} = {v}" for k, v in settings.items()),
    )
    logger.debug("rclone config: ~%s~", cfg)

    return cfg


def write_timestamp(remote_path: Path, config_path: Path, timeout: int):
    with tempfile.NamedTemporaryFile() as file:
        file.write(f"{time.time()}\n".encode("utf-8"))
        file.flush()
        stdout, stderr = _execute(
            RCLONE_PATH,
            "copyto",
            file.name,
            remote_path.joinpath(".rmount"),
            "--config",
            config_path,
            timeout=timeout,
        )
        if len(stdout) > 0:
            logger.info(stdout)
        if len(stderr) > 0:
            logger.warning(stderr)


def refresh(remote_path: Path, config_path: Path, timeout: int):
    write_timestamp(remote_path=remote_path, config_path=config_path, timeout=timeout)
    _execute(
        RCLONE_PATH,
        "rc",
        "vfs/refresh",
        timeout=timeout,
    )