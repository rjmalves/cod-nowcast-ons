# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e
# nwp-core-template: Dockerfile 0.1.0
FROM ghcr.io/astral-sh/uv:0.9.22@sha256:2320e6c239737dc73cccce393a8bb89eba2383d17018ee91a59773df802c20e6 AS uv

FROM python:3.12-slim-trixie@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS builder
ARG BUILD_APT_PACKAGES="gcc libc6-dev"
RUN apt-get update \
    && apt-get install -y --no-install-recommends git $BUILD_APT_PACKAGES \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_NO_CACHE=1
WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
# Known limits of the build secret (security review 1 of TICKET-013):
# - Every process in the two `uv sync` RUNs can read the token, build backends
#   included, and uv.lock does not lock build backends. Use a fine-grained,
#   read-only, single-repository and short-lived token.
# - The helper prints the whole secret file. A file with more than one line
#   puts its later lines in git's stderr, which a failed fetch logs, so the
#   secret must hold the token on one line.
RUN --mount=type=secret,id=nwp_core_token,required=false \
    GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0=credential.https://github.com.helper \
    GIT_CONFIG_VALUE_0='!f() { if [ -f /run/secrets/nwp_core_token ]; then echo username=x-access-token; echo "password=$(cat /run/secrets/nwp_core_token)"; fi; }; f' \
    uv sync --locked --no-dev --no-editable --no-install-project
COPY app/ app/
COPY main.py ./
RUN --mount=type=secret,id=nwp_core_token,required=false \
    GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0=credential.https://github.com.helper \
    GIT_CONFIG_VALUE_0='!f() { if [ -f /run/secrets/nwp_core_token ]; then echo username=x-access-token; echo "password=$(cat /run/secrets/nwp_core_token)"; fi; }; f' \
    uv sync --locked --no-dev --no-editable

FROM python:3.12-slim-trixie@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS runtime
ARG RUNTIME_APT_PACKAGES="libgomp1"
RUN if [ -n "$RUNTIME_APT_PACKAGES" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends $RUNTIME_APT_PACKAGES \
        && rm -rf /var/lib/apt/lists/*; \
    fi
COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    XDG_CONFIG_HOME=/tmp/.config \
    XDG_DATA_HOME=/tmp/.local/share \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
ARG IMAGE_SOURCE
LABEL org.opencontainers.image.source=$IMAGE_SOURCE
USER 10001:10001
# The one required edit: the name of the project's console script.
ENTRYPOINT ["cod-nowcast-ons"]
