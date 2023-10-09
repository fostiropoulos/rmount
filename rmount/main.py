"""
Main RemoteMount module with auxiliary utilities to enable multi-processing
monitoring.
"""
import logging
import multiprocessing as mp
import os
import subprocess
import tempfile
import threading
import time
import traceback
from collections import abc
from multiprocessing import Process, Queue, active_children
from multiprocessing.synchronize import Event, Lock
from pathlib import Path
import uuid
from rmount.config import S3, Remote
from rmount.utils import (
    CFG_NAME,
    TIMEOUT,
    is_mounted,
    make_config,
    mount,
    parse_pipes,
    refresh,
    refresh_cache,
    terminate,
    unmount,
)

logger = logging.getLogger("RMount")

# Number of missed heartbeats of the mount process after which to throw an error.
MISSED_HEARTBEATS = 3
# Number of retries to mount after missed heartbeats
MOUNT_ERROR_LIMIT = 1
# Number of retries to detect the mount point after initialization
MOUNT_CALLBACK_RETRIES = 5
# Name of OS that is supported
SUPPORTED_OS = ["posix"]
INPUT_OUTPUT_ERROR_MSG = "[Errno 5] Input/output error"


def _mount_callback(  # noqa:DOC201
    local_path: Path, timeout: int, is_alive_event: Event
):
    """
    A callback to determine whether the `local_path` mount point is active and
    signal the main process via `is_alive_event`. The function returns either after
    the mount point is active or after a time threshold is reached. The threshold is
    calculated based  on ``MOUNT_CALLBACK_RETRIES`` repetitions of `timeout` with
    2 seconds delay between repetitions. i.e.
    timeout_s = MOUNT_CALLBACK_RETRIES * `timeout` * 2

    Parameters
    ----------
    local_path : Path
        Path to the local mount point
    timeout : int
        The timeout for each ``is_alive`` method call.
    is_alive_event : Event
        The object used to signal that the mount point is active.
    """
    for _ in range(MOUNT_CALLBACK_RETRIES):
        if is_alive(local_path, timeout=timeout):
            is_alive_event.set()
            return
        time.sleep(1)
    logger.error("Could not detect mountpoint.")
    return


def is_alive(local_path: Path, timeout: int) -> bool:
    """
    is_alive checks whether there is an alive ``RemoteMount`` process in
    `local_path` given a `timeout`.

    Parameters
    ----------
    local_path : Path
        The local directory where the mount process is expected to be.
    timeout : int
        The timeout after which it will return False

    Returns
    -------
    bool
        Whether there is a ``RemoteMount`` running at `local_path`
    """

    def _is_alive(queue):
        file_flag = False
        try:
            # we do an _is_init check because if we try to access the
            # filesystem before being ready, we can interrupt the process.
            if local_path.joinpath(".rmount").exists():
                last_alive = float(
                    local_path.joinpath(".rmount").read_text()
                )
                file_flag = time.time() - last_alive < timeout * 2
                logger.debug("Mountpoint last alive: %s", last_alive)
        # pylint: disable=broad-exception-caught
        except Exception:
            exc_str = traceback.format_exc()
            # error relating to `.rmount` be synchronously written to
            if INPUT_OUTPUT_ERROR_MSG not in exc_str:
                logger.error(exc_str)

        mountpoint_flag = is_mounted(local_path, timeout=timeout)
        logger.debug(
            "Mountpoint (active, valid): (%s,%s)",
            mountpoint_flag,
            file_flag,
        )
        queue.put(mountpoint_flag and file_flag)

    queue: Queue = Queue()
    _is_alive_process = Process(target=_is_alive, args=(queue,))
    _is_alive_process.start()
    _is_alive_process.join(timeout=timeout)
    _is_alive_process.kill()

    if queue.empty() or not queue.get_nowait():
        return False
    return True


