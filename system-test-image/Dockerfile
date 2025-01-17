FROM ubuntu:latest AS build

ARG DEBIAN_FRONTEND=noninteractive
ARG RUNNER_VERSION="2.321.0"

RUN apt update -y && apt upgrade -y && useradd -m docker
RUN apt install -y \
    curl 

RUN  cd /home/docker && \
     mkdir actions-runner && \
     cd actions-runner && \
     curl -o actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz\
     -L https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz && \
     tar xzf ./actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz 

# .NET 6 Linux package dependencies from
# https://github.com/dotnet/core/blob/main/release-notes/6.0/linux-packages.md#ubuntu-2404-noble
RUN apt-get install -y --no-install-recommends \
    libc6 \
    libgcc-s1 \
    libicu74 \
    libssl3 \
    libstdc++6 \
    zlib1g

COPY start.sh /home/docker/actions-runner/start.sh

RUN chown -R docker ~docker

# Needed for fetching live registration tokens
RUN apt install -y jq
# Needed for decent version of git for actions/checkout github action
RUN apt install -y git 
# Needed for pytest coverage
RUN apt install -y libsqlite3-0
# Needed for python cv2 dependency
RUN apt install -y libgl1 libglib2.0-0

USER docker
WORKDIR /home/docker/actions-runner
ENTRYPOINT ["./start.sh"]
