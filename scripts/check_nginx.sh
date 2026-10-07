#!/bin/bash
# Isolated syntax check with disposable certificates; never reloads host Nginx.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
stage=$(mktemp -d)
container=''
cleanup() {
    if [[ -n "$container" ]]; then
        docker rm -f "$container" >/dev/null 2>&1 || true
    fi
    rm -rf "$stage"
}
trap cleanup EXIT
nginx_image=${NGINX_TEST_IMAGE:-nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236}
mkdir -p "$stage/certs" "$stage/snippets"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj '/CN=pcep.micutu.com' -keyout "$stage/certs/privkey.pem" -out "$stage/certs/fullchain.pem" 2>/dev/null
cp "$root"/nginx/snippets/pcep-*.conf "$stage/snippets/"
printf 'location ~ /\\. { deny all; }\n' > "$stage/snippets/block-dotfiles.conf"
# Shared variables/includes are provided by the actual production host.
sed -e '/include \/etc\/letsencrypt\/options-ssl-nginx.conf;/d' -e '/ssl_dhparam \/etc\/letsencrypt\/ssl-dhparams.pem;/d' "$root/nginx/pcep.micutu.com.conf" > "$stage/pcep.conf"
# shellcheck disable=SC2016 # Nginx variable must remain literal.
printf 'geo $from_cloudflare_origin { default 1; }\n' > "$stage/shared.conf"
mounts=(
    -v "$stage/pcep.conf:/etc/nginx/conf.d/default.conf:ro"
    -v "$stage/shared.conf:/etc/nginx/conf.d/shared.conf:ro"
    -v "$stage/snippets:/etc/nginx/snippets:ro"
    -v "$stage/certs:/etc/letsencrypt/live/pcep.micutu.com:ro"
)
docker run --rm --network none "${mounts[@]}" "$nginx_image" nginx -t

# Exercise responses generated inside Nginx. A syntax check cannot detect header
# inheritance drift in named error locations.
head -c 70000 /dev/zero | tr '\0' x > "$stage/oversized.json"
container=$(docker run -d --rm -p 127.0.0.1::443 "${mounts[@]}" "$nginx_image")
port=$(docker port "$container" 443/tcp)
port=${port##*:}
base_url="https://pcep.micutu.com:$port"

for admin_path in /admin /admin/login/; do
    admin_label=${admin_path//\//_}
    status=$(curl --http1.1 --insecure --silent --show-error \
        --resolve "pcep.micutu.com:$port:127.0.0.1" \
        --dump-header "$stage/$admin_label.headers" \
        --output "$stage/$admin_label.body" \
        --write-out '%{http_code}' "$base_url$admin_path")
    [[ "$status" == 404 ]]
    tr -d '\r' < "$stage/$admin_label.headers" > "$stage/$admin_label.headers.clean"
    grep -Fqi 'Cache-Control: no-store' "$stage/$admin_label.headers.clean"
    grep -Fqi "Content-Security-Policy: default-src 'none'; frame-ancestors 'none'" "$stage/$admin_label.headers.clean"
    grep -Fqi 'X-Content-Type-Options: nosniff' "$stage/$admin_label.headers.clean"
    grep -Fqi 'X-Frame-Options: DENY' "$stage/$admin_label.headers.clean"
    grep -Eqi '^X-Request-ID: [0-9a-f]{32}$' "$stage/$admin_label.headers.clean"
    ! grep -Eqi '^Set-Cookie:' "$stage/$admin_label.headers.clean"
    ! grep -Eqi 'Django administration|admin login' "$stage/$admin_label.body"
done

status=''
for _ in $(seq 1 30); do
    status=$(curl --http1.1 --insecure --silent --show-error \
        --resolve "pcep.micutu.com:$port:127.0.0.1" \
        --header 'Content-Type: application/json' \
        --request POST --data-binary "@$stage/oversized.json" \
        --dump-header "$stage/413.headers" --output "$stage/413.body" \
        --write-out '%{http_code}' "$base_url/api/grade/" 2>/dev/null || true)
    [[ "$status" == 413 ]] && break
    sleep 0.1
done
[[ "$status" == 413 ]]
tr -d '\r' < "$stage/413.headers" > "$stage/413.headers.clean"
grep -Fqi 'Content-Type: application/json' "$stage/413.headers.clean"
grep -Fqi 'Cache-Control: no-store' "$stage/413.headers.clean"
grep -Fqi "Content-Security-Policy: default-src 'none'; frame-ancestors 'none'" "$stage/413.headers.clean"
grep -Eqi '^X-Request-ID: [0-9a-f]{32}$' "$stage/413.headers.clean"
grep -Fqx '{"detail":"Request body is too large."}' "$stage/413.body"

status=''
for _ in $(seq 1 60); do
    status=$(curl --http1.1 --insecure --silent --show-error \
        --resolve "pcep.micutu.com:$port:127.0.0.1" \
        --dump-header "$stage/429.headers" --output "$stage/429.body" \
        --write-out '%{http_code}' "$base_url/api/stats/" 2>/dev/null || true)
    [[ "$status" == 429 ]] && break
done
[[ "$status" == 429 ]]
tr -d '\r' < "$stage/429.headers" > "$stage/429.headers.clean"
grep -Fqi 'Content-Type: application/json' "$stage/429.headers.clean"
grep -Fqi 'Cache-Control: no-store' "$stage/429.headers.clean"
grep -Fqi "Content-Security-Policy: default-src 'none'; frame-ancestors 'none'" "$stage/429.headers.clean"
grep -Fqi 'Retry-After: 1' "$stage/429.headers.clean"
grep -Eqi '^X-Request-ID: [0-9a-f]{32}$' "$stage/429.headers.clean"
grep -Fqx '{"detail":"Too many requests. Please wait and retry."}' "$stage/429.body"

printf '%s\n' 'Nginx syntax, disabled admin and generated API error contracts: OK'
