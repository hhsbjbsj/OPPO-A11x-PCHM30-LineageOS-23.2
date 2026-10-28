FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git git-lfs gnupg curl wget \
    python3 python-is-python3 python3-requests python3-protobuf \
    build-essential gcc-multilib g++-multilib \
    flex bison bc gperf zip unzip rsync cpio file patch \
    erofs-utils kmod protobuf-compiler xxd yasm \
    ccache schedtool squashfs-tools lzop pngcrush \
    zlib1g-dev lib32z1-dev libc6-dev-i386 lib32readline-dev \
    libncurses5 libncurses5-dev lib32ncurses5-dev \
    libssl-dev libelf-dev libdw-dev libgnutls28-dev liblz4-tool libsdl1.2-dev \
    x11proto-core-dev libx11-dev libgl1-mesa-dev \
    libxml2 libxml2-dev libxml2-utils xsltproc fontconfig \
    openjdk-17-jdk-headless openssh-server \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fL --retry 5 https://code-server.dev/install.sh \
        -o /tmp/install-code-server.sh \
    && sh /tmp/install-code-server.sh \
    && rm /tmp/install-code-server.sh

RUN curl -fL --retry 5 \
        https://storage.googleapis.com/git-repo-downloads/repo \
        -o /usr/local/bin/repo \
    && chmod 755 /usr/local/bin/repo

RUN git config --system user.name "PCHM30 ROM Builder" \
    && git config --system user.email "builder@example.invalid" \
    && git lfs install --system

# Pinned manifest commit from the official lineage-23.2 branch.
ARG LOS_MANIFEST_REV=9776e518de506f610218c4caa6c1fddff46873af

RUN mkdir -p /opt/lineage \
    && cd /opt/lineage \
    && python3 -c 'import shutil; assert shutil.disk_usage(".").free >= 160 * 2**30, "Insufficient image-build disk space before source download"' \
    && repo init \
        -u https://github.com/LineageOS/android.git \
        -b "${LOS_MANIFEST_REV}" \
        --depth=1 --git-lfs \
    && mkdir -p .repo/local_manifests \
    && printf '%s\n' \
        '<?xml version="1.0" encoding="UTF-8"?>' \
        '<manifest>' \
        '  <project path="prebuilts/vndk/v30" name="platform/prebuilts/vndk/v30" remote="aosp" revision="981aa5282109c68469dadb6cae80a1cf53a58fab" upstream="refs/heads/android14-release" clone-depth="1" />' \
        '</manifest>' > .repo/local_manifests/pchm30-vndk30.xml \
    && repo sync -c -j16 \
        --no-clone-bundle --no-tags --retry-fetches=3 \
    && repo manifest -r -o /opt/lineage/.cnb-source-lock.xml \
    && test -f build/envsetup.sh \
    && test "$(git -C prebuilts/vndk/v30 rev-parse HEAD)" = 981aa5282109c68469dadb6cae80a1cf53a58fab \
    && touch /opt/lineage/.cnb-los23.2-ready

WORKDIR /workspace
