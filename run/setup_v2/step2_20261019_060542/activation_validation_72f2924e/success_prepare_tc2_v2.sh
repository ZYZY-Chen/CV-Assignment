set -euo pipefail
unset QT_XCB_GL_INTEGRATION
environment_prefix=/synthetic/ca6129
conda() {
    if [[ "$1 $2" == 'shell.bash hook' ]]; then
        if [[ 'success' == hook_failure ]]; then return 71; fi
        printf '%s\n' 'optional_qt_value="$QT_XCB_GL_INTEGRATION"'
    elif [[ "$1" == activate ]]; then
        if [[ 'success' == activate_failure ]]; then return 72; fi
        optional_activate_value="$QT_XCB_GL_INTEGRATION"
    else
        return 80
    fi
}
set +u
    conda_hook="$(conda shell.bash hook)"
    eval "$conda_hook"
    conda activate "$environment_prefix"
    set -u
    unset conda_hook
[[ "$-" == *u* && "$-" == *e* ]] || exit 97
set -o | grep -Eq '^pipefail[[:space:]]+on$'
if (printf '%s' "$UNDEFINED_AFTER_ACTIVATION" >/dev/null) 2>/dev/null; then exit 98; fi
echo POST_ACTIVATION_REACHED
