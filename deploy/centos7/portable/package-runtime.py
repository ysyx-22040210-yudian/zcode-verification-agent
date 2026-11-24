"""Collect ELF dependencies and the initramfs drivers from the build distribution."""
import gzip
import lzma
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile
import hashlib


def host_runtime(destination):
    lib = destination / "lib"
    modules = destination / "modules"
    firmware = destination / "firmware"
    for directory in (lib, modules, firmware):
        directory.mkdir()
    inputs = [Path(shutil.which(binary)) for binary in ("qemu-system-x86_64", "socat", "pdftotext", "pdftoppm")]
    module_dir = Path("/usr/lib/x86_64-linux-gnu/qemu")
    for pattern in ("accel-*-x86_64.so", "hw-9pfs-*.so"):
        for plugin in module_dir.glob(pattern):
            shutil.copy2(plugin, modules / plugin.name)
            inputs.append(plugin)
    sources = set(inputs)
    for binary in inputs:
        if binary.parent != module_dir:
            shutil.copy2(binary, destination / binary.name)
        output = subprocess.check_output(["ldd", binary], text=True)
        if "not found" in output:
            raise ValueError("Missing library for " + str(binary))
        for name in re.findall(r"(?:=>\s+|^\s*)(/[^ \n]+)\s+\(", output, re.M):
            path = Path(name)
            sources.add(path)
            shutil.copy2(path, lib / path.name)
    for directory in (Path("/usr/share/seabios"), Path("/usr/share/qemu")):
        for pattern in ("bios.bin", "bios-256k.bin", "linuxboot*.bin", "kvmvapic.bin", "multiboot*.bin"):
            for item in directory.glob(pattern):
                shutil.copy2(item, firmware / item.name)
                sources.add(item)
    assert (firmware / "bios-256k.bin").is_file() and (lib / "ld-linux-x86-64.so.2").is_file()
    notices = destination / "licenses"
    notices.mkdir()
    packages = {"poppler-data", "fonts-dejavu-core", "fonts-noto-cjk"}
    for path in sources:
        for p in (str(path), str(path.resolve()), str(path.resolve()).removeprefix("/usr")):
            found = subprocess.run(["dpkg-query", "-S", p], capture_output=True, text=True)
            if not found.returncode:
                packages.add(found.stdout.split(": ", 1)[0].split(":")[0])
                break
    versions = []
    for package in sorted(packages):
        copyright_file = Path("/usr/share/doc") / package / "copyright"
        shutil.copyfile(copyright_file, notices / (package + ".txt"))
        versions.append(subprocess.check_output(["dpkg-query", "-W", "-f=${binary:Package} ${Version} ${source:Package} ${source:Version}", package], text=True))
    (notices / "packages.txt").write_text("\n".join(versions) + "\n")
    shutil.copytree("/usr/share/poppler", destination / "share/poppler")
    fonts = destination / "share/fonts"
    fonts.mkdir()
    for font in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        shutil.copy2(font, fonts)


def drivers(kernel, stage, version):
    order = []
    for name in ("virtio_pci", "virtio_blk", "virtio_net", "virtio_rng", "9pnet_virtio", "9p", "squashfs", "overlay", "ext4", "fuse"):
        lines = subprocess.check_output(["modprobe", "-d", kernel, "-S", version, "--show-depends", name], text=True)
        for line in lines.splitlines():
            if not line.startswith("insmod "):
                continue
            path = Path(line.split()[1])
            basename = path.name.split(".ko")[0] + ".ko"
            if basename in order:
                continue
            if path.suffix == ".xz":
                data = lzma.decompress(path.read_bytes())
            elif path.suffix == ".zst":
                data = subprocess.check_output(["zstd", "-dc", path])
            elif path.suffix == ".gz":
                data = gzip.decompress(path.read_bytes())
            else:
                data = path.read_bytes()
            (stage / "modules" / basename).write_bytes(data)
            order.append(basename)
    (stage / "module-order").write_text("\n".join(order) + "\n")


def add_pdf(wheel, kit):
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if digest != "ee22155d3a634642d76553204867d862ae1bdd9f7cf70c0797d8127ebee6bed5":
        raise ValueError("Expected the CentOS-compatible PyMuPDF 1.25.5 manylinux2014 x86-64 wheel")
    with zipfile.ZipFile(wheel) as package:
        package.extractall(kit / "formal-toolchain/python/lib/python3.11/site-packages")


if __name__ == "__main__":
    mode, *args = sys.argv[1:]
    if mode == "host":
        host_runtime(Path(args[0]))
    elif mode == "modules":
        drivers(Path(args[0]), Path(args[1]), args[2])
    elif mode == "pdf":
        add_pdf(Path(args[0]), Path(args[1]))
