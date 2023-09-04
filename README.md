# RMount - Robust Remote Mount


This is a robust remote mount wrapper around the mount utility [rclone](https://rclone.org/). The python-side implementation makes it possible to integrate rclone into your python application with pre-packaged rclone binaries (version v1.62.2). This is a ready-to-go solution without external dependencies for mounting a local directory to a remote storage provider such as AWS S3. RMount is robust to time-outs, connection drops, while it abstracts the details of integrating directly with the remote provider. **NOTE** Currently only supports Linux.


**Storage Systems** currently supported:
* [Google Cloud Storage](https://cloud.google.com/storage) via S3.
* [AWS](https://aws.amazon.com/s3/) via S3.
* Remote SSH, i.e. for your own private server with SSH access
* S3 remote file-systems are supported by several cloud providers [listed below](#providers).

## Install

`pip install rmount`

* `mountpoint` command must be accessible and in Path. e.g. running `mountpoint .` should return `. is not a mountpoint` or `. is a mountpoint`


## Usage

You will first need to define your configuration object and then you can use `RemoteMount` with a context manager i.e. `with` or simply by calling `.mount()` and `.unmount()`. See below and [example](examples/run.py).
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



## Developer guide
Full details [HERE](DEVELOPER.md)
```bash
$ pip install -e .[dev]
$ make test
```


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



