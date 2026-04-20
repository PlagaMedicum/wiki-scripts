#!/usr/bin/env bash

set -e

# Parse command line arguments
JSON_MODE=false
FORCE_OVERWRITE=false
ARGS=()

for arg in "$@"; do
    case "$arg" in
        --json) 
            JSON_MODE=true 
            ;;
        --force)
            FORCE_OVERWRITE=true
            ;;
        --help|-h) 
            echo "Usage: $0 [--json]"
            echo "  --json    Output results in JSON format"
            echo "  --force   Overwrite an existing non-empty plan.md"
            echo "  --help    Show this help message"
            exit 0 
            ;;
        *) 
            ARGS+=("$arg") 
            ;;
    esac
done

log_note() {
    if $JSON_MODE; then
        echo "$1" >&2
    else
        echo "$1"
    fi
}

# Get script directory and load common functions
SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Get all paths and variables from common functions
_paths_output=$(get_feature_paths) || { echo "ERROR: Failed to resolve feature paths" >&2; exit 1; }
eval "$_paths_output"
unset _paths_output

# Check if we're on a proper feature branch (only for git repos)
check_feature_branch "$CURRENT_BRANCH" "$HAS_GIT" || exit 1

# Ensure the feature directory exists
mkdir -p "$FEATURE_DIR"

PLAN_ACTION="preserved"

# Copy plan template if it exists, but never silently replace a filled plan unless --force is set
if [[ -f "$IMPL_PLAN" ]] && [[ -s "$IMPL_PLAN" ]] && [[ "$FORCE_OVERWRITE" != "true" ]]; then
    log_note "Preserved existing plan at $IMPL_PLAN"
else
    TEMPLATE=$(resolve_template "plan-template" "$REPO_ROOT") || true
    if [[ -n "$TEMPLATE" ]] && [[ -f "$TEMPLATE" ]]; then
        cp "$TEMPLATE" "$IMPL_PLAN"
        log_note "Copied plan template to $IMPL_PLAN"
        PLAN_ACTION="copied-template"
    else
        log_note "Warning: Plan template not found"
        # Create a basic plan file if template doesn't exist
        touch "$IMPL_PLAN"
        PLAN_ACTION="touched-empty"
    fi
fi

# Output results
if $JSON_MODE; then
    if has_jq; then
        jq -cn \
            --arg feature_spec "$FEATURE_SPEC" \
            --arg impl_plan "$IMPL_PLAN" \
            --arg specs_dir "$FEATURE_DIR" \
            --arg branch "$CURRENT_BRANCH" \
            --arg has_git "$HAS_GIT" \
            --arg plan_action "$PLAN_ACTION" \
            '{FEATURE_SPEC:$feature_spec,IMPL_PLAN:$impl_plan,SPECS_DIR:$specs_dir,BRANCH:$branch,HAS_GIT:$has_git,PLAN_ACTION:$plan_action}'
    else
        printf '{"FEATURE_SPEC":"%s","IMPL_PLAN":"%s","SPECS_DIR":"%s","BRANCH":"%s","HAS_GIT":"%s","PLAN_ACTION":"%s"}\n' \
            "$(json_escape "$FEATURE_SPEC")" "$(json_escape "$IMPL_PLAN")" "$(json_escape "$FEATURE_DIR")" "$(json_escape "$CURRENT_BRANCH")" "$(json_escape "$HAS_GIT")" "$(json_escape "$PLAN_ACTION")"
    fi
else
    echo "FEATURE_SPEC: $FEATURE_SPEC"
    echo "IMPL_PLAN: $IMPL_PLAN" 
    echo "SPECS_DIR: $FEATURE_DIR"
    echo "BRANCH: $CURRENT_BRANCH"
    echo "HAS_GIT: $HAS_GIT"
    echo "PLAN_ACTION: $PLAN_ACTION"
fi
