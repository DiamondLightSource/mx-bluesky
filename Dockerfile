# The devcontainer should use the developer target and run as root with podman
# or docker with user namespaces.
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION} AS developer

# Add any system dependencies for the developer/build environment here
RUN apt-get update && apt-get install -y --no-install-recommends \
    graphviz \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Set up a virtual environment and put it in PATH
RUN python -m venv /venv
ENV PATH=/venv/bin:$PATH

# The build stage installs the context into the venv
FROM developer AS build
# Requires buildkit 0.17.0
COPY --chmod=o+wrX . /workspaces/mx-bluesky
WORKDIR /workspaces/mx-bluesky
RUN touch dev-requirements.txt && pip install -c dev-requirements.txt .


FROM build AS debug


# Set origin to use ssh
RUN git remote set-url origin git@github.com:DiamondLightSource/mx-bluesky.git


# For this pod to understand finding user information from LDAP
RUN apt update
RUN DEBIAN_FRONTEND=noninteractive apt install libnss-ldapd -y
RUN sed -i 's/files/ldap files/g' /etc/nsswitch.conf

# Make editable and debuggable
RUN pip install debugpy
RUN pip install -e .

# Alternate entrypoint to allow devcontainer to attach
ENTRYPOINT [ "/bin/bash", "-c", "--" ]
CMD [ "while true; do sleep 30; done;" ]


# The runtime stage copies the built venv into a slim runtime container
FROM python:${PYTHON_VERSION}-slim AS runtime
# Add apt-get system dependecies for runtime here if needed
COPY --from=build /venv/ /venv/
ENV PATH=/venv/bin:$PATH

# change this entrypoint if it is not the same as the repo
ENTRYPOINT ["mx-bluesky"]
CMD ["--version"]
