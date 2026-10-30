#!/usr/bin/env bash
# Builds dist/Matterfall-windows/ and dist/Matterfall-windows.zip: a folder that runs Matterfall
# (PS4, CUSA02475) on any Windows 10/11 x64 PC with a Vulkan GPU, without Python or MSYS2.
#   Matterfall Launcher.exe   starter (gow3_pc/packaging/windows/matterfall) -> python\pythonw.exe
#                             launcher\matterfall_launcher.pyw
#   python\                   Windows Python with Tkinter, Pillow and cryptography (PKG unpacking)
#   launcher\ tools\          the launcher and the start script (tools/run_matterfall.py)
#   gow3_pc\scripts\          preparation, settings, UE4 override pak, save backups, PKG unpacker
#   gow3_pc\out\              the runtime (gow3-probe.exe, without debug information) and its DLLs
#   Start-Matterfall.cmd, README.txt, LICENSE.txt, licenses\
# No game files ship: each player selects their own copy of the game in the launcher.
# Run after building the runtime (gow3_pc/build.sh), from Git Bash or an MSYS2 CLANG64 shell.
# PYTHON_HOME is a Windows Python 3.10+ with Pillow and cryptography (default: `python` on PATH).
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
# The Windows Python (looked up before the CLANG64 tools go first on PATH: MSYS2 has its own).
python=${PYTHON:-python}
python_home=${PYTHON_HOME:-$("$python" -c 'import sys, os; print(os.path.dirname(sys.executable))')}
case $python_home in
    *msys64*|/usr/*|/clang64/*) echo "Need a Windows Python (PYTHON_HOME), not MSYS2's: $python_home" >&2; exit 1 ;;
esac
msys=${MSYS2_ROOT:-/c/msys64}
msys=${msys%/}
[[ -d $msys/clang64/bin ]] && export PATH="$msys/clang64/bin:$PATH"
[[ -f gow3_pc/out/gow3-probe.exe ]] || { echo 'Build the runtime first: gow3_pc/build.sh' >&2; exit 1; }
pack=gow3_pc/packaging/windows/matterfall

stage=dist/stage/Matterfall-windows
rm -rf -- dist/stage
mkdir -p "$stage/gow3_pc/out" "$stage/gow3_pc/scripts" "$stage/tools" "$stage/launcher" \
    "$stage/analysis/matterfall" "$stage/user"

# The runtime without debug information, and every DLL it loads from the CLANG64 tree. A copy
# first: another build may replace the file while this runs.
cp gow3_pc/out/gow3-probe.exe dist/stage/gow3-probe.exe
llvm-strip --strip-debug -o "$stage/gow3_pc/out/gow3-probe.exe" dist/stage/gow3-probe.exe
ldd dist/stage/gow3-probe.exe | awk '/clang64/ {print $3}' | sort -u | while read -r dll; do
    cp "$dll" "$stage/gow3_pc/out/"
done
rm -f dist/stage/gow3-probe.exe
[[ -n $(ls "$stage"/gow3_pc/out/*.dll 2>/dev/null) ]] || { echo 'No runtime DLLs found (ldd, CLANG64 on PATH?)' >&2; exit 1; }

# Scripts: what tools/run_matterfall.py and the launcher use.
for script in prepare.py link_modules.py link_libc.py content_profile.py matterfall_settings.py \
    ue4_override.py save_backup.py pkg_extract.py pkg_keys.py; do
    cp "gow3_pc/scripts/$script" "$stage/gow3_pc/scripts/"
done
cp tools/run_matterfall.py "$stage/tools/"
cp launcher/matterfall_launcher.pyw "$stage/launcher/"
cp Start-Matterfall.cmd "$stage/"
cp "$pack/README-Windows.txt" "$stage/README.txt"
cp gow3_pc/LICENSE "$stage/LICENSE.txt"
# The package's version (tools/VERSION when there is one, else the date).
if [[ -f tools/VERSION_MATTERFALL ]]; then cp tools/VERSION_MATTERFALL "$stage/VERSION"
else date +0.1.%Y%m%d > "$stage/VERSION"; fi

# Licenses of the sources built into the runtime, and of every MSYS2 package whose DLL ships.
licenses=$stage/licenses
mkdir -p "$licenses"
for dir in gow3_pc/gpu/third_party/* gow3_pc/third_party/*; do
    for file in "$dir"/LICENSE* "$dir"/COPYING* "$dir"/COPYRIGHT*; do
        [[ -f $file ]] || continue
        mkdir -p "$licenses/$(basename -- "$dir")"
        cp "$file" "$licenses/$(basename -- "$dir")/"
    done
done
[[ -f gow3_pc/gpu/third_party/gcn/include/gcn/si_ci_vi_merged_offset.h ]] && \
    head -n 24 gow3_pc/gpu/third_party/gcn/include/gcn/si_ci_vi_merged_offset.h > "$licenses/gcn-headers.txt"
pacman=$(command -v pacman || echo "$msys/usr/bin/pacman")
if [[ -x $pacman || -x $pacman.exe ]]; then
    dlls=()
    for dll in "$stage"/gow3_pc/out/*.dll; do
        dlls+=("$(cygpath -m "$msys/clang64/bin/$(basename -- "$dll")")")
    done
    mapfile -t packages < <({ "$pacman" -Qqo "${dlls[@]}" 2>/dev/null || true; } | sort -u)
    if ((${#packages[@]})); then
        { "$pacman" -Qlq "${packages[@]}" | grep '/share/licenses/.*[^/]$' || true; } | while read -r file; do
            name=${file#*/share/licenses/}
            mkdir -p "$licenses/msys2/$(dirname -- "$name")"
            cp "$msys$file" "$licenses/msys2/$name"
        done
        {
            echo "Third-party packages whose DLLs ship in gow3_pc\\out (MSYS2 CLANG64 builds)."
            echo "Their sources: https://repo.msys2.org/mingw/sources/ and https://packages.msys2.org/"
            "$pacman" -Qi "${packages[@]}" | awk '/^Name /{print ""} /^(Name|Version|Licenses|URL) /{print}'
        } > "$licenses/THIRD-PARTY.txt"
    fi
