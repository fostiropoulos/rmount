# RMount - Robust Remote Mount
![](assets/mount.png)

This is a robust remote mount wrapper around the mount utility [rclone](https://rclone.org/). The python-side implementation makes it possible to integrate rclone into your python application with pre-packaged rclone binaries (version v1.62.2). This is a ready-to-go solution without external dependencies for mounting a local directory to a remote storage provider such as AWS S3. RMount is robust to time-outs, connection drops, while it abstracts the details of integrating directly with the remote provider. **NOTE** Currently only supports Linux.

Philosophy of the library:
1. Monitor
2. Restart when possible
3. Exit Gracefully
4. Fail Loudly

**Storage Systems** currently supported:
* [Google Cloud Storage](https://cloud.google.com/storage) via S3.
* [AWS](https://aws.amazon.com/s3/) via S3.
* Remote SSH, i.e. for your own private server with SSH access
* S3 remote file-systems are supported by several cloud providers [listed below](#providers).

### System Requirements

1. `mountpoint` command should be in PATH
2. `fusermount` command should be in PATH
3. System support for FUSE file system

The above requirements are by default met on most Linux distributions such as Ubuntu.

## Install

`pip install rmount`

* `mountpoint` command must be accessible and in Path. e.g. running `mountpoint .` should return `. is not a mountpoint` or `. is a mountpoint`


## Usage

You will first need to define your configuration object and then you can use `RemoteMount` with a context manager i.e. `with` or simply by calling `.mount()` and `.unmount()`. See below and [s3 example](examples/s3.py), [ssh example](examples/remote_server.py).


<a target="_blank" href="https://colab.research.google.com/github/fostiropoulos/rmount/blob/main/examples/s3.ipynb">
  <img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/>
</a>

### AWS S3 Config

[Set-up your access keys](https://aws.amazon.com/blogs/security/wheres-my-secret-access-key/)

```python
from rmount import S3
config = S3(
    provider="AWS",
    region="us-east-1",
    secret_access_key="xxx",
    access_key_id="xxx",
)
```
### GCS S3 Config
[Set-up your access keys](https://cloud.google.com/storage/docs/authentication/managing-hmackeys)

```
config = S3(
    provider="GCS",
    secret_access_key="xxx",
    access_key_id="xxx",
    endpoint="https://storage.googleapis.com",
)
```

### SSH Remote Config
[Set-up your access keys](https://ubuntu.com/server/docs/service-openssh)


```python
from pathlib import Path
from rmount import Remote
config = Remote(
    host="localhost",
    user="root",
    port=22,
    key_file=Path.home() / ".ssh" / "id_rsa",
)

```

### Writing a file
```python
# local directory
local_path = Path("/tmp/s3")
# remote directory e.g. s3://rmount gs://rmount or /rmount
remote_path = "rmount"
mount = RemoteMount(config, remote_path, local_path)
with mount:
    local_path.joinpath("foo").write_text("bar")
```

## Advanced Usage

You might prefer to not use S3 storage, for several reasons, such as privacy, costs and more. In those cases we support the use of a personal `RemoteServer`.

`pip install rmount[server]`

You will also need Docker installed with root access. Please see [DEVELOPER GUIDE](DEVELOPER.md)
### RemoteServer

RemoteServer is a docker container running an SFTP server. The advantage of using a `RemoteServer` is that you can isolate access between the storage of the mount process and access to more sensitive files. This allows you fine-grained control of file-system access using SSH.



#### Use-case example
Assume you use `rmount` for the experiment You might want to provide access to the storage of the experiment data to several people you trust enough to get access to experiment data, e.g. `ABLATOR` dashboard, but at the same time you might not want them to be able to `ssh` into your main machine to have access to your personal files.

```python
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
```

A full example can be found [HERE](examples/remote_server.py)
## Known Issue

Because the monitoring of the mount process happens in the background and is monitored via threads and processes. The background threads / processes are run async to the main process and are used to restart the mount process and eventually gracefully exit. When an application dies or is killed for x,y,z reason the graceful clean-up, such as unmounting might not take place. As such you can have a mount process running on the background. The problem can not be addressed from within the library as this depends on many OS related factors. For example, a new process is spawned and if `SIG_KILL` is received for one process it is not possible to detect from within python or attempt a clean-up as such all other background processes will remain alive.


**In summary**

if you `SIG_KILL` a python application using `rmount` you *might* also need to manually clean-up after yourself any remaining background processes e.g. `rclone` or they will use memory and compute.

## Developer guide
Full details [HERE](DEVELOPER.md)
```bash
$ pip install -e .[dev]
$ make test
```

Currently there is no support for Mac or Windows as they require multiple additional steps to install mount. It is not viable for the [main developer of this project](https://iordanis.me) to support these systems. If you are interested in writing code to support additional OS. You should find a way to replace the command line utility depedencies listed above.

`mountpoint` command checks whether a directory is a mount point and `fusermount` command unmounts a directory. As long as robust alternatives can be found and packaged in this repo or documentation provided for them it should be sufficient for the same library to work on any OS. Additionally, the OS must support FUSE filesystem, e.g. [WinFsp](https://winfsp.dev/) or [macFUSE](https://osxfuse.github.io/).

## <a name="providers"></a> S3 Remote Storage Providers

In theory, RMount support all [the providers supported by rclone](https://rclone.org/overview/), but you will need to implement your own configuration object. We have only tested with AWS S3 but in *theory* it should work with all providers:
* AWS S3
* Alibaba Cloud (Aliyun) Object Storage System (OSS)
* Ceph
* China Mobile Ecloud Elastic Object Storage (EOS)
* Cloudflare R2
* Arvan Cloud Object Storage (AOS)
* DigitalOcean Spaces
* Dreamhost
* GCS
* Huawei OBS
* IBM COS S3
* IDrive e2
* IONOS Cloud
* Liara Object Storage
* Minio
* Petabox
* Qiniu Cloud Object Storage (Kodo)
* RackCorp Object Storage
* Scaleway
* Seagate Lyve Cloud
* SeaweedFS
* StackPath
* Storj
* Tencent Cloud Object Storage (COS)
* Wasabi



