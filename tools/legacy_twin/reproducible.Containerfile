# Exact amd64 Ubuntu 24.04 manifest resolved from the official registry 2026-10-11.
FROM ubuntu@sha256:f610ab94648195aa356059f5b41d6085c9d4d903c072430cdd1af7bdb646106b
# Pin transitive build packages as well as the four checksum-pinned COBOL packages.
RUN sed -i -E 's@http://(archive|security).ubuntu.com/ubuntu/?@http://snapshot.ubuntu.com/ubuntu/20261001T000000Z/@g' /etc/apt/sources.list.d/ubuntu.sources \
 && printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99snapshot \
 && apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates curl python3 sudo
COPY tools/legacy_twin/install-pinned.sh /tmp/install-pinned.sh
RUN bash /tmp/install-pinned.sh && rm /tmp/install-pinned.sh
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC PYTHONDONTWRITEBYTECODE=1
