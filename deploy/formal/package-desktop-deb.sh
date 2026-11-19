#!/bin/sh
# Wrap the verified electron-builder Linux directory as a separately named offline desktop package.
set -eu
app=$(realpath -- "${1:?Pass the linux-unpacked directory}")
output=$(realpath -m -- "${2:?Pass the output .deb path}")
version=${3:-3.18.2+formal1}
binary=$(find "$app" -maxdepth 1 -type f \( -name zcode -o -name zcode-preview \) -printf '%f\n')
case "$binary" in zcode|zcode-preview) ;; *) echo "Missing ZCode executable" >&2; exit 2 ;; esac
test -f "$app/resources/app.asar"
test -x "$app/resources/verification-formal/formal-toolchain/python/bin/python3.11"
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
prefix=/opt/zcode-verification-agent
install -d "$stage/DEBIAN" "$stage$prefix" "$stage/usr/bin" "$stage/usr/share/applications"
cp -a "$app/." "$stage$prefix/"
chmod -R go-w "$stage$prefix"
cat >"$stage/DEBIAN/control" <<EOF
Package: zcode-verification-agent
Version: $version
Architecture: amd64
Maintainer: ZCode Verification Agent contributors
Section: electronics
Priority: optional
Depends: libc6 (>= 2.28), libgtk-3-0 | libgtk-3-0t64, libnss3, libasound2 | libasound2t64, libxss1, libxtst6, libgbm1, libdrm2, libsecret-1-0, libxkbcommon0, libatk-bridge2.0-0 | libatk-bridge2.0-0t64, libcups2 | libcups2t64
Description: ZCode verification desktop with local SystemVerilog Formal tools
 Includes the Yosys, SMTBMC and Z3 toolchain, FIFO project and commercial adapter interface.
EOF
cat >"$stage/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -eu
# Electron uses its distributed root-owned sandbox on hosts without unprivileged user namespaces.
if runuser -u nobody -- unshare -Ur true >/dev/null 2>&1; then
  chmod 0755 /opt/zcode-verification-agent/chrome-sandbox
else
  chmod 4755 /opt/zcode-verification-agent/chrome-sandbox
fi
EOF
chmod 0755 "$stage/DEBIAN/postinst"
cat >"$stage/usr/bin/zcode-verification-agent" <<EOF
#!/bin/sh
set -eu
if [ "\$#" -eq 0 ]; then
  set -- "--open-workspace=$prefix/resources/verification-formal/fifo"
elif [ "\$#" -eq 1 ] && [ -d "\$1" ]; then
  set -- "--open-workspace=\$(realpath -- "\$1")"
fi
exec "$prefix/$binary" "\$@"
EOF
chmod 0755 "$stage/usr/bin/zcode-verification-agent"
cat >"$stage/usr/share/applications/zcode-verification-agent.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=ZCode Verification Agent
Name[zh_CN]=ZCode 验证 Agent
Exec=zcode-verification-agent
Icon=$prefix/resources/icon_512x512.png
Terminal=false
Categories=Development;Electronics;
EOF
mkdir -p "$(dirname -- "$output")"
dpkg-deb --root-owner-group -Zgzip -z4 --build "$stage" "$output"

