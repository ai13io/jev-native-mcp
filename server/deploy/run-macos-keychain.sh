#!/bin/sh
set -eu
umask 077

deploy_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
server_dir=$(CDPATH= cd -- "$deploy_dir/.." && pwd)

: "${JEV_PYTHON:=$server_dir/.venv/bin/python}"
: "${JEV_KEYCHAIN_ACCOUNT:=${USER:?USER is not set}}"
: "${JEV_KEYCHAIN_SERVICE:=jev-native-typesafe-api-key}"
: "${JEV_RECEIPT_KEYCHAIN_SERVICE:=jev-native-receipt-hmac-key}"
: "${JEV_MCP_HOST:=127.0.0.1}"
: "${JEV_MCP_PORT:=8765}"
: "${JEV_BUDGET_PATH:=$server_dir/runtime/usage.json}"
: "${JEV_RECEIPT_DIR:=$server_dir/runtime/receipts-v2}"

TYPESAFE_API_KEY=$(
  /usr/bin/security find-generic-password \
    -a "$JEV_KEYCHAIN_ACCOUNT" \
    -s "$JEV_KEYCHAIN_SERVICE" \
    -w
)
JEV_RECEIPT_HMAC_KEY=$(
  /usr/bin/security find-generic-password \
    -a "$JEV_KEYCHAIN_ACCOUNT" \
    -s "$JEV_RECEIPT_KEYCHAIN_SERVICE" \
    -w
)
export TYPESAFE_API_KEY JEV_RECEIPT_HMAC_KEY JEV_MCP_HOST JEV_MCP_PORT JEV_BUDGET_PATH JEV_RECEIPT_DIR

cd "$server_dir"
exec "$JEV_PYTHON" "$server_dir/server.py"
