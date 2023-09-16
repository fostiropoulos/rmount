# Developer Guide

This guide is meant for those interested in contributing to RMount.

## Installing Development Version of RMount

The development version of RMount can be installed via pip `pip install -e .[dev]`

The `-e` option automatically updates the library's content based on local changes.

## Setting up Docker Environment

Docker is used for mocking a remote SSH server and is required to be installed. For detailed instructions on how to install Docker please refer to the [official documentation](https://docs.docker.com/engine/install/).


## Setting up Docker Enviroment for non-root users

You will need to set-up docker to run in `root-less` mode. For example, the system user that will be executing the tests should be able to execute: `docker run hello-world` without running into errors. For instructions specific to your system please refer to the [official documentation](https://docs.docker.com/engine/install/linux-postinstall/).


## Running Tests

To run tests and static checks you can run the following commands in the root directory of this repository

```bash
$ make static-checks
$ make test
```

