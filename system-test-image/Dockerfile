FROM python:3.11 AS build

ARG DEBIAN_FRONTEND=noninteractive

RUN apt update -y && apt upgrade -y

## Needed for decent version of git for actions/checkout github action
#RUN apt install -y git 
# Needed for pytest coverage
RUN apt install -y libsqlite3-0
# Needed for python cv2 dependency
RUN apt install -y libgl1 libglib2.0-0

COPY start.sh /build/start.sh
COPY ispyb-test-credentials.cfg /dls_sw/dasc/mariadb/credentials/ispyb-hyperion-dev.cfg

#WORKDIR /home/docker/actions-runner
ENTRYPOINT ["/bin/bash"]
