#!/usr/bin/env bash
# Regenere le certificat serveur du broker MQTT, signe par la CA interne.
# Usage : bash security/gen-certs.sh <IP du PC broker>
set -euo pipefail
export MSYS_NO_PATHCONV=1

IP="${1:?Usage : bash security/gen-certs.sh <IP du PC broker>}"
CERTS=docker/mosquitto/certs
CA=security/ca

openssl req -new -key "$CERTS/server.key" -subj "/CN=$IP" -out "$CA/server.csr"

printf 'subjectAltName=IP:%s,DNS:%s,IP:127.0.0.1,DNS:localhost\n' "$IP" "$IP" > "$CA/san.ext"

openssl x509 -req -in "$CA/server.csr" \
  -CA "$CERTS/ca.crt" -CAkey "$CA/ca.key" \
  -CAserial "$CA/ca.srl" -CAcreateserial \
  -days 365 -sha256 -extfile "$CA/san.ext" \
  -out "$CERTS/server.crt"

rm -f "$CA/server.csr" "$CA/san.ext"
echo "OK : certificat serveur emis pour $IP"
