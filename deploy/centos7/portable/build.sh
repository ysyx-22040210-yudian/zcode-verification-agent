#!/usr/bin/env bash
# Build inside Debian 12 amd64 using a clean Bookworm guest root and a packaged Linux desktop.
set -euo pipefail
src=$(cd -- "$(dirname -- "$0")" && pwd -P)
app=$(realpath -- "${1:?linux-unpacked directory}")
sysroot=$(realpath -- "${2:?clean Debian guest sysroot}")
kernel_deb=$(realpath -- "${3:?Debian linux-image .deb}")
wheel=$(realpath -- "${4:?pinned CentOS-compatible PyMuPDF wheel}")
output=$(realpath -m -- "${5:?output .run file}")
[[ $EUID == 0 && $sysroot != / && -x $sysroot/usr/bin/dbus-run-session && -x $sysroot/usr/bin/bindfs && -f $app/resources/app.asar ]]
for name in dev proc sys; do ! mountpoint -q "$sysroot/$name" || { echo "Use an unmounted guest sysroot" >&2; exit 1; }; done
mkdir -p -- "$(dirname -- "$output")"
work=$(mktemp -d -- "$(dirname -- "$output")/.centos7-build.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT
bundle=$work/payload
root=$work/root
ram=$work/ram
mkdir -p "$bundle"/{host,guest} "$root" "$ram"/{bin,dev,proc,sys,modules,lower,writable,newroot}
cp -a --reflink=auto "$sysroot/." "$root"
rm -rf -- "$root/var/cache/apt/archives" "$root/var/lib/apt/lists" "$root/var/log" "$root/debootstrap"
mkdir -p "$root"/{var/log,etc,run,sys,proc,dev,tmp,opt/zcode-verification-agent,usr/lib/zcode-portable}
rm -f -- "$root"/{etc/machine-id,var/lib/dbus/machine-id,etc/resolv.conf}
printf 'zcode-desktop\n' >"$root/etc/hostname"
printf '127.0.0.1 localhost zcode-desktop\n::1 localhost\n' >"$root/etc/hosts"
printf 'nameserver 10.0.2.3\n' >"$root/etc/resolv.conf"
install -m755 "$src/guest-init" "$root/sbin/zcode-init"
install -m644 "$src/guest.py" "$root/usr/lib/zcode-portable/guest.py"
install -m755 /bin/busybox "$root/bin/busybox"
(cd "$app" && tar --exclude='./resources/verification-formal' -cf - .) | tar -C "$root/opt/zcode-verification-agent" -xf -
ln -s /run/zcode/kit "$root/opt/zcode-verification-agent/resources/verification-formal"
chown -hR root:root "$root/opt/zcode-verification-agent"
chmod -R go-w "$root/opt/zcode-verification-agent"
chmod 4755 "$root/opt/zcode-verification-agent/chrome-sandbox"
cp -a --reflink=auto "$app/resources/verification-formal" "$bundle/kit"
python3 "$src/package-runtime.py" pdf "$wheel" "$bundle/kit"
if [[ $# -gt 5 ]]; then
  [[ $# -ge 7 ]] || { echo "Provide the knowledge directory and at least one source ID" >&2; exit 2; }
  python3 -I "$src/knowledge_seed.py" "$bundle/kit/runner" "$(realpath -- "$6")" "$bundle/knowledge-seed" "${@:7}"
  rm -f -- "$bundle/knowledge-seed/.catalog-lock.sqlite3"
fi
python3 "$src/package-runtime.py" host "$bundle/host"
install -m755 "$src/start" "$bundle/start"
install -m755 "$src/zcode-x11" "$bundle/host/zcode-x11"
mkdir "$bundle/host/pdf-tools"
for tool in pdftotext pdftoppm; do install -m755 "$src/pdf-tool" "$bundle/host/pdf-tools/$tool"; done
install -m644 "$src/fonts.conf" "$bundle/host/fonts.conf"
install -m644 "$src/launch.py" "$bundle/launch.py"
install -m644 "$src/knowledge_seed.py" "$bundle/knowledge_seed.py"
dpkg-deb -x "$kernel_deb" "$work/kernel"
version=$(basename "$(find "$work/kernel/lib/modules" -mindepth 1 -maxdepth 1 -type d)")
depmod -b "$work/kernel" "$version" 2>/dev/null
install -m644 "$work/kernel/boot/vmlinuz-$version" "$bundle/guest/vmlinuz"
cp -a "$work/kernel/usr/share/doc/$(dpkg-deb -f "$kernel_deb" Package)" "$bundle/guest/kernel-notices"
python3 "$src/package-runtime.py" modules "$work/kernel" "$ram" "$version"
install -m755 /bin/busybox "$ram/bin/busybox"
for cmd in sh mount insmod seq sleep switch_root mkdir; do ln -s busybox "$ram/bin/$cmd"; done
install -m755 "$src/initramfs-init" "$ram/init"
(cd "$ram" && find . -print0 | cpio --quiet -o -0 -H newc | gzip -1) >"$bundle/guest/initrd.gz"
truncate -s 4G "$work/desktop.img"
mkfs.ext4 -F -q -m0 -L zcode-profile "$work/desktop.img"
chmod 600 "$work/desktop.img"
(cd "$work" && tar --sparse --format=gnu -czf "$bundle/guest/profile.tar.gz" desktop.img)
chroot "$root" dpkg-query -W -f='${binary:Package} ${Version}\n' >"$bundle/guest/packages.txt"
mksquashfs "$root" "$bundle/guest/desktop.squashfs" -noappend -no-xattrs -comp zstd -Xcompression-level 8 -processors 4 -no-progress
(cd "$bundle" && tar --owner=0 --group=0 -cf - . | gzip -1) >"$work/payload.tar.gz"
digest=$(sha256sum "$work/payload.tar.gz")
sed "s/@PAYLOAD_SHA256@/${digest%% *}/" "$src/self-extract.sh" >"$work/desktop.run"
cat "$work/payload.tar.gz" >>"$work/desktop.run"
chmod 755 "$work/desktop.run"
mv -T -- "$work/desktop.run" "$output"
sha256sum "$output"
