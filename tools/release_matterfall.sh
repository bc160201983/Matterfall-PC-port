#!/usr/bin/env bash
# Publishes a Matterfall release: tools/release_matterfall.sh 1.0.0
#   1. needs tools/release-notes-matterfall/v1.0.0.md and sets tools/VERSION_MATTERFALL to 1.0.0,
#   2. exports and pushes the source (tools/export_matterfall.sh), tags that commit v1.0.0 and
#      pushes the tag,
#   3. GitHub Actions builds the package and publishes the release with it (about 20 minutes).
# The export repository needs an "origin" remote (the GitHub repository).
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
version=${1:?usage: tools/release_matterfall.sh <version, e.g. 1.0.0>}
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Not a version: $version" >&2; exit 1; }
tag=v$version
dest=${GITHUB_EXPORT:-../matterfall-github}
[[ -f tools/release-notes-matterfall/$tag.md ]] || { echo "Write tools/release-notes-matterfall/$tag.md first" >&2; exit 1; }
printf '%s\n' "$version" > tools/VERSION_MATTERFALL
tools/export_matterfall.sh "$dest" "Release $version"
git -C "$dest" fetch -q --tags origin || true
if git -C "$dest" rev-parse -q --verify "refs/tags/$tag" > /dev/null; then
    echo "$tag exists already" >&2
    exit 1
fi
git -C "$dest" push -q origin main
git -C "$dest" tag -a "$tag" -m "Release $version"
git -C "$dest" push -q origin "$tag"
echo "Pushed $tag: GitHub Actions builds the package and publishes the release (about 20 minutes)."
