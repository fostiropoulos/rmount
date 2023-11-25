
Usage
=====

You will first need to define your configuration object and then you can use `RemoteMount` with a context manager i.e. `with` or simply by calling `.mount()` and `.unmount()`. See below and

* `s3 example`_
* `ssh example`_

.. _s3 example: https://github.com/fostiropoulos/rmount/blob/main/examples/s3.py
.. _ssh example: https://github.com/fostiropoulos/rmount/blob/main/examples/remote_server.py

.. raw:: html

    <a target="_blank" href="https://colab.research.google.com/github/fostiropoulos/rmount/blob/main/examples/s3.ipynb">
    <img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/>
    </a>


`AWS S3 Config Instructions`_

.. code-block:: python

    from rmount import S3
    config = S3(
        provider="AWS",
        region="us-east-1",
        secret_access_key="xxx",
        access_key_id="xxx",
    )


`GCS S3 Config Instructions`_


.. code-block:: python

    config = S3(
        provider="GCS",
        secret_access_key="xxx",
        access_key_id="xxx",
        endpoint="https://storage.googleapis.com",
    )

`SSH Remote Config Instructions`_


.. code-block:: python

    from pathlib import Path
    from rmount import Remote
    config = Remote(
        host="localhost",
        user="root",
        port=22,
        key_file=Path.home() / ".ssh" / "id_rsa",
    )

Example
------

.. code-block:: python

    # local directory
    local_path = Path("/tmp/s3")
    # remote directory e.g. s3://rmount gs://rmount or /rmount
    remote_path = "rmount"
    mount = RemoteMount(config, remote_path, local_path)
    with mount:
        local_path.joinpath("foo").write_text("bar")



.. _AWS S3 Config Instructions: https://aws.amazon.com/blogs/security/wheres-my-secret-access-key/
.. _GCS S3 Config Instructions: https://cloud.google.com/storage/docs/authentication/managing-hmackeys
.. _SSH Remote Config Instructions: https://ubuntu.com/server/docs/service-openssh