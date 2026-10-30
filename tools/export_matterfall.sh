#!/usr/bin/env bash
# Copies the Matterfall port's source into a separate Git repository (default: ../matterfall-github)
# and commits it, for the GitHub repository that builds and releases the Windows package.
#   gow3_pc/   the runtime: its tracked and new files (not out/, user/ or other ignored files); the
#              submodules are pinned as gitlinks at the commits checked out here
#   tools/     the Matterfall start, package, export and release scripts, release notes, VERSION
#   launcher/matterfall_launcher.pyw, Start-Matterfall.cmd, and tools/matterfall-github/ (README,
#   CHANGELOG, .gitignore, GitHub Actions workflow) at the root
# The Uncharted launcher, its multiplayer research and its tools stay out. Nothing from the game or a
# player is copied; a final check refuses the commit if such a file slipped in.
# usage: tools/export_matterfall.sh [destination] [commit message]
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
src=$PWD
dest=${1:-../matterfall-github}
message=${2:-"Sync from the working tree"}
mkdir -p "$dest"
dest=$(cd -- "$dest" && pwd)
[[ -d $dest/.git ]] || git -C "$dest" init -q -b main
git -C "$dest" config core.autocrlf false
git -C "$dest" config core.eol lf
git -C "$dest" config core.longpaths true

# Everything but .git is rebuilt from the working tree, so deleted files disappear from the export.
find "$dest" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +

copy() {  # copy <relative path>
    mkdir -p "$dest/$(dirname -- "$1")"
    cp -p -- "$src/$1" "$dest/$1"
}

# This repository lists the runtime's submodules at its root, as gow3_pc/<path>.
submodules=$(git config -f .gitmodules --get-regexp '\.path$' | awk '{print $2}' | sed 's|^gow3_pc/||')
git -C gow3_pc ls-files -co --exclude-standard | while read -r path; do
    case $path in
        .github/*|.gitmodules|README.md|README.*.md|docs/*|launcher/*|patches/*|run.py|run.sh) continue ;;
        packaging/linux/*|packaging/appimage.sh|packaging/default.nix|packaging/gow3-entry.c) continue ;;
        packaging/windows/README*|packaging/windows/package.sh|packaging/windows/build_dlss.sh) continue ;;
        tests/test_launcher_*|tests/test_button_icons.py) continue ;;
        scripts/steam_shortcut.py|tools/gow3_frame_map.py|tests/test_steam_shortcut.py) continue ;;
        tools/aerolib.inl) continue ;;  # 9 MB NID list from shadPS4, only for gen_import_names.py
    esac
    grep -qxF -- "$path" <<< "$submodules" && continue
    [[ -f gow3_pc/$path ]] && copy "gow3_pc/$path"
done
for path in tools/run_matterfall.py tools/package_matterfall.sh tools/copy_python.py \
    tools/export_matterfall.sh tools/release_matterfall.sh tools/VERSION_MATTERFALL \
    launcher/matterfall_launcher.pyw Start-Matterfall.cmd; do
    copy "$path"
done
for path in tools/release-notes-matterfall/*.md; do copy "$path"; done
cp -r tools/matterfall-github/. "$dest/"

# Submodules: .gitmodules from the runtime's, under gow3_pc/, pinned at the checked-out commits.
: > "$dest/.gitmodules"
while read -r path; do
    url=$(git config -f .gitmodules --get "submodule.gow3_pc/$path.url")
    printf '[submodule "gow3_pc/%s"]\n\tpath = gow3_pc/%s\n\turl = %s\n' "$path" "$path" "$url" \
        >> "$dest/.gitmodules"
    mkdir -p "$dest/gow3_pc/$path"
done <<< "$submodules"

forbidden=$(cd "$dest" && find . -path ./.git -prune -o \( -iname eboot.bin -o -iname '*.elf' \
    -o -iname sce_sys -o -iname savedata -o -iname '*.log' -o -iname '*.ini' -o -iname '*.pkg' \
    -o -iname '*.pak' -o -iname '*.uasset' -o -iname '*.prx' -o -iname '*.mp4' -o -iname 'boot*.bin' \
    -o -iname '*.spv' -o -iname '*.dmp' -o -iname 'content.bin' -o -iname 'entry.bin' -o -iname '*.sav' \
    -o -iname 'icon0.png' -o -iname 'pic*.png' \) -print)
if [[ -n $forbidden ]]; then
    echo "The export holds files that must not be pushed:" >&2
    echo "$forbidden" >&2
    exit 1
fi

cd "$dest"
git add -A
while read -r path; do
    sha=$(git -C "$src/gow3_pc/$path" rev-parse HEAD)
    git update-index --add --cacheinfo "160000,$sha,gow3_pc/$path"
done <<< "$submodules"
if git diff --cached --quiet; then
    echo "No changes to commit in $dest"
else
    git commit -q -m "$message" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
    git log --oneline -1
fi
