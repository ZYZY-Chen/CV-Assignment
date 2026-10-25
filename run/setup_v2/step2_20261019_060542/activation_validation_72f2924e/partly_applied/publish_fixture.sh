set -euo pipefail
root="$(pwd -P)"
archive="$root/_downloads/activation-fix-20261019_071223_5bf8af03.tar"
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == 86b889390cb063f0746da6c44d2142c67ec9cf36ce6f85fba96835c4a3c8b7ff ]] || { echo 'Activation bundle hash mismatch.' >&2; exit 2; }
incoming="$root/tmp/activation-fix-20261019_071223_5bf8af03"
backup="$root/run/setup_v2/activation_fix_20261019_071223_5bf8af03"
mkdir -- "$incoming"
tar -xf "$archive" -C "$incoming" --no-same-owner --no-same-permissions
# Verify all old/new pairs before replacing either script.
while read -r old_hash new_hash relative; do
    case "$relative" in scripts/slurm/prepare_tc2_v2.sh|scripts/slurm/check_setup_v2.sh) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    current_hash=$(sha256sum "$target" | cut -d' ' -f1)
    [[ "$current_hash" == "$old_hash" || "$current_hash" == "$new_hash" ]] || exit 2
    [[ "$(sha256sum "$incoming/$relative" | cut -d' ' -f1)" == "$new_hash" ]] || exit 2
done < "$incoming/activation.sha256"
mkdir -- "$backup"
cp -- "$incoming/activation.sha256" "$backup/activation.sha256"
while read -r old_hash new_hash relative; do
    target="$root/$relative"
    mkdir -p -- "$backup/$(dirname -- "$relative")"
    cp -p -- "$target" "$backup/$relative"
done < "$incoming/activation.sha256"
while read -r old_hash new_hash relative; do
    target="$root/$relative"
    current_hash=$(sha256sum "$target" | cut -d' ' -f1)
    [[ "$current_hash" == "$old_hash" || "$current_hash" == "$new_hash" ]] || exit 2
    if [[ "$current_hash" != "$new_hash" ]]; then
        mv -T -- "$incoming/$relative" "$target"
    fi
    [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$new_hash" ]] || exit 2
    printf '%s %s %s\n' "$old_hash" "$new_hash" "$relative" >> "$backup/applied.txt"
done < "$incoming/activation.sha256"
echo 'Two activation entry points updated; installed environment retained.'