# pylint: disable=broad-exception-caught
def _heartbeat(  # noqa:DOC501
    config_path: Path,
    local_path: Path,
    remote_path: Path,
    refresh_interval: int,
    timeout: int,
    lock: Lock | None,
    alive_event: Event,
    terminate_event: Event,
    verbose: bool,
) -> None:
    """
    _heartbeat function that runs constantly in the background
    to monitor the health of the mount process. If the mount process
    fails to communicate up to ``MISSED_HEARTBEATS``, then it restarts
    the mount process up to a ``MOUNT_ERROR_LIMIT`` limit.

    Parameters
    ----------
    config_path : Path
        The path of the configuration for rclone
    local_path : Path
        The local mount directory. If it is not empty, the contents will
        be preserved and the directory will be mounted on top.
    remote_path : Path
        The remote location to mount.
    refresh_interval : int
        The interval by which to refresh the contents of the files from and to
        the remote. A higher value leads to larger network and resource demands.
    timeout : int
        The timeout in seconds to use after which it will raise an error if
        a command or process fails to return.
    lock : Lock | None
        The lock is used to indicate in the parent process that the mount
        was successful.
    alive_event : Event
        The event is used to communicate from the main process whether it
        should remain alive or terminate.
    terminate_event : Event
        The event is set before termination to indicate a graceful exit.
    verbose : bool
        Whether to print `rclone` process logs in STDOUT. Warning: can cause
        logs to be unreadable. Must also set log-level to ``logging.DEBUG``

    """
    mount_process = _MountProcess(
        config_path,
        remote_path,
        local_path,
        timeout=timeout,
        refresh_interval_s=refresh_interval,
        verbose=verbose,
    )
    missed_heartbeats = 0
    while alive_event.is_set():
        try:
            # we need to take refresh interval into consideration, because
            # if the refresh does not happen very often and the timeout
            # is less than the refresh, it will lead to incorrectly thinking
            # the process is dead.
            alive_timeout = max(2, refresh_interval)

            refresh(
                mount_process.remote_path,
                config_path,
                timeout=timeout,
            )
            _alive = is_alive(local_path, timeout=alive_timeout)
            if not _alive and missed_heartbeats >= MISSED_HEARTBEATS:
                missed_heartbeats = 0
                unmount(local_path, timeout=timeout)
                raise TimeoutError("Mount process is dead.")
            if not _alive:
                missed_heartbeats += 1
                continue
            missed_heartbeats = 0
            if lock is not None:
                lock.release()
                lock = None
        except Exception:
            exc = traceback.format_exc()
            logger.error("Error during process heartbeat.")
            logger.debug(exc)
            try:
                mount_process.error_callback(timeout=timeout)
            except OSError:
                # Too many errors.
                mount_process.kill()
                # The process is not exiting gracefully
                terminate_event.clear()
                return
            except Exception:
                exc = traceback.format_exc()
                logger.error("Error during heartbeat error-callback.")
                logger.debug(exc)
        time.sleep(refresh_interval)
    # received a kill signal
    mount_process.kill()
    terminate_event.set()
    return


