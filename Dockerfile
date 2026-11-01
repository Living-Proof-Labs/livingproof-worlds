# SPDX-License-Identifier: Apache-2.0
# Base image and uv pins follow livingproof-sim-mujoco at the time of writing; this image installs
# only git, curl and Task. Optional APT_MIRROR (empty by default) replaces deb.debian.org.
ARG PYTHON_IMAGE=python:3.11.14-slim-bookworm@sha256:65a93d69fa75478d554f4ad27c85c1e69fa184956261b4301ebaf6dbb0a3543d
FROM ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 AS uv-tools
FROM ${PYTHON_IMAGE} AS development
ARG APT_MIRROR=
COPY --from=uv-tools /uv /uvx /usr/local/bin/
RUN sed -i "s|http://deb.debian.org|${APT_MIRROR:-https://deb.debian.org}|g" /etc/apt/sources.list.d/debian.sources && apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates && rm -rf /var/lib/apt/lists/*
ARG TASK_VERSION=3.54.0
RUN set -eu; \
    arch="$(dpkg --print-architecture)"; mkdir /tmp/task; cd /tmp/task; \
    curl --connect-timeout 15 --max-time 120 -fsSLO "https://github.com/go-task/task/releases/download/v${TASK_VERSION}/task_linux_${arch}.tar.gz"; \
    curl --connect-timeout 15 --max-time 120 -fsSLO "https://github.com/go-task/task/releases/download/v${TASK_VERSION}/task_checksums.txt"; \
    sha256sum --ignore-missing -c task_checksums.txt; \
    tar -xzf "task_linux_${arch}.tar.gz" task; install task /usr/local/bin/task; rm -rf /tmp/task
ENV LIVINGPROOF_TOOLING=1
ENV UV_PROJECT_ENVIRONMENT=/opt/worlds-venv UV_CACHE_DIR=/opt/worlds-cache UV_PYTHON_DOWNLOADS=never UV_SYSTEM_CERTS=true
RUN mkdir /opt/worlds-venv /opt/worlds-cache && chmod 1777 /opt/worlds-venv /opt/worlds-cache
RUN groupadd --gid 1000 vscode && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash vscode
WORKDIR /workspace/worlds
CMD ["sleep", "infinity"]
