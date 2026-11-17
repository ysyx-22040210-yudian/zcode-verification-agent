#!/usr/bin/env bash
set -euo pipefail
base=/home/verification-agent
rootfs="$base/compat/bookworm"
proxy="${VERIFICATION_HTTP_PROXY:-}"
if [ ! -f "$rootfs/.verification-rootfs.json" ]; then
  HTTPS_PROXY="$proxy" https_proxy="$proxy" python3 "$base/compat/install-bookworm.py"
fi
install -d -o host -g host -m 0755 "$base/runtime/build-home" "$base/runtime/profile" "$base/cache/xdg"
if ! grep -q '^host:' "$rootfs/etc/passwd"; then
  printf 'host:x:%s:%s:ZCode Development:%s/runtime/build-home:/bin/bash\n' "$(id -u host)" "$(id -g host)" "$base" >>"$rootfs/etc/passwd"
  printf 'host:x:%s:\n' "$(id -g host)" >>"$rootfs/etc/group"
fi
"$base/compat/bookworm.sh" --root /bin/bash -c '
  set -e
  node -p "process.version"
  apt_source=/etc/apt/sources.list.d/debian.sources
  sed -i "s|http://deb.debian.org|https://deb.debian.org|g" "$apt_source"
  dpkg_options="-o Acquire::ForceIPv4=true -o Acquire::Retries=2"
  apt-get $dpkg_options update -qq
  apt-get $dpkg_options install -y --no-install-recommends \
    dbus dbus-x11 fonts-noto-cjk fonts-noto-color-emoji \
    g++ git libasound2 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 \
    libcairo2 libcups2 libdbus-1-3 libdrm2 libgbm1 libglib2.0-0 libgtk-3-0 \
    libnspr4 libnss3 libpango-1.0-0 libpangocairo-1.0-0 libsecret-1-0 \
    libx11-6 libx11-xcb1 libxcb-dri3-0 libxcomposite1 libxdamage1 libxext6 \
    libxfixes3 libxkbcommon0 libxkbfile1 libxrandr2 libxrender1 libxshmfence1 \
    libxss1 libxtst6 make openssh-client pkg-config procps python3 unzip \
    wget xauth xdg-utils xvfb xz-utils
  npm --fetch-retries=2 install --global pnpm@10.33.2
  pnpm --version
'
printf '%s\n' 'Desktop dependencies prepared'
