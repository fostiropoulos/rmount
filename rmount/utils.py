"""Utilities, globals and helper functions for ``RemoteMount``."""
# pylint: disable=missing-function-docstring
import logging
import multiprocessing
import re
import subprocess
import tempfile
import time
import traceback
import typing
from pathlib import Path

logging.basicConfig(
    format=(
        "%(asctime)s %(levelname)-5s [%(filename)s:%(lineno)d]"
        " %(message)s"
    ),
    datefmt="%Y-%m-%d:%H:%M:%S",
    level=logging.WARN,
)
logger = logging.getLogger("RMount")

CFG_NAME = "RMount"
CFG_TEMPLATE = """[{name}]\n{settings}"""
TIMEOUT = 30

RCLONE_PATH: Path = Path(__file__).parent.joinpath("rclone")

# initialization flag that checks for depedencies only once.
_IS_INIT = False
log_re = re.compile(
    "[0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} "
)


def _parse_args(args: tuple[typing.Any, ...]) -> list[str]:
    parsed_args = [str(arg) for arg in args]
    logger.debug("Invoking: %s", " ".join(parsed_args))
    return parsed_args


def _clean_log_msg(msg: str):
    _, msg = re.split(
        log_re,
        msg,
    )
    return msg


def _handle_pipe(pipe, verbose: bool):
    with pipe:
        while True:
            msg = pipe.readline().decode().strip("\n").strip(" ")
            if verbose and len(msg) > 0:
                msg = _clean_log_msg(msg)
                logger.debug("RClone: %s", msg)


def parse_pipes(
    process, verbose
) -> tuple[multiprocessing.Process, multiprocessing.Process]:
    pipes = (
        multiprocessing.Process(
            target=_handle_pipe, args=(process.stderr, verbose)
        ),
        multiprocessing.Process(
            target=_handle_pipe, args=(process.stdout, verbose)
        ),
    )
    for pipe in pipes:
        pipe.start()
    return pipes


def _execute(
    *args: typing.Any, timeout: int | None = None
) -> tuple[str, str]:
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
        raise RuntimeError(
            f"Could not execute command `{' '.join(arg_list)}`"
        ) from exc


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
        _execute(
            "fusermount", "-uz", f"{local_path}", timeout=timeout
        )
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
        "--vfs-write-back",
        "0s",
        "--poll-interval",
        f"{refresh_interval:d}s",
        "--vfs-cache-poll-interval",
        f"{refresh_interval:d}s",
        "--rc",
        "--rc-no-auth",
        "-vvvv",
    ]
    return _execute_async(*command_with_args)


def is_mounted(local_path, timeout: int):
    mountpoint_flag = False
    try:
        message, _ = _execute(
            "mountpoint", local_path, timeout=timeout
        )
        mountpoint_flag = message.strip("\n").endswith(
            "is a mountpoint"
        )
    except Exception:  # pylint: disable=broad-exception-caught
        exc = traceback.format_exc()
        logger.error(
            "Error calling `mountpoint` command: %s", message
        )
        logger.debug(exc)
    return mountpoint_flag


def make_config(settings):
    cfg = CFG_TEMPLATE.format(
        name=CFG_NAME,
        settings="\n".join(f"{k} = {v}" for k, v in settings.items()),
    )
    logger.debug("rclone config: ~%s~", cfg)

    return cfg


def write_timestamp(
    remote_path: Path, config_path: Path, timeout: int
):
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
            logger.warning(
                "RClone Log: %s", stderr.strip("\n").strip(" ")
            )


def refresh_cache(timeout: int):
    try:
        _execute(
            RCLONE_PATH,
            "rc",
            "vfs/refresh",
            timeout=timeout,
        )
    except:  # pylint: disable=bare-except # noqa : E722
        pass


def terminate():
    try:
        _execute(
            RCLONE_PATH,
            "rc",
            "core/quit",
            timeout=1,
        )
    except:  # pylint: disable=bare-except # noqa : E722
        pass


def refresh(remote_path: Path, config_path: Path, timeout: int):
    write_timestamp(
        remote_path=remote_path,
        config_path=config_path,
        timeout=timeout,
    )
    refresh_cache(timeout=timeout)


def _requirements_installed():
    mountpoint_flag = False
    local_dir = Path(__file__).parent
    try:
        message, _ = _execute("mountpoint", local_dir, timeout=5)
        mountpoint_flag = message.strip("\n").endswith(
            "is a mountpoint"
        )
    except Exception as exc:
        raise ImportError(
            "Could not execute or find the `mountpoint` command"
        ) from exc
    if mountpoint_flag:
        raise ImportError("`mountpoint` must be misconfigured")

    try:
        _execute("fusermount", "-uz", f"{local_dir}", timeout=5)
    except Exception as exc:
        raise ImportError(
            "Could not execute or find the `fusermount` command"
        ) from exc
    if is_mounted(local_dir, timeout=5):
        raise ImportError("`fusermount` must be misconfigured")
    return True


if not _IS_INIT and _requirements_installed():
    _IS_INIT = True
