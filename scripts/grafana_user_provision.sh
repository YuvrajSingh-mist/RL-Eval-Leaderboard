#!/usr/bin/env sh
set -eu

: "${GRAFANA_URL:=http://grafana:3000}"
: "${GRAFANA_ADMIN_USER:=admin}"
: "${GRAFANA_ADMIN_PASSWORD:=admin}"
: "${GRAFANA_NEW_USER:=rl-yuvraj}"
: "${GRAFANA_NEW_PASSWORD:=changeme}"
: "${GRAFANA_NEW_ROLE:=Admin}"

echo "Waiting for Grafana at ${GRAFANA_URL} ..."
for i in $(seq 1 60); do
  if curl -sf "${GRAFANA_URL}/api/health" >/dev/null; then
    break
  fi
  sleep 2
done

# Lookup user
lookup() {
  curl -sf -u "${GRAFANA_ADMIN_USER}:${GRAFANA_ADMIN_PASSWORD}" \
    "${GRAFANA_URL}/api/users/lookup?loginOrEmail=${GRAFANA_NEW_USER}" || true
}

USER_JSON="$(lookup)"
USER_ID="$(echo "$USER_JSON" | grep -o '"id"[: ]*[0-9]*' | head -n1 | cut -d: -f2 | tr -d ' ')"

if [ -z "${USER_ID}" ]; then
  echo "Creating Grafana user ${GRAFANA_NEW_USER}"
  curl -sf -u "${GRAFANA_ADMIN_USER}:${GRAFANA_ADMIN_PASSWORD}" \
    -H 'Content-Type: application/json' \
    -X POST "${GRAFANA_URL}/api/admin/users" \
    -d "{\"name\":\"${GRAFANA_NEW_USER}\",\"login\":\"${GRAFANA_NEW_USER}\",\"password\":\"${GRAFANA_NEW_PASSWORD}\",\"email\":\"\"}" >/dev/null
  USER_JSON="$(lookup)"
  USER_ID="$(echo "$USER_JSON" | grep -o '"id"[: ]*[0-9]*' | head -n1 | cut -d: -f2 | tr -d ' ')"
fi

if [ -n "${USER_ID}" ]; then
  echo "Ensuring password is updated for ${GRAFANA_NEW_USER}"
  curl -sf -u "${GRAFANA_ADMIN_USER}:${GRAFANA_ADMIN_PASSWORD}" \
    -H 'Content-Type: application/json' \
    -X PUT "${GRAFANA_URL}/api/admin/users/${USER_ID}/password" \
    -d "{\"password\":\"${GRAFANA_NEW_PASSWORD}\"}" >/dev/null || true

  echo "Setting role ${GRAFANA_NEW_ROLE} in default org"
  # Try PATCH first
  curl -s -o /dev/null -w '%{http_code}' -u "${GRAFANA_ADMIN_USER}:${GRAFANA_ADMIN_PASSWORD}" \
    -H 'Content-Type: application/json' \
    -X PATCH "${GRAFANA_URL}/api/orgs/1/users/${USER_ID}" \
    -d "{\"role\":\"${GRAFANA_NEW_ROLE}\"}" | grep -E '^(2|3)[0-9][0-9]$' >/dev/null || {
      # Fallback: POST add user to org
      curl -sf -u "${GRAFANA_ADMIN_USER}:${GRAFANA_ADMIN_PASSWORD}" \
        -H 'Content-Type: application/json' \
        -X POST "${GRAFANA_URL}/api/orgs/1/users" \
        -d "{\"loginOrEmail\":\"${GRAFANA_NEW_USER}\",\"role\":\"${GRAFANA_NEW_ROLE}\"}" >/dev/null || true
    }
fi

echo "Grafana user provisioning complete."

