#!/usr/bin/env bash
# Usage: ci/fixture-nowcast.sh IMAGE (an image ID, a tag, or a name@digest)
#
# Materializes the fixture frames from their committed text source inside
# IMAGE, then runs IMAGE on them, offline, read-only and without
# capabilities. The import check alone passes on an image that crashes here,
# because pysteps imports cv2 lazily.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 IMAGE" >&2
  exit 2
fi
root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
frames="$(mktemp -d)"
trap 'rm -rf -- "$frames"' EXIT
# mktemp creates the folder as 0700, and the nowcast reads it as another user.
chmod 0755 "$frames"

docker run --rm --network none --read-only --tmpfs /tmp --cap-drop ALL \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$root/tests/fixtures/goes_cod,dst=/goes_cod,readonly" \
  --mount "type=bind,src=$frames,dst=/frames" \
  --entrypoint python "$1" /goes_cod/materialize.py /frames

docker run --rm --network none --read-only --tmpfs /tmp --cap-drop ALL \
  --user 54321:54321 \
  --mount "type=bind,src=$frames,dst=/fixtures,readonly" \
  --mount "type=bind,src=$root/ci,dst=/ci,readonly" \
  "$1" nowcast --config /ci/fixture-nowcast.toml
