#!/usr/bin/env bash
# Executes ONLY inside an explicitly approved Packer build, never on the laptop.
set -euo pipefail
cd /tmp/lightyear-bundle
python3 /tmp/check_cloud_image_bundle.py --root . --manifest-sha256 "$BUNDLE_MANIFEST_SHA256"
# All OS package dependencies must be in the reviewed offline .deb set.
sudo dpkg --install ./debs/*.deb
sudo mkdir -p /opt/lightyear/jdk /opt/lightyear/docker /opt/lightyear/venv
sudo tar --extract --gzip --file jdk21.tar.gz --directory /opt/lightyear/jdk --strip-components=1
sudo tar --extract --gzip --file docker-static.tgz --directory /opt/lightyear/docker --strip-components=1
sudo python3 -m venv /opt/lightyear/venv
sudo /opt/lightyear/venv/bin/python -m pip install --no-index --find-links wheels --require-hashes -r requirements.lock
sudo cp manifest.json /opt/lightyear/image-bundle-manifest.json
sudo /opt/lightyear/jdk/bin/java -version
sudo /opt/lightyear/docker/docker --version
sudo /opt/lightyear/venv/bin/python --version
# No daemon, container, model or campaign starts during the image build.
# Phase 2 adds and reviews the boot agent before sealed operation.
