
Welcome to RMount's documentation!
==================================


.. image:: _static/mount.png
    :align: center


Welcome to RMount's documentation. Get started by reading our :doc:`install`
and then get an overview with the :doc:`usage`.

RMount was developed for `ABLATOR`_ be sure to check the project's documentation.


RMount is a robust remote mount wrapper around the mount utility `rclone`_ . The python-side implementation makes it possible to integrate rclone into your python application with pre-packaged rclone binaries (version v1.62.2). This is a ready-to-go solution without external dependencies for mounting a local directory to a remote storage provider such as AWS S3. RMount is robust to time-outs, connection drops, while it abstracts the details of integrating directly with the remote provider. **NOTE** Currently only supports Linux.

Philosophy of the library:

1. Monitor

2. Restart when possible

3. Exit Gracefully

4. Fail Loudly


.. _ABLATOR: https://ablator.org
.. _rclone: https://rclone.org/

Navigate
--------

.. toctree::
    :maxdepth: 2

    Source <https://github.com/fostiropoulos/rmount>
    install
    usage
    advanced_usage
    providers
    api

