#!/bin/bash
# Isolated syntax check with disposable certificates; never reloads host Nginx.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
stage=$(mktemp -d)
container=''

assert_absent() {
    local label=$1
    shift
    local status

    if grep "$@"; then
        printf 'Nginx check failed: forbidden %s is present.\n' "$label" >&2
        return 1
    else
        status=$?
    fi
    # grep returns 1 only for a clean "no match". Missing/unreadable fixtures
    # and every other execution error must fail the security check as well.
    [[ $status -eq 1 ]] || return "$status"
}

cleanup() {
    if [[ -n "$container" ]]; then
        docker rm -f "$container" >/dev/null 2>&1 || true
    fi
    rm -rf "$stage"
}
trap cleanup EXIT
nginx_image=${NGINX_TEST_IMAGE:-nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236}
mkdir -p "$stage/certs" "$stage/snippets" "$stage/frontend/pyodide" \
    "$stage/operations-health" \
    "$stage/frontend/.well-known" \
    "$stage/frontend/pyodide.previous.audit" "$stage/static/admin/css" \
    "$stage/media"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj '/CN=pcep.micutu.com' -keyout "$stage/certs/privkey.pem" -out "$stage/certs/fullchain.pem" 2>/dev/null
cp "$root"/nginx/snippets/pcep-*.conf "$stage/snippets/"
cp "$root/frontend/public/runner.html" "$root/frontend/public/runner-bridge.js" \
    "$root/frontend/public/py-worker.js" "$stage/frontend/"
cp "$root/frontend/index.html" "$stage/frontend/index.html"
cp "$root/frontend/public/.well-known/security.txt" \
    "$stage/frontend/.well-known/security.txt"
# The Ops job intentionally does not download the 12 MB runtime. This fixture
# exercises Nginx routing only; fetch/build and production smoke verify the real
# pinned runtime independently.
printf '%s\n' '0.29.4' > "$stage/frontend/pyodide/VERSION"
printf '%s\n' '{"checked_at":"2026-10-13T09:00:00Z","schema":1,"status":"ok"}' \
    > "$stage/operations-health/status.json"
printf '%s\n' 'must never be published' \
    > "$stage/frontend/pyodide.previous.audit/pyodide.js"
printf '%s\n' 'must never be published' > "$stage/static/admin/css/base.css"
printf '%s\n' 'must never be published' > "$stage/media/probe.txt"
printf 'location ~ /\\. { deny all; }\n' > "$stage/snippets/block-dotfiles.conf"
# Shared variables/includes are provided by the actual production host.
sed -e '/include \/etc\/letsencrypt\/options-ssl-nginx.conf;/d' -e '/ssl_dhparam \/etc\/letsencrypt\/ssl-dhparams.pem;/d' "$root/nginx/pcep.micutu.com.conf" > "$stage/pcep.conf"
sed -e '/include \/etc\/letsencrypt\/options-ssl-nginx.conf;/d' -e '/ssl_dhparam \/etc\/letsencrypt\/ssl-dhparams.pem;/d' "$root/nginx/pcep-runner.micutu.com.conf" > "$stage/pcep-runner.conf"
# shellcheck disable=SC2016 # Nginx variables must remain literal.
printf '%s\n' \
    'geo $from_cloudflare_origin { default 1; }' \
    'server {' \
    '    listen 127.0.0.1:3010;' \
    '    server_name analytics-fixture;' \
    '    if ($http_cookie != "") { return 418; }' \
    '    if ($http_authorization != "") { return 418; }' \
    '    if ($http_proxy_authorization != "") { return 418; }' \
    '    if ($http_x_csrftoken != "") { return 418; }' \
    '    if ($http_x_xsrf_token != "") { return 418; }' \
    '    location = /script.js {' \
    '        default_type application/javascript;' \
    '        add_header Set-Cookie "tracker=bad; Path=/" always;' \
    '        add_header WWW-Authenticate "Basic realm=bad" always;' \
    '        add_header Location "https://attacker.invalid/" always;' \
    '        add_header Content-Security-Policy "script-src *" always;' \
    '        add_header X-Accel-Redirect "/should-not-run" always;' \
    '        add_header X-Accel-Limit-Rate "1" always;' \
    '        return 200 "window.fixtureAnalytics=true;";' \
    '    }' \
    '    location = /api/send {' \
    '        add_header Set-Cookie "tracker=bad; Path=/" always;' \
    '        add_header WWW-Authenticate "Basic realm=bad" always;' \
    '        add_header Location "https://attacker.invalid/" always;' \
    '        add_header Content-Security-Policy "script-src *" always;' \
    '        add_header X-Accel-Redirect "/should-not-run" always;' \
    '        return 204;' \
    '    }' \
    '}' \
    'server {' \
    '    listen 127.0.0.1:8001;' \
    '    server_name backend-fixture;' \
    '    location = /api/stats/ {' \
    '        default_type application/json;' \
    '        return 200 "{}";' \
    '    }' \
    '    location = /api/error-probe/ {' \
    '        return 444;' \
    '    }' \
    '}' > "$stage/shared.conf"
