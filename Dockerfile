FROM continuumio/miniconda3:latest
RUN groupadd -r admin \
  && useradd -r -g admin admin
WORKDIR /usr/src/app



LABEL maintainer="mail@iordanis.me"
LABEL description="Running environment for RMount"

RUN apt-get update
RUN apt-get install -y openssh-server rsync fuse
RUN apt-get install -y fuse3
RUN apt-get install -y gcc python3-dev build-essential


RUN ssh-keygen -t rsa -f ~/.ssh/id_rsa -q -N ""
RUN cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
RUN conda update -y conda
ARG PY_VERSION=3.10.12
RUN conda install -y python=$PY_VERSION pip


COPY ./setup.py ./setup.py
COPY ./README.md ./README.md
COPY ./linux ./linux
COPY ./rmount/__init__.py ./rmount/__init__.py
RUN pip install -e .[dev]
COPY . .

RUN chmod a+x ./scripts/docker-entrypoint.sh
ENTRYPOINT ["./scripts/docker-entrypoint.sh"]
EXPOSE 22
CMD ["pytest","."]
