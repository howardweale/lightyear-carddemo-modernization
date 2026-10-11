#!/usr/bin/env bash
# Ubuntu 24.04 amd64 only. SHA256s from the immutable 2024-05-01 noble index.
set -euo pipefail
[[ $(dpkg --print-architecture) == amd64 ]]
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]]
snapshot=https://snapshot.ubuntu.com/ubuntu/20240501T000000Z
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
packages=(gnucobol3 libcob4-dev libcob4t64 libfaketime)
versions=(3.1.2-5.1ubuntu1 3.1.2-5.1ubuntu1 3.1.2-5.1ubuntu1 0.9.10-2.1)
paths=(pool/universe/g/gnucobol3 pool/universe/g/gnucobol3 pool/universe/g/gnucobol3 pool/universe/f/faketime)
hashes=(3706d30bb9fb37473911e12888addee0132d38428520139683da289ea8bfd399 089b2e1c43ae7bc83e8fdbbeed2d60537c462c834ad67946755067c0265cec93 664d91e5d7b6219126e6255d7d1f99a9d232206d027005ecf5719dca3674923f 25fc8987f1f700c58603f68edd93ac03a1b7dea35da1e84509f29f444d5b11e9)
for i in "${!packages[@]}"; do
  name=${packages[$i]}_${versions[$i]}_amd64.deb
  if [[ ${TWIN_FORCE_SNAPSHOT:-0} == 1 ]] || ! curl -fL --retry 2 --max-time 90 "https://archive.ubuntu.com/ubuntu/${paths[$i]}/$name" -o "$stage/$name"; then
    curl -fL --retry 2 --max-time 90 "$snapshot/${paths[$i]}/$name" -o "$stage/$name"
  fi
  echo "${hashes[$i]}  $stage/$name" | sha256sum --check --strict
 done
sudo apt-get update
sudo apt-get install -y --no-install-recommends "$stage/"*.deb
for i in "${!packages[@]}"; do
  [[ $(dpkg-query -W -f='${Version}' "${packages[$i]}") == "${versions[$i]}" ]]
done
