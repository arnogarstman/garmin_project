#!/usr/bin/env bash
# Create the Strava webhook subscription (once per Strava API app), pointing at the deployed Worker.
# Usage: STRAVA_CLIENT_ID=... STRAVA_CLIENT_SECRET=... STRAVA_VERIFY_TOKEN=... ./subscribe.sh https://<worker>.workers.dev/strava
# Prints {"id": <subscription id>}; set it with `npx wrangler secret put STRAVA_SUBSCRIPTION_ID`.
set -euo pipefail
callback="${1:?usage: subscribe.sh <callback url>}"
curl -sS -X POST https://www.strava.com/api/v3/push_subscriptions \
  -F client_id="${STRAVA_CLIENT_ID:?}" \
  -F client_secret="${STRAVA_CLIENT_SECRET:?}" \
  -F callback_url="$callback" \
  -F verify_token="${STRAVA_VERIFY_TOKEN:?}"
echo
