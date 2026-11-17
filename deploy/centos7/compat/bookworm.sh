#!/usr/bin/env bash
set -euo pipefail
base=/home/verification-agent
rootfs="$base/compat/bookworm"
if [ "$(id -u)" != 0 ]; then
  echo "This launcher needs root to set up private mounts." >&2
  exit 2
fi
if [ "${1:-}" != --private-mounts ]; then
  exec unshare -m /bin/bash "$0" --private-mounts "$@"
fi
shift
mount --make-rprivate /
test -f "$rootfs/.verification-rootfs.json"

mount -t proc proc "$rootfs/proc"
mount --bind /dev "$rootfs/dev"
mount --bind /dev/pts "$rootfs/dev/pts"
mount --bind /dev/shm "$rootfs/dev/shm"
for file in hosts resolv.conf; do
  touch "$rootfs/etc/$file"
  mount --bind "/etc/$file" "$rootfs/etc/$file"
  mount -o remount,bind,ro "$rootfs/etc/$file"
done
for name in zcode fifo runner cache runtime artifacts evidence probes; do
  if [ -d "$base/$name" ]; then
    install -d "$rootfs$base/$name"
    mount --bind "$base/$name" "$rootfs$base/$name"
  fi
done
if [ -n "${VERIFICATION_WORKSPACE:-}" ]; then
  target="$(readlink -f -- "$VERIFICATION_WORKSPACE")"
  case "$target" in
    "$base/fifo"|"$base/zcode") ;;
    *)
      test "$target" != /
      destination="$(readlink -m -- "$rootfs$target")"
      case "$destination" in "$rootfs/"*) ;; *) exit 2 ;; esac
      install -d "$destination"
      mount --bind "$target" "$destination"
      ;;
  esac
fi
if [ -d /tmp/.X11-unix ]; then
  install -d -m 1777 "$rootfs/tmp/.X11-unix"
  mount --bind /tmp/.X11-unix "$rootfs/tmp/.X11-unix"
fi
authority=
if [ -n "${XAUTHORITY:-}" ] && [ -f "$XAUTHORITY" ]; then
  authority=/tmp/verification-Xauthority
  touch "$rootfs$authority"
  mount --bind "$XAUTHORITY" "$rootfs$authority"
  mount -o remount,bind,ro "$rootfs$authority"
fi

proxy="${VERIFICATION_HTTP_PROXY:-}"
declare -a common=(PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C.UTF-8
  "http_proxy=$proxy" "https_proxy=$proxy" "HTTPS_PROXY=$proxy" "HTTP_PROXY=$proxy"
  no_proxy=127.0.0.1,localhost,::1 NO_PROXY=127.0.0.1,localhost,::1
  CI=1 HUSKY=0 "XDG_CACHE_HOME=$base/cache/xdg" "ZCODE_DATA_BASE_DIR=$base/runtime/profile"
  "DISPLAY=${DISPLAY:-}" "XAUTHORITY=$authority")
if [ "${1:-}" = --root ]; then
  shift
  exec chroot "$rootfs" /usr/bin/env -i HOME=/root "${common[@]}" "$@"
fi
uid="$(id -u host)"
gid="$(id -g host)"
exec chroot "$rootfs" /usr/bin/setpriv --reuid="$uid" --regid="$gid" --clear-groups /usr/bin/env -i \
  "HOME=$base/runtime/build-home" USER=host LOGNAME=host "${common[@]}" "$@"
