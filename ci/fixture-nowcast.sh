#!/usr/bin/env bash
# Usage: ci/fixture-nowcast.sh IMAGE (an image ID, a tag, or a name@digest)
#
# Runs IMAGE on the committed fixture frames, offline, read-only and without
# capabilities. The import check alone passes on an image that crashes here,
# because pysteps imports cv2 lazily.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 IMAGE" >&2
  exit 2
fi
root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
exec docker run --rm --network none --read-only --tmpfs /tmp --cap-drop ALL \
  --user 54321:54321 \
  --mount "type=bind,src=$root/tests/fixtures/data,dst=/fixtures,readonly" \
  --mount "type=bind,src=$root/ci,dst=/ci,readonly" \
  "$1" --config /ci/fixture-nowcast.jsonc
