Advanced Usage
==============

You might prefer to **not** use S3 storage, for several reasons, such as privacy, costs and more. In those cases we support the use of a personal ``RemoteServer``.

.. code-block:: bash

    pip install rmount[server]

You will also need Docker installed with root access. Please see `DEVELOPER GUIDE`_

RemoteServer
------------

RemoteServer is a docker container running an SFTP server. The advantage of using a ``RemoteServer`` is that you can isolate access between the storage of the mount process and access to more sensitive files. This allows you fine-grained control of file-system access using SSH.



Use-case example
^^^^^^^^^^^^^^^^
Assume you use ``rmount`` for the experiment You might want to provide access to the storage of the experiment data to several people you trust enough to get access to experiment data, e.g. ``ABLATOR`` dashboard, but at the same time you might not want them to be able to ``ssh`` into your main machine to have access to your personal files.

.. code-block:: python

    from rmount.server import RemoteServer
    from pathlib import Path
    public_key = Path.home() / ".ssh" / "id_rsa.pub"
    private_key = Path.home() / ".ssh" / "id_rsa"
    local_path = Path("/tmp/")

    server = RemoteServer(
        local_path=local_path,
        remote_path=remote_path,
        public_key=public_key,
    )
    server.start()

    config = Remote(
        host=server.ip_address,
        user=server.user,
        port=server.port,
        key_file=private_key,
    )
    mount = RemoteMount(config, remote_path, local_path)
    with mount:
        local_path.joinpath("foo").write_text("bar")

    print(server.ssh_command)

A full example can be found `REMOTE EXAMPLE`_


Known Issue
^^^^^^^^^^^

Because the monitoring of the mount process happens in the background and is monitored via threads and processes. The background threads / processes are run async to the main process and are used to restart the mount process and eventually gracefully exit. When an application dies or is killed for x,y,z reason the graceful clean-up, such as unmounting might not take place. As such you can have a mount process running on the background. The problem can not be addressed from within the library as this depends on many OS related factors. For example, a new process is spawned and if ``SIG_KILL`` is received for one process it is not possible to detect from within python or attempt a clean-up as such all other background processes will remain alive.


**Summary**

if you ``SIG_KILL`` a python application using ``rmount`` you *might* also need to manually clean-up after yourself any remaining background processes e.g. ``rclone`` or they will use memory and compute.


Developer guide
^^^^^^^^^^^^^^^

Full details [HERE](DEVELOPER.md)

.. code-block:: bash

    $ pip install -e .[dev]
    $ make test

Currently there is no support for Mac or Windows as they require multiple additional steps to install mount. It is not viable for the `main developer of this project`_ to support these systems. If you are interested in writing code to support additional OS. You should find a way to replace the command line utility depedencies listed above.

`mountpoint` command checks whether a directory is a mount point and ``fusermount`` command unmounts a directory. As long as robust alternatives can be found and packaged in this repo or documentation provided for them it should be sufficient for the same library to work on any OS. Additionally, the OS must support FUSE filesystem, e.g. `WinFsp`_ or `macFUSE`_.



.. _DEVELOPER GUIDE: https://github.com/fostiropoulos/rmount/blob/main/DEVELOPER.md
.. _WinFsp: https://winfsp.dev/
.. _macFUSE: https://osxfuse.github.io/
.. _main developer of this project: https://iordanis.me
.. _REMOTE EXAMPLE: https://github.com/fostiropoulos/rmount/blob/main/examples/remote_server.py