mounts=(
    # Match sites-enabled ordering: pcep-runner sorts before pcep.micutu.com.
    -v "$stage/pcep.conf:/etc/nginx/conf.d/pcep.micutu.com.conf:ro"
    -v "$stage/pcep-runner.conf:/etc/nginx/conf.d/pcep-runner.micutu.com.conf:ro"
    -v "$stage/shared.conf:/etc/nginx/conf.d/shared.conf:ro"
    -v "$stage/snippets:/etc/nginx/snippets:ro"
    -v "$stage/certs:/etc/letsencrypt/live/pcep.micutu.com:ro"
    -v "$stage/frontend:/var/www/pcep/frontend:ro"
    -v "$stage/static:/var/www/pcep/static:ro"
    -v "$stage/media:/var/www/pcep/media:ro"
    -v "$stage/operations-health/status.json:/var/lib/pcep-operations-health/status.json:ro"
)
docker run --rm --network none "${mounts[@]}" "$nginx_image" nginx -t

# shellcheck disable=SC2016 # Nginx variable must remain literal.
grep -Fqx 'limit_req_zone $binary_remote_addr zone=pcep_api:10m rate=10r/s;' \
    "$root/nginx/pcep.micutu.com.conf"
grep -Fqx '        limit_req zone=pcep_api burst=60 nodelay;' \
    "$root/nginx/pcep.micutu.com.conf"
grep -Fqx '    limit_req_log_level notice;' \
    "$root/nginx/pcep.micutu.com.conf"
grep -Fqx '        error_log /var/log/nginx/pcep_error.log crit;' \
    "$root/nginx/pcep.micutu.com.conf"
assert_absent 'static filesystem alias' \
    -Fq 'alias /var/www/pcep/static/' "$root/nginx/pcep.micutu.com.conf"
assert_absent 'media filesystem alias' \
    -Fq 'alias /var/www/pcep/media/' "$root/nginx/pcep.micutu.com.conf"

analytics_snippet="$root/nginx/snippets/pcep-analytics-proxy.conf"
[[ $(grep -Fc 'include snippets/pcep-analytics-proxy.conf;' \
    "$root/nginx/pcep.micutu.com.conf") -eq 2 ]]
for analytics_boundary in \
    'proxy_set_header Cookie "";' \
    'proxy_set_header Authorization "";' \
    'proxy_hide_header Set-Cookie;' \
    'proxy_hide_header WWW-Authenticate;' \
    'proxy_hide_header Location;' \
    'proxy_hide_header Content-Security-Policy;' \
    'proxy_ignore_headers X-Accel-Redirect X-Accel-Expires X-Accel-Limit-Rate X-Accel-Buffering X-Accel-Charset Set-Cookie;'
do
    grep -Fqx "$analytics_boundary" "$analytics_snippet"
done

