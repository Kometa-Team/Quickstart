# syntax=docker/dockerfile:1
#
# Multi-stage build for Quickstart.
#
# Stage 1 (jsbuild) runs the Vite bundle so shipped images serve
# hashed, minified, cache-busted JS from /static/dist/. Runs on
# ``$BUILDPLATFORM`` -- the platform doing the build -- rather than
# ``$TARGETPLATFORM``. That means arm64 and arm7 image builds do the
# Node work natively on the amd64 build host instead of under qemu
# emulation, cutting build time from minutes to seconds.
#
# Stage 2 is the runtime image: Python 3.13 + Kometa's runtime deps.
# It gets /static/dist/ copied in from the jsbuild stage, so the
# ``asset_url()`` Jinja helper (see modules/helpers/_vite_manifest.py)
# resolves the manifest at request time and serves optimized bundles.
#
# If ``static/dist/`` is missing, ``asset_url()`` transparently falls
# back to /static/local-js/*.js -- so the app still boots even in
# scenarios like ``docker run`` from a pre-multi-stage image or a
# non-shipping environment. But that fallback is not what shipped
# images should hit; the copy below is the load-bearing part.

# ---- Stage 1: Build the JS bundles ---------------------------------
FROM --platform=$BUILDPLATFORM node:22-slim AS jsbuild
WORKDIR /jsbuild

# Copy only the files needed for the JS build. This keeps the layer
# cache warm across changes to Python code / templates -- unless
# package*.json or the JS sources change, this stage is a cache hit.
COPY package.json package-lock.json vite.config.js vite.detectModuleEntry.mjs ./
COPY static/local-js/ ./static/local-js/

# npm ci is stricter than npm install: fails on any lockfile drift.
# That's what we want for reproducible builds.
RUN npm ci --no-fund --no-audit \
 && npm run build

# ---- Stage 2: Runtime image ----------------------------------------
FROM python:3.13-slim
ARG BRANCH_NAME=master
ENV BRANCH_NAME=${BRANCH_NAME}
ENV TINI_VERSION=v0.19.0
ENV QUICKSTART_DOCKER=True
COPY requirements.txt requirements.txt
RUN echo "**** install system packages ****" \
 && apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get install -y tzdata --no-install-recommends \
 && apt-get install -y gcc g++ libxml2-dev libxslt-dev libz-dev libjpeg62-turbo-dev zlib1g-dev wget curl ffmpeg libsm6 libxext6 \
 && wget -O /tini https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini-"$(dpkg --print-architecture | awk -F- '{ print $NF }')" \
 && chmod +x /tini
RUN echo "**** install python packages ****" \
 && pip3 install --no-cache-dir --upgrade --requirement /requirements.txt
RUN echo "**** cleanup system packages ****" \
 && apt-get --purge autoremove gcc g++ libxml2-dev libxslt-dev libz-dev -y \
 && apt-get clean \
 && apt-get update \
 && apt-get check \
 && apt-get -f install \
 && apt-get autoclean \
 && rm -rf /requirements.txt /tmp/* /var/tmp/* /var/lib/apt/lists/*
COPY . /
# Copy the Vite build output from the jsbuild stage. This overwrites
# any /static/dist/ that snuck in from the host (the .dockerignore
# `**/dist` rule should prevent that, but this line makes the source
# of truth unambiguous). Placed AFTER the whole-repo COPY so it wins
# in the final image.
COPY --from=jsbuild /jsbuild/static/dist/ /static/dist/
VOLUME /config
ENTRYPOINT ["/tini", "-s", "python3", "quickstart.py", "--"]
