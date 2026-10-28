#!/usr/bin/env bash
# Git side of the download-stats workflow: keep the data on the orphan branch
# `download-stats`, never on `master` (see .github/workflows/download-stats.yml).
#
#   download_stats_git.sh prepare   check the branch out into $DATA_DIR (create it on the first run)
#   download_stats_git.sh publish   commit what changed in $DATA_DIR and push it (never forced)
#
# Environment: DATA_DIR (default: data), STATS_REMOTE (default: origin),
# GIT_AUTH_TOKEN (optional; sent only to github.com as a basic-auth header, so the
# checkout can run with persist-credentials: false and no other step holds the token).
set -euo pipefail

BRANCH=download-stats
DATA_DIR="${DATA_DIR:-data}"
REMOTE="${STATS_REMOTE:-origin}"

remote_git() {
  if [ -n "${GIT_AUTH_TOKEN:-}" ]; then
    local header
    header="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$GIT_AUTH_TOKEN" | base64 | tr -d '\n')"
    git -c "http.https://github.com/.extraheader=${header}" "$@"
  else
    git "$@"
  fi
}

prepare() {
  local rc=0
  remote_git ls-remote --exit-code --heads "$REMOTE" "refs/heads/${BRANCH}" > /dev/null || rc=$?
  case "$rc" in
    0)
      remote_git fetch --depth=1 "$REMOTE" "+refs/heads/${BRANCH}:refs/remotes/${REMOTE}/${BRANCH}"
      git worktree add -B "$BRANCH" "$DATA_DIR" "refs/remotes/${REMOTE}/${BRANCH}"
      ;;
    2)
      # exit code 2 is exactly "no such branch": the first run
      echo "No ${BRANCH} branch yet: creating it as an orphan branch."
      git worktree add --orphan -b "$BRANCH" "$DATA_DIR"
      ;;
    *)
      # anything else is a network or auth failure: never mistake it for "no branch"
      echo "git ls-remote failed with exit code ${rc}" >&2
      exit 1
      ;;
  esac
}

publish() {
  local want
  want="$(cd "$DATA_DIR" && pwd -P)"
  cd "$DATA_DIR"
  # never commit in the master checkout because the data worktree is missing or misnamed
  # (symbolic-ref, not rev-parse: the orphan branch is unborn until its first commit)
  if [ "$(git symbolic-ref --short HEAD)" != "$BRANCH" ] \
      || [ "$(git rev-parse --show-toplevel)" != "$want" ]; then
    echo "${DATA_DIR} is not the ${BRANCH} worktree: refusing to commit" >&2
    exit 1
  fi
  git add -A
  if git diff --cached --quiet; then
    echo "No file changed; nothing to commit."
    exit 0
  fi
  # core.hooksPath: a hook in the shared .git directory must not run with the token in the environment
  git -c core.hooksPath=/dev/null \
      -c user.name="github-actions[bot]" \
      -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
      commit -q -m "chore: download stats $(date -u +%F)"
  remote_git push "$REMOTE" "HEAD:refs/heads/${BRANCH}"
}

case "${1:-}" in
  prepare) prepare ;;
  publish) publish ;;
  *) echo "usage: $0 prepare|publish" >&2; exit 64 ;;
esac
