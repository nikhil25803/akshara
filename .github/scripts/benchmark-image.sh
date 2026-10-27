#!/usr/bin/env bash
set -Eeuo pipefail

if [ "$#" -ne 6 ]; then
  echo "usage: benchmark-image.sh IMAGE LABEL CONTAINER PORT SETUP_MS OUTPUT_DIR" >&2
  exit 2
fi

image="$1"
label="$2"
container="$3"
port="$4"
setup_ms="$5"
output_dir="$6"
inspect_container="${container}-inspect"
api_key="benchmark-api-key-with-at-least-32-characters"

mkdir -p "$output_dir"
touch "$output_dir/container.log"

now_ms() {
  date +%s%3N
}

seconds() {
  awk -v milliseconds="$1" 'BEGIN { printf "%.3f s", milliseconds / 1000 }'
}

cleanup() {
  docker logs --timestamps "$container" > "$output_dir/container.log" 2>&1 || true
  docker rm --force "$container" "$inspect_container" >/dev/null 2>&1 || true
}
trap cleanup EXIT

content_bytes="$(docker image inspect --format '{{.Size}}' "$image")"
docker create --name "$inspect_container" "$image" >/dev/null
installed_bytes="$(docker export "$inspect_container" | wc -c | tr -d ' ')"
docker rm "$inspect_container" >/dev/null

startup_started="$(now_ms)"
docker run --detach \
  --name "$container" \
  --publish "$port:8000" \
  --env ENABLE_LLM=false \
  --env OCR_LANGUAGES=en \
  --env API_KEY="$api_key" \
  --tmpfs /models:rw,size=1g,mode=1777 \
  "$image" >/dev/null

ready=false
for _ in {1..900}; do
  if curl --fail --silent --max-time 2 \
    "http://127.0.0.1:$port/health" > "$output_dir/health.json"; then
    ready=true
    break
  fi
  sleep 1
done
if [ "$ready" != true ]; then
  echo "$label did not become healthy within 15 minutes" >&2
  exit 1
fi
startup_ms=$(( $(now_ms) - startup_started ))

test "$(docker exec "$container" id -u)" = "10001"
docker exec "$container" sh -c 'test -w /models'
docker exec "$container" /app/.venv/bin/python -c 'import paddle, paddleocr'

curl --fail --silent --show-error "http://127.0.0.1:$port/" \
  > "$output_dir/root.json"
version="$(python3 -c "import json; print(json.load(open('$output_dir/root.json'))['version'])")"
python3 -c "import json; data=json.load(open('$output_dir/root.json')); assert data['name'] == 'Akshara'"
python3 -c "import json; data=json.load(open('$output_dir/health.json')); assert data['status'] == 'ok' and data['paddleocr'] is True"

auth_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  "http://127.0.0.1:$port/docs")"
test "$auth_status" = "401"

first_started="$(now_ms)"
if ! first_status="$(curl --silent --show-error --max-time 900 \
  --output "$output_dir/first-ocr.json" \
  --write-out '%{http_code}' \
  --request POST \
  --header "api_key: $api_key" \
  --form 'file=@assets/img/banner.png;type=image/png' \
  "http://127.0.0.1:$port/v1/ocr?language=en")"; then
  echo "$label first OCR request failed or timed out" >&2
  exit 1
fi
first_ms=$(( $(now_ms) - first_started ))
test "$first_status" = "200"
python3 -c "import json; data=json.load(open('$output_dir/first-ocr.json')); assert data['text'].strip()"

warm_started="$(now_ms)"
if ! warm_status="$(curl --silent --show-error --max-time 900 \
  --output "$output_dir/warm-ocr.json" \
  --write-out '%{http_code}' \
  --request POST \
  --header "api_key: $api_key" \
  --form 'file=@assets/img/banner.png;type=image/png' \
  "http://127.0.0.1:$port/v1/ocr?language=en")"; then
  echo "$label warm OCR request failed or timed out" >&2
  exit 1
fi
warm_ms=$(( $(now_ms) - warm_started ))
test "$warm_status" = "200"
python3 -c "import json; data=json.load(open('$output_dir/warm-ocr.json')); assert data['text'].strip()"

content_size="$(numfmt --to=iec-i --suffix=B "$content_bytes")"
installed_size="$(numfmt --to=iec-i --suffix=B "$installed_bytes")"
total_ms=$(( startup_ms + first_ms ))
summary_file="${GITHUB_STEP_SUMMARY:-/dev/stdout}"
echo "| $label ($version) | $(seconds "$setup_ms") | $content_size | $installed_size | $(seconds "$startup_ms") | $(seconds "$first_ms") | $(seconds "$warm_ms") | $(seconds "$total_ms") |" \
  >> "$summary_file"