class _MountProcess:
    """
    Internal helper class to manage the Process that mounts
    to the local directory. The class implements error-handling
    as well as managing resources such as pipes of the mount process.
    This is the main class where the mount process lives. Currently,
    there is only support for Linux and Mac.

    Parameters
    ----------
    config_path : Path | str
        Path to the configuration for the remote location.
    remote_path : Path | str
        Path to the remote location to mount.
    local_path : Path | str
        Path to the local directory to mount.
    timeout : int
        The timeout in seconds to use after which it will raise an error if
        a command or process fails to return.
    refresh_interval_s : int, optional
        The interval by which to refresh the contents of the files from and to
        the remote. A higher value leads to larger network and
        resource demands, by default 10
    verbose : bool
        Whether to print `rclone` process logs in STDOUT. Warning: can cause
        logs to be unreadable. Must also set log-level to ``logging.DEBUG``, by default False
    """

    def __init__(
        self,
        config_path: Path | str,
        remote_path: Path | str,
        local_path: Path | str,
        timeout: int,
        refresh_interval_s: int = 10,
        verbose: bool = False,
    ):
        self.config_path: Path = Path(config_path)

        self._remount_err_count = 0
        self._last_error_time = time.time()
        self._refresh_interval_s = refresh_interval_s
        self._verbose = verbose
        self._timeout = timeout
        self.remote_dir = Path(remote_path)
        self.remote_path: Path = Path(f"{CFG_NAME}:{remote_path}")
        self.local_path = Path(local_path)
        self._process: subprocess.Popen | None = None
        self._pipes: list[Process] | None = None
        self.mount()

    def mount(self):  # noqa: DOC201
        """
        Mounts a remote storage to a local directory. It first writes
        a timestamp file to the remote storage that is used to signal that the
        remote storage has been mounted successfully. For example, once the remote
        storage is mounted we would expect the file to appear in the local storage.

        Then it creates a child ``Process`` that runs `rclone` in the background
        to create the mount point.

        Then it monitors the time at which the mount point will be successfully
        created. If it fails to mount, it retries for ``MOUNT_ERROR_LIMIT``
        times and finally returns or raises an error.

        Raises
        ------
        RuntimeError
            If it can not connect to the `remote_path` due to misconfiguration or
            errors in the mount process itself. e.g. slow connection.
        """
        # refresh writes a timestamped file to the remote. Fails early if the
        # configuration is invalid.
        try:
            refresh(
                self.remote_path,
                self.config_path,
                timeout=self._timeout,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Could not connect to remote {self.remote_path}."
                " Make sure your configuration is correct."
            ) from exc

        # we unmount the directory just in case.
        unmount(self.local_path, timeout=self._timeout)
        self.local_path.mkdir(exist_ok=True, parents=True)

        # This is the main mount process
        self._process = mount(
            self.config_path,
            self.remote_path,
            self.local_path,
            self._refresh_interval_s,
        )
        # We need this, otherwise, the pipe gets overloaded and causes an error.
        self._pipes = parse_pipes(self._process, self._verbose)

        try:
            timeout = max(self._refresh_interval_s, self._timeout)

            is_alive_event = mp.Event()
            mt_c = Process(
                target=_mount_callback,
                args=(self.local_path, timeout, is_alive_event),
            )
            mt_c.start()
            _call_back_timeout = (
                timeout * (MOUNT_CALLBACK_RETRIES + 1) * 2
            )
            for _ in range(_call_back_timeout):
                if is_alive_event.wait(timeout=1):
                    return
                if not mt_c.is_alive() and not is_alive_event.wait(
                    timeout=1
                ):
                    break
            self.error_callback()

        except TimeoutError as exc:
            raise RuntimeError(
                "Could not successfully create a mount point between"
                f" {self.local_path} and {self.remote_path}."
            ) from exc

    def error_callback(self, timeout: int | None = None):
        """
        Called when the mount process faces an error to
        restart the mount process. The method uses the time record of
        the last error to terminate as the error could be irrecoverable
        after ``MOUNT_ERROR_LIMIT`` restarts.

        Parameters
        ----------
        timeout : int | None, optional
            The timeout used for the unmount process and as a threshold
            to reset the consecutive error counter. If not specified,
            uses the object's default `timeout`, by default None

        Raises
        ------
        OSError
            If the process faces a non-recoverable mount error.
        """
        if timeout is None:
            timeout = self._timeout
        if self._remount_err_count >= MOUNT_ERROR_LIMIT:
            unmount(self.local_path, timeout=timeout)
            error_msg = (
                f"Failed to mount {MOUNT_ERROR_LIMIT} times in a row."
            )
            raise OSError(error_msg)
        _error_timeout = timeout * (MOUNT_CALLBACK_RETRIES + 3) * 2
        if time.time() - self._last_error_time < _error_timeout:
            # error happened within the time it takes for the mount_callback
            # to terminate
            self._remount_err_count += 1
        else:
            self._remount_err_count = 1

        self._last_error_time = time.time()

        logger.error(
            "Mount point failure. Restarting %s / %s ...",
            self._remount_err_count,
            MOUNT_ERROR_LIMIT,
        )
        self.kill()
        self.mount()

    def kill(self):
        """
        Terminate the main mount process along with any auxiliary processes and
        unmount the local path. This should restore the system to its original
        state.
        """
        terminate()
        if hasattr(self, "_process") and self._process is not None:
            self._process.kill()
            unmount(self.local_path, timeout=self._timeout)
        if hasattr(self, "_pipes") and self._pipes is not None:
            for pipe in self._pipes:
                pipe.kill()

    def __exit__(self, *args, **kwargs):
        self.kill()

    def __del__(self):
        try:
            self.kill()
        except Exception:
            ...


