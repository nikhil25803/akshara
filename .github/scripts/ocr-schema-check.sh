#!/usr/bin/env bash

set -uo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 LABEL FIXTURE SCHEMA" >&2
  exit 2
fi

label="$1"
fixture="$2"
schema="$3"
response="/tmp/akshara-schema-${label,,}.json"
result="Failed"

echo "${label} schema curl request:"
printf 'curl --request POST --header "api_key: ***" --form "file=@%s" --form "schema=<%s;type=application/json" "%s"\n' \
  "$fixture" "$schema" \
  "http://127.0.0.1:8000/v1/ocr/schema?language=en"

if metrics="$(
  curl --silent --show-error --max-time 300 \
    --output "$response" \
    --write-out $'%{http_code}\t%{time_total}' \
    --header "api_key: ${API_KEY}" \
    --form "file=@${fixture}" \
    --form "schema=<${schema};type=application/json" \
    "http://127.0.0.1:8000/v1/ocr/schema?language=en"
)"; then
  IFS=$'\t' read -r http_code duration <<< "$metrics"
else
  http_code="000"
  duration="timeout"
fi

echo "${label} schema extraction API response:"
if [ -s "$response" ]; then
  python3 -m json.tool "$response"
else
  echo "No response body received."
fi

if [ "$http_code" = "200" ]; then
  result="Passed"
fi

if [ "$duration" = "timeout" ]; then
  duration_display="$duration"
else
  duration_display="${duration}s"
fi

printf '%s schema metrics: HTTP=%s, Duration=%s, Result=%s\n' \
  "$label" "$http_code" "$duration_display" "$result"
printf '%s\t%s\t%s\t%s\n' \
  "$label" "$http_code" "$duration_display" "$result" \
  >> /tmp/akshara-schema-results.tsv

if [ "$result" != "Passed" ]; then
  exit 1
fi
