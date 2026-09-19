#!/bin/bash
# Isolated syntax check with disposable certificates; never reloads host Nginx.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/certs" "$stage/snippets"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj '/CN=pcep.micutu.com' -keyout "$stage/certs/privkey.pem" -out "$stage/certs/fullchain.pem" 2>/dev/null
cp "$root"/nginx/snippets/pcep-*.conf "$stage/snippets/"
printf 'location ~ /\\. { deny all; }\n' > "$stage/snippets/block-dotfiles.conf"
# Shared variables/includes are provided by the actual production host.
sed -e '/include \/etc\/letsencrypt\/options-ssl-nginx.conf;/d' -e '/ssl_dhparam \/etc\/letsencrypt\/ssl-dhparams.pem;/d' "$root/nginx/pcep.micutu.com.conf" > "$stage/pcep.conf"
printf 'geo $from_cloudflare_origin { default 1; }\n' > "$stage/shared.conf"
docker run --rm --network none -v "$stage/pcep.conf:/etc/nginx/conf.d/default.conf:ro" -v "$stage/shared.conf:/etc/nginx/conf.d/shared.conf:ro" -v "$stage/snippets:/etc/nginx/snippets:ro" -v "$stage/certs:/etc/letsencrypt/live/pcep.micutu.com:ro" nginx:1.28-alpine nginx -t