class RemoteMount:
    """
    The class creates a mount point between a `remote_path` and
    a `local_path` based on some configuration `settings`
    the interval by which to refresh the cache and robustness
    to errors via a user-specified timeout. The class manages and monitors
    an `rclone` process that is responsible for implementing the mount
    logic. The mount point is expected to be robust to errors caused by
    connectivity issues or dead mount points.

    When it class encounters an error it triggers `SIGKILL` to terminate
    all relevant background processes and itself. For this reason, it is
    recommended you run it in its process.

    Parameters
    ----------
    settings : RemoteConfig
        A remote configuration object specific to the storage type
        and user preferences. Please see ``RemoteConfig``
    remote_path : Path | str
        The remote path to connect to the mount point
    local_path : Path | str
        The local path to the mount point
    refresh_interval_s : int, optional
        The interval by which to reset the cache, by default 10
    timeout : int, optional
        The timeout after which many of the processes and functions
        will raise an error, by default ``TIMEOUT = 30``
    verbose : bool, optional
        Whether to print `rclone` logs to the console, by default ``False``
    error_callback : bool, optional
        A function called once the process encounters a non-recoverable error, by default ``None``
    Raises
    ------
    NotImplementedError
        If the running OS is Windows.
    """

    def __init__(  # noqa: DOC105
        self,
        settings: Remote | S3,
        remote_path: Path | str,
        local_path: Path | str,
        refresh_interval_s: int = 10,
        timeout: int = TIMEOUT,
        verbose: bool = False,
        error_callback: abc.Callable | None = None,
    ):
        if os.name.lower() not in SUPPORTED_OS:
            raise NotImplementedError(
                "RemoteMount not supported for your platform"
                f" `{os.name}`"
            )
        self.local_path: Path = Path(local_path)
        self.remote_path: Path = Path(remote_path)
        self._refresh_interval: int = refresh_interval_s
        self._timeout: int = timeout
        if verbose:
            logger.setLevel(logging.DEBUG)
        self._verbose: bool = verbose
        self._heart: Process | None = None
        self._is_alive: Event = mp.Event()
        self._terminate_callback: Event = mp.Event()
        self.__settings = settings.to_dict()
        self._config_path: Path = self.__write_settings()
        self._error_callback = error_callback

    def mount(self):  # noqa: DOC502
        """
        Creates a mount point between `local_path` and `remote_path`
        based on the configuration `settings`. The function
        creates and monitors several processes that run in the background
        despite the state of the object. To terminate the background
        processes you will need to use ``unmount``.

        Warning: When the mount process faces a non-recoverable error,
        it terminates the process in which ``mount`` was called.
        As a result, it is recommended you instantiate a dedicated process
        for a ``RemoteMount`` object.

        Raises
        ------
        RuntimeError
            When the mount process dies with an irrecoverable error.
        """
        self._config_path = self.__write_settings()
        lock = mp.Lock()
        lock.acquire(block=True, timeout=self._timeout)
        self._is_alive.set()
        self._terminate_callback.clear()
        self._heart = Process(
            target=_heartbeat,
            args=(
                self._config_path,
                self.local_path,
                self.remote_path,
                self._refresh_interval,
                self._timeout,
                lock,
                self._is_alive,
                self._terminate_callback,
                self._verbose,
            ),
        )

        # It's alive!
        self._heart.start()
        if not lock.acquire(block=True, timeout=self._timeout):
            self.unmount()
            raise RuntimeError("Could not mount on time.")

        def _monitor():
            while self._heart is not None and self._heart.is_alive():
                time.sleep(1)
            self._heart = None
            # If the terminate call-back was not set, means
            # ungraceful exit. We call the error_callback

            terminate()
            if not self._terminate_callback.wait(self._timeout):
                logger.error("Non-recoverable RMount Error. Exiting.")
                if self._error_callback is not None:
                    self._error_callback()
                else:
                    raise RuntimeError("Mount process died.")

        monitor = threading.Thread(target=_monitor)
        monitor.start()

    def is_alive(self, timeout: int | None = None) -> bool:
        """
        Check whether the mount process is alive.

        Parameters
        ----------
        timeout : int | None, optional
            The timeout to apply when checking the
            status of the mounting process, by default None

        Returns
        -------
        bool
            Whether the mount point is active.
        """
        if timeout is None:
            timeout = max(self._timeout, self._refresh_interval)
        return is_alive(self.local_path, timeout=timeout)

    def unmount(self, timeout: int | None = None):
        """
        Tears down the current mount process and kills any
        related background processes gracefully.

        Parameters
        ----------
        timeout : int | None, optional
            The timeout to apply when unmounting and tearing down
            the main processes.

        """
        if timeout is None:
            timeout = self._timeout
        refresh_cache(timeout=1)
        terminate()
        if self._is_alive.is_set():
            self._is_alive.clear()
            self._terminate_callback.wait(timeout=timeout)
        self._terminate_callback.set()
        if (
            hasattr(self, "_heart")
            and self._heart is not None
            and self._heart.is_alive()
        ):
            self._heart.kill()
        if hasattr(self, "local_path"):
            unmount(self.local_path, timeout=timeout)
        for process in active_children():
            process.kill()

    def refresh(self):
        """
        Updates the timestamp file used to signal the health
        of the mount process.
        """
        refresh(
            config_path=self._config_path,
            remote_path=Path(f"{CFG_NAME}:{self.remote_path}"),
            timeout=self._timeout,
        )

    def __write_settings(self):
        tmp_dir = tempfile.gettempdir()
        config_path = Path(tmp_dir) / f"{uuid.uuid4()}-rmount.conf"
        descriptor = os.open(
            path=config_path.as_posix(),
            flags=(
                os.O_WRONLY  # access mode: write only
                | os.O_CREAT  # create if not exists
                | os.O_TRUNC  # truncate the file to zero
            ),
            mode=0o600,
        )

        with open(descriptor, "w", encoding="utf-8") as file:
            file.write(make_config(self.__settings))
        return config_path

    def __enter__(self) -> "RemoteMount":
        self.mount()
        return self

    def __exit__(self, *args, **kwargs):
        self.unmount()
        if (
            self._config_path is not None
            and self._config_path.exists()
        ):
            self._config_path.unlink()

    def __del__(self):
        try:
            if self._config_path is not None:
                self._config_path.unlink()
            self.unmount()
        except Exception:  # pylint: disable=broad-exception-caught
            pass
