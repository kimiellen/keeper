#!/bin/bash
set -euo pipefail

CERT_DIR="$(dirname "$0")/../certs"
mkdir -p "$CERT_DIR"

if command -v mkcert &>/dev/null; then
    echo "Using mkcert..."
    mkcert -install
    mkcert -key-file "$CERT_DIR/localhost+2-key.pem" \
           -cert-file "$CERT_DIR/localhost+2.pem" \
           localhost 127.0.0.1 ::1
else
    echo "mkcert not found, falling back to openssl..."
    openssl req -x509 -newkey rsa:2048 \
        -keyout "$CERT_DIR/localhost+2-key.pem" \
        -out "$CERT_DIR/localhost+2.pem" \
        -days 3650 -nodes \
        -subj "/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:::1"
fi

echo "Certificates generated in $CERT_DIR/"
ls -la "$CERT_DIR/"