fi

# Python with Tkinter and Pillow (tools/copy_python.py), and cryptography with its cffi backend for
# the launcher's "Install from PKG" (gow3_pc/scripts/pkg_extract.py).
"$python_home/python.exe" tools/copy_python.py "$python_home" "$stage/python"
site=$python_home/Lib/site-packages
for package in cryptography cffi pycparser; do
    [[ -d $site/$package ]] || { echo "$package is not installed in $python_home (pip install cryptography)" >&2; exit 1; }
    cp -r "$site/$package" "$stage/python/Lib/site-packages/"
done
cp "$site"/_cffi_backend*.pyd "$stage/python/Lib/site-packages/"
for dist in pillow cryptography cffi pycparser; do
    for file in "$site"/$dist-*.dist-info/licenses/* "$site"/$dist-*.dist-info/LICENSE*; do
        [[ -f $file ]] && { mkdir -p "$licenses/$dist"; cp "$file" "$licenses/$dist/"; }
    done
done

# The starter, with an icon drawn here (no game art ships).
"$python_home/python.exe" "$pack/make_icon.py" dist/stage/matterfall.ico
windres -I dist/stage "$pack/starter.rc" -O coff -o dist/stage/starter.res.o
clang -O2 -municode -mwindows "$pack/starter.c" dist/stage/starter.res.o -o "$stage/Matterfall Launcher.exe"

find "$stage" -name __pycache__ -prune -exec rm -rf {} +
# Nothing from the game or a player (game executables, saves, caches, logs, paks) may ship.
forbidden=$(find "$stage" \( -iname eboot.bin -o -iname '*.elf' -o -iname sce_sys -o -iname savedata \
    -o -iname cache -o -iname '*.log' -o -iname 'matterfall.ini' -o -iname '*.pkg' -o -iname '*.pak' \
    -o -iname '*.uasset' -o -iname 'icon0.png' -o -iname 'pic*.png' -o -iname 'boot*.bin' \) -print)
if [[ -n $forbidden ]]; then
    echo "Package holds files that must not ship:" >&2
    echo "$forbidden" >&2
    exit 1
fi

# The staged launcher must start with the packaged Python alone (every page built, then closed).
GOW3_DATA_DIR="$(cygpath -w "$PWD/dist/stage/smoke")" "$stage/python/python.exe" -I \
    "$stage/launcher/matterfall_launcher.pyw" --smoke-test
"$stage/python/python.exe" -I -c "import sys; sys.path.insert(0, r'$(cygpath -w "$stage/gow3_pc/scripts")'); \
import pkg_extract, ue4_override, matterfall_settings, save_backup, prepare; print('Packaged Python: scripts import OK')"
"$stage/python/python.exe" -I "$stage/tools/run_matterfall.py" --help > /dev/null
rm -rf dist/stage/smoke

rm -f dist/Matterfall-windows.zip
"$python_home/python.exe" -m zipfile -c dist/Matterfall-windows.zip "$stage"
rm -rf dist/Matterfall-windows
mv "$stage" dist/Matterfall-windows
rm -rf dist/stage
du -sh dist/Matterfall-windows dist/Matterfall-windows.zip
