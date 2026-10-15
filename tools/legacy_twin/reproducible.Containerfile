# Exact amd64 Ubuntu 24.04 manifest resolved from the official registry 2026-10-11.
FROM ubuntu@sha256:f610ab94648195aa356059f5b41d6085c9d4d903c072430cdd1af7bdb646106b
# The minimal base has no CA bundle. Bootstrap verified public CA bytes without
# disabling TLS verification or installing anything on the operator host.
ADD --checksum=sha256:641de77d8f142cfd62a1a6f964ba67b20754d3337c480efb529d086075a06c9a https://snapshot.ubuntu.com/ubuntu/20240501T000000Z/pool/main/c/ca-certificates/ca-certificates_20240203_all.deb /tmp/bootstrap-ca.deb
RUN dpkg-deb -x /tmp/bootstrap-ca.deb /tmp/bootstrap-ca \
 && mkdir -p /etc/ssl/certs \
 && cat /tmp/bootstrap-ca/usr/share/ca-certificates/mozilla/*.crt > /etc/ssl/certs/ca-certificates.crt \
 && rm -r /tmp/bootstrap-ca /tmp/bootstrap-ca.deb
# Pin transitive build packages as well as the four checksum-pinned COBOL packages.
RUN sed -i -E 's@http://(archive|security).ubuntu.com/ubuntu/?@https://snapshot.ubuntu.com/ubuntu/20261001T000000Z/@g' /etc/apt/sources.list.d/ubuntu.sources \
 && printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\nAcquire::http::Timeout "30";\nAcquire::https::Timeout "30";\nAPT::Update::Error-Mode "any";\n' > /etc/apt/apt.conf.d/99snapshot \
 && apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates curl python3 sudo
COPY tools/legacy_twin/install-pinned.sh /tmp/install-pinned.sh
RUN bash /tmp/install-pinned.sh && rm /tmp/install-pinned.sh
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC PYTHONDONTWRITEBYTECODE=1
