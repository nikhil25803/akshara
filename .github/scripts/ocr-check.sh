#!/usr/bin/env bash

set -uo pipefail

if [ "$#" -ne 4 ]; then
  echo "usage: $0 LABEL FIXTURE EXPECTED_MIME EXPECTED_SOURCE" >&2
  exit 2
fi

label="$1"
fixture="$2"
expected_mime="$3"
expected_source="$4"
response="/tmp/akshara-${label,,}.json"

mime="—"
pages="—"
characters="—"
warnings="—"
source="—"
result="Failed"

if metrics="$(
  curl --silent --show-error --max-time 300 \
    --output "$response" \
    --write-out $'%{http_code}\t%{time_total}' \
    --header "api_key: ${API_KEY}" \
    --form "file=@${fixture}" \
    "http://127.0.0.1:8000/v1/ocr?language=en&extraction_source=true"
)"; then
  IFS=$'\t' read -r http_code duration <<< "$metrics"
else
  http_code="000"
  duration="timeout"
fi

echo "${label} OCR API response:"
if [ -s "$response" ]; then
  python3 -m json.tool "$response"
else
  echo "No response body received."
fi

if [ "$http_code" = "200" ] && details="$(
  python3 - "$response" "$expected_mime" "$expected_source" <<'PY'
import json
import sys

response_path, expected_mime, expected_source = sys.argv[1:]
with open(response_path) as response_file:
    data = json.load(response_file)

assert data.get("mime_type") == expected_mime, "unexpected MIME type"
assert data.get("language") == "en", "unexpected OCR language"
assert isinstance(data.get("text"), str) and data["text"].strip(), "empty text"
assert isinstance(data.get("page_count"), int) and data["page_count"] >= 1, (
    "invalid page count"
)
assert isinstance(data.get("warnings"), list), "invalid warnings"
assert isinstance(data.get("pages"), list), "missing page details"
assert len(data["pages"]) == data["page_count"], (
    "page details do not match page count"
)

sources = sorted({page.get("extraction_source") for page in data["pages"]})
assert sources == [expected_source], "unexpected extraction source"
print(
    data["mime_type"],
    data["page_count"],
    len(data["text"]),
    len(data["warnings"]),
    ", ".join(sources),
    sep="\t",
)
PY
)"; then
  IFS=$'\t' read -r mime pages characters warnings source <<< "$details"
  result="Passed"
fi

if [ "$duration" = "timeout" ]; then
  duration_display="$duration"
else
  duration_display="${duration}s"
fi

printf '%s OCR metrics: HTTP=%s, MIME=%s, Source=%s, Pages=%s, Characters=%s, Warnings=%s, Duration=%s, Result=%s\n' \
  "$label" "$http_code" "$mime" "$source" "$pages" "$characters" \
  "$warnings" "$duration_display" "$result"

printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
  "$label" "$http_code" "$mime" "$source" "$pages" "$characters" \
  "$warnings" "$duration_display" "$result" >> "$GITHUB_STEP_SUMMARY"

if [ "$result" != "Passed" ]; then
  exit 1
fi