# Exercise responses generated inside Nginx. A syntax check cannot detect header
# inheritance drift in named error locations.
head -c 70000 /dev/zero | tr '\0' x > "$stage/oversized.json"
container=$(docker run -d --rm -p 127.0.0.1::443 "${mounts[@]}" "$nginx_image")
port=$(docker port "$container" 443/tcp)
port=${port##*:}
base_url="https://pcep.micutu.com:$port"
runner_url="https://pcep-runner.micutu.com:$port"

status=''
for _ in $(seq 1 30); do
    status=$(curl --http1.1 --insecure --silent --show-error \
        --resolve "pcep-runner.micutu.com:$port:127.0.0.1" \
        --dump-header "$stage/runner.headers" --output "$stage/runner.body" \
        --write-out '%{http_code}' "$runner_url/runner.html" 2>/dev/null || true)
    [[ "$status" == 200 ]] && break
    sleep 0.1
done
[[ "$status" == 200 ]]
tr -d '\r' < "$stage/runner.headers" > "$stage/runner.headers.clean"
grep -Fqi 'Content-Type: text/html' "$stage/runner.headers.clean"
grep -Fqi 'Cache-Control: no-store' "$stage/runner.headers.clean"
grep -Fqi 'Cross-Origin-Resource-Policy: same-origin' "$stage/runner.headers.clean"
grep -Fqi 'Referrer-Policy: no-referrer' "$stage/runner.headers.clean"
grep -Fqi 'Origin-Agent-Cluster: ?1' "$stage/runner.headers.clean"
grep -Fqi "frame-ancestors https://pcep.micutu.com" "$stage/runner.headers.clean"
grep -Fqi "script-src 'self'; worker-src 'self'; connect-src 'none'" "$stage/runner.headers.clean"
assert_absent 'runner X-Frame-Options header' \
    -Eqi '^X-Frame-Options:' "$stage/runner.headers.clean"
assert_absent 'runner Set-Cookie header' \
    -Eqi '^Set-Cookie:' "$stage/runner.headers.clean"
grep -Fq '<script src="/runner-bridge.js" defer></script>' "$stage/runner.body"

status=$(curl --http1.1 --insecure --silent --show-error \
    --resolve "pcep.micutu.com:$port:127.0.0.1" \
    --dump-header "$stage/shell.headers" --output "$stage/shell.body" \
    --write-out '%{http_code}' "$base_url/")
[[ "$status" == 200 ]]
tr -d '\r' < "$stage/shell.headers" > "$stage/shell.headers.clean"
grep -Fqi "script-src 'self'; connect-src 'self'" "$stage/shell.headers.clean"
assert_absent 'Cloudflare browser-insights policy' \
    -Fqi 'cloudflareinsights.com' "$stage/shell.headers.clean"

status=$(curl --http1.1 --insecure --silent --show-error \
    --resolve "pcep.micutu.com:$port:127.0.0.1" \
    --dump-header "$stage/operations.headers" \
    --output "$stage/operations.body" \
    --write-out '%{http_code}' "$base_url/.well-known/pcep-operations.json")
[[ "$status" == 200 ]]
tr -d '\r' < "$stage/operations.headers" > "$stage/operations.headers.clean"
grep -Fqi 'Content-Type: application/json' "$stage/operations.headers.clean"
grep -Fqi 'Cache-Control: no-store' "$stage/operations.headers.clean"
grep -Fqi "Content-Security-Policy: default-src 'none'; frame-ancestors 'none'" \
    "$stage/operations.headers.clean"
grep -Fqx \
    '{"checked_at":"2026-10-13T09:00:00Z","schema":1,"status":"ok"}' \
    "$stage/operations.body"

status=$(curl --http1.1 --insecure --silent --show-error \
    --resolve "pcep.micutu.com:$port:127.0.0.1" \
    --request POST --output /dev/null --write-out '%{http_code}' \
    "$base_url/.well-known/pcep-operations.json")
[[ "$status" == 403 ]]

status=$(curl --http1.1 --insecure --silent --show-error \
    --resolve "pcep.micutu.com:$port:127.0.0.1" \
    --dump-header "$stage/security-txt.headers" \
    --output "$stage/security-txt.body" \
    --write-out '%{http_code}' "$base_url/.well-known/security.txt")
[[ "$status" == 200 ]]
tr -d '\r' < "$stage/security-txt.headers" \
    > "$stage/security-txt.headers.clean"
grep -Fqi 'Content-Type: text/plain' "$stage/security-txt.headers.clean"
grep -Fqi 'Cache-Control: no-cache, no-store, must-revalidate' \
    "$stage/security-txt.headers.clean"
grep -Fqi "Content-Security-Policy: default-src 'none'; frame-ancestors 'none'" \
    "$stage/security-txt.headers.clean"
assert_absent 'security.txt Set-Cookie header' \
    -Eqi '^Set-Cookie:' "$stage/security-txt.headers.clean"
cmp "$root/frontend/public/.well-known/security.txt" "$stage/security-txt.body"

status=$(curl --http1.1 --insecure --silent --show-error \
    --resolve "pcep.micutu.com:$port:127.0.0.1" \
    --request POST --output /dev/null --write-out '%{http_code}' \
    "$base_url/.well-known/security.txt")
[[ "$status" == 403 ]]

# SPA fallback must retain the original path for detection without logging the
# query string (which can contain search terms or other user-supplied data).
status=$(curl --http1.1 --insecure --silent --show-error \
    --resolve "pcep.micutu.com:$port:127.0.0.1" \
    --output /dev/null --write-out '%{http_code}' \
    "$base_url/audit/original-path?audit-query-canary=must-not-be-logged")
[[ "$status" == 200 ]]
docker exec "$container" cat /var/log/nginx/pcep_access.log > "$stage/pcep-access.log"
grep -Fq '"path":"/audit/original-path"' "$stage/pcep-access.log"
assert_absent 'Nginx access-log query string' \
    -Fq 'audit-query-canary' "$stage/pcep-access.log"

status=$(curl --http1.1 --insecure --silent --show-error \
    --resolve "pcep.micutu.com:$port:127.0.0.1" \
    --header 'Cookie: learner=secret' \
    --header 'Authorization: Bearer secret' \
    --header 'Proxy-Authorization: Basic secret' \
    --header 'X-CSRFToken: secret' \
    --header 'X-XSRF-TOKEN: secret' \
    --dump-header "$stage/analytics-script.headers" \
    --output "$stage/analytics-script.body" \
    --write-out '%{http_code}' "$base_url/u/script.js")
[[ "$status" == 200 ]]
tr -d '\r' < "$stage/analytics-script.headers" \
    > "$stage/analytics-script.headers.clean"
grep -Fqi 'Content-Type: application/javascript' \
    "$stage/analytics-script.headers.clean"
grep -Fqi "script-src 'self'; connect-src 'self'" \
    "$stage/analytics-script.headers.clean"
assert_absent 'analytics-script credential or redirect response header' \
    -Eqi '^Set-Cookie:|^WWW-Authenticate:|^Location:' \
    "$stage/analytics-script.headers.clean"
grep -Fqx 'window.fixtureAnalytics=true;' "$stage/analytics-script.body"

status=$(curl --http1.1 --insecure --silent --show-error \
    --resolve "pcep.micutu.com:$port:127.0.0.1" \
    --dump-header "$stage/analytics.headers" --output "$stage/analytics.body" \
    --write-out '%{http_code}' "$base_url/u/api/send")
[[ "$status" == 403 ]]
tr -d '\r' < "$stage/analytics.headers" > "$stage/analytics.headers.clean"
grep -Fqi 'Cache-Control: no-store' "$stage/analytics.headers.clean"
grep -Fqi "Content-Security-Policy: default-src 'none'; frame-ancestors 'none'" \
    "$stage/analytics.headers.clean"
assert_absent 'rejected analytics credential or redirect response header' \
    -Eqi '^Set-Cookie:|^WWW-Authenticate:|^Location:' \
    "$stage/analytics.headers.clean"

status=$(curl --http1.1 --insecure --silent --show-error \
    --resolve "pcep.micutu.com:$port:127.0.0.1" \
    --header 'Content-Type: application/json' \
    --header 'Cookie: learner=secret' \
    --header 'Authorization: Bearer secret' \
    --header 'X-CSRFToken: secret' \
    --request POST --data '{}' \
    --dump-header "$stage/analytics-post.headers" \
    --output "$stage/analytics-post.body" \
    --write-out '%{http_code}' "$base_url/u/api/send")
[[ "$status" == 204 ]]
tr -d '\r' < "$stage/analytics-post.headers" > "$stage/analytics-post.headers.clean"
grep -Fqi 'Cache-Control: no-store' "$stage/analytics-post.headers.clean"
grep -Fqi "Content-Security-Policy: default-src 'none'; frame-ancestors 'none'" \
    "$stage/analytics-post.headers.clean"
assert_absent 'analytics credential or redirect response header' \
    -Eqi '^Set-Cookie:|^WWW-Authenticate:|^Location:' \
    "$stage/analytics-post.headers.clean"

for runner_path in /runner-bridge.js /py-worker.js /pyodide/VERSION; do
    runner_label=${runner_path//\//_}
    status=$(curl --http1.1 --insecure --silent --show-error \
        --resolve "pcep-runner.micutu.com:$port:127.0.0.1" \
        --dump-header "$stage/$runner_label.headers" \
        --output "$stage/$runner_label.body" \
        --write-out '%{http_code}' "$runner_url$runner_path")
    [[ "$status" == 200 ]]
    tr -d '\r' < "$stage/$runner_label.headers" > "$stage/$runner_label.headers.clean"
    grep -Fqi 'Cache-Control: no-store' "$stage/$runner_label.headers.clean"
    grep -Fqi 'Cross-Origin-Resource-Policy: same-origin' "$stage/$runner_label.headers.clean"
    assert_absent "runner asset $runner_path Set-Cookie header" \
        -Eqi '^Set-Cookie:' "$stage/$runner_label.headers.clean"
done
grep -Fqi "script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'" \
    "$stage/_py-worker.js.headers.clean"

status=$(curl --http1.1 --insecure --silent --show-error \
    --resolve "pcep-runner.micutu.com:$port:127.0.0.1" \
    --output /dev/null --write-out '%{http_code}' "$runner_url/api/live/")
[[ "$status" == 404 ]]

for isolated_path in \
    /runner.html /runner.html/probe /runner-bridge.js \
    /runner-bridge.js/probe /py-worker.js /py-worker.js/probe \
    /pyodide /pyodide/VERSION /pyodide.previous.audit/pyodide.js \
    /%72unner.html /runner.html%2fprobe /%70y-worker.js \
    /pyodide%2fVERSION /x/../pyodide/VERSION //pyodide/VERSION
do
    status=$(curl --http1.1 --insecure --silent --show-error \
        --path-as-is \
        --resolve "pcep.micutu.com:$port:127.0.0.1" \
        --output /dev/null --write-out '%{http_code}' "$base_url$isolated_path")
    [[ "$status" == 404 ]]
done

for admin_path in \
    /admin /admin/login/ /%61dmin/login/ /admin%2flogin/ \
    /x/../admin/login/ //admin/login/
do
    admin_label=${admin_path//\//_}
    status=$(curl --http1.1 --insecure --silent --show-error \
        --path-as-is \
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
    assert_absent "admin route $admin_path Set-Cookie header" \
        -Eqi '^Set-Cookie:' "$stage/$admin_label.headers.clean"
    assert_absent "admin route $admin_path disclosure" \
        -Eqi 'Django administration|admin login' "$stage/$admin_label.body"
done

for retired_path in \
    /static /static/ /static/admin/css/base.css \
    /%73tatic/admin/css/base.css /static%2fadmin/css/base.css \
    /x/../static/admin/css/base.css //static/admin/css/base.css \
    /media /media/ /media/probe.txt \
    /%6dedia/probe.txt /media%2fprobe.txt /x/../media/probe.txt //media/probe.txt
do
    retired_label=${retired_path//\//_}
    status=$(curl --http1.1 --insecure --silent --show-error \
        --path-as-is \
        --resolve "pcep.micutu.com:$port:127.0.0.1" \
        --dump-header "$stage/$retired_label.headers" \
        --output "$stage/$retired_label.body" \
        --write-out '%{http_code}' "$base_url$retired_path")
    [[ "$status" == 404 ]]
    tr -d '\r' < "$stage/$retired_label.headers" \
        > "$stage/$retired_label.headers.clean"
    grep -Fqi 'Cache-Control: no-store' "$stage/$retired_label.headers.clean"
    grep -Fqi "Content-Security-Policy: default-src 'none'; frame-ancestors 'none'" \
        "$stage/$retired_label.headers.clean"
    grep -Fqi 'X-Content-Type-Options: nosniff' \
        "$stage/$retired_label.headers.clean"
    grep -Fqi 'X-Frame-Options: DENY' "$stage/$retired_label.headers.clean"
    grep -Eqi '^X-Request-ID: [0-9a-f]{32}$' \
        "$stage/$retired_label.headers.clean"
    assert_absent "retired route $retired_path Set-Cookie header" \
        -Eqi '^Set-Cookie:' "$stage/$retired_label.headers.clean"
    assert_absent "retired route $retired_path file disclosure" \
        -Fqi 'must never be published' "$stage/$retired_label.body"
done

status=$(curl --http1.1 --insecure --silent --show-error \
    --resolve "pcep.micutu.com:$port:127.0.0.1" \
    --output /dev/null --write-out '%{http_code}' \
    "$base_url/api/error-probe/?audit-api-error-query=must-not-be-logged")
[[ "$status" == 502 ]]

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
for _ in $(seq 1 120); do
    status=$(curl --http1.1 --insecure --silent --show-error \
        --resolve "pcep.micutu.com:$port:127.0.0.1" \
        --dump-header "$stage/429.headers" --output "$stage/429.body" \
        --write-out '%{http_code}' \
        "$base_url/api/stats/?audit-rate-limit-query=must-not-be-logged" \
        2>/dev/null || true)
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
docker exec "$container" cat /var/log/nginx/pcep_error.log \
    > "$stage/pcep-error.log"
assert_absent 'rate-limit error-log query string' \
    -Fq 'audit-rate-limit-query' "$stage/pcep-error.log"
assert_absent 'API upstream error-log query string' \
    -Fq 'audit-api-error-query' "$stage/pcep-error.log"

printf '%s\n' 'Nginx syntax, disclosure metadata, isolated runner, disabled admin/static/media and generated API error contracts: OK'
