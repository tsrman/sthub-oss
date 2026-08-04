#!/usr/bin/env bash
# Generate a local, self-signed TLS certificate for the HTTPS (:443) sample stack.
#
# Output (git-ignored):
#   certs/local.crt   — certificate (also usable as the CA to trust)
#   certs/local.key   — private key
#
# The cert is valid for `localhost`, `127.0.0.1` and any *.localhost host, so the
# whole stack is reachable at https://localhost/. Override the primary name with:
#   CERT_HOST=sthub.local ./certs/generate-certs.sh
set -euo pipefail

cd "$(dirname "$0")"

HOST="${CERT_HOST:-localhost}"
DAYS="${CERT_DAYS:-825}"

openssl req -x509 -newkey rsa:2048 -sha256 -nodes \
  -keyout local.key -out local.crt -days "$DAYS" \
  -subj "/CN=${HOST}/O=sthub-local" \
  -addext "subjectAltName=DNS:${HOST},DNS:localhost,DNS:*.localhost,IP:127.0.0.1"

chmod 600 local.key
echo "Generated local.crt / local.key for '${HOST}' (valid ${DAYS} days)."
echo "Trust certs/local.crt in your browser/OS to avoid the warning."
