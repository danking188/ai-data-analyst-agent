#!/bin/sh
set -eu

data_root="${DATA_ROOT:-/mnt/workspace/data}"
cache_root="${STORAGE_CACHE_ROOT:-/tmp/datatrace-storage-cache}"

case "$data_root" in
    /mnt/workspace | /mnt/workspace/*) ;;
    *)
        echo "DATA_ROOT must be /mnt/workspace or a child directory" >&2
        exit 1
        ;;
esac

case "$cache_root" in
    /tmp/datatrace-storage-cache | /tmp/datatrace-storage-cache/*) ;;
    *)
        echo "STORAGE_CACHE_ROOT must be /tmp/datatrace-storage-cache or a child directory" >&2
        exit 1
        ;;
esac

# ModelScope mounts /mnt/workspace at runtime, replacing image-layer ownership.
# Prepare only the two validated application roots, then immediately drop privileges.
mkdir -p "$data_root" "$cache_root"
chown -R app:app "$data_root" "$cache_root"

exec gosu app "$@"
