#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Same wrapper as livingproof-sim-mujoco: the development image marks its
# prepared toolchain explicitly; do not infer it from Docker availability.
set -euo pipefail
if [[ ${LIVINGPROOF_TOOLING:-} == 1 ]]; then
  exec task -t Taskfile.runtime.yml "$@"
fi
if ! command -v docker >/dev/null; then
  echo 'Host tasks require Docker. Inside an already prepared environment use: task -t Taskfile.runtime.yml setup (then verify).' >&2
  exit 1
fi
args=(compose run --rm)
[[ $1 != setup ]] || args+=(--build)
exec docker "${args[@]}" tooling task -t Taskfile.runtime.yml "$@"
