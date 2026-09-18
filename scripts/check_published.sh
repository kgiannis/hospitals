#!/usr/bin/env bash
# Fail if the published site is serving older data than the repo holds.
#
# The 2026-08/09 outage was invisible because a deploy that never runs leaves
# nothing red in the Actions tab. This turns "site quietly frozen" into a failed
# workflow run, which GitHub emails about.
#
# Usage: check_published.sh <page-url> [repo-index-json]
set -euo pipefail

PAGE_URL="${1:?page URL required}"
REPO_INDEX="${2:-daily_schedules/attica/index.json}"

# Pages reports success as soon as the deployment is created; the CDN edge can
# lag by a few seconds. Poll rather than asserting once, so a slow edge is a
# wait and not a false alarm — a tripwire that cries wolf gets ignored.
ATTEMPTS="${ATTEMPTS:-12}"
INTERVAL="${INTERVAL:-15}"

repo_latest=$(jq -r '.dates | max' "$REPO_INDEX")
if [ -z "$repo_latest" ] || [ "$repo_latest" = "null" ]; then
  echo "::error::Could not read a newest date from ${REPO_INDEX}."
  exit 1
fi
echo "Repo newest published date: ${repo_latest}"

index_url="${PAGE_URL%/}/data/index.json"
live=""
for attempt in $(seq 1 "$ATTEMPTS"); do
  # Cache-bust: the Pages CDN may still hold the previous object.
  live=$(curl -fsS -H 'Cache-Control: no-cache' \
            "${index_url}?cachebust=${GITHUB_RUN_ID:-local}-${attempt}" \
          | jq -r '.dates | max' 2>/dev/null || echo "")

  if [ "$live" = "$repo_latest" ]; then
    echo "Published site is current (${live}), confirmed on attempt ${attempt}."
    exit 0
  fi

  echo "Attempt ${attempt}/${ATTEMPTS}: site serves '${live:-<unreachable>}', expected '${repo_latest}'."
  [ "$attempt" -lt "$ATTEMPTS" ] && sleep "$INTERVAL"
done

echo "::error::Published site is stale: serving '${live:-<unreachable>}' while main holds '${repo_latest}'. The deploy reported success but ${index_url} did not update."
exit 1
