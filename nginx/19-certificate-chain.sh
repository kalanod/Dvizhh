#!/bin/sh
set -eu

cp /etc/nginx/http-proxy.conf /etc/nginx/http-route.conf
rm -f /etc/nginx/templates/https.conf.template /etc/nginx/conf.d/https.conf
for file in certificate.crt certificate_ca.crt certificate.key; do
    if [ ! -s "/etc/nginx/certs/$file" ]; then
        echo "TLS disabled: missing or empty $file; HTTP remains available"
        exit 0
    fi
done

cp /etc/nginx/nginx.tls.conf.template /etc/nginx/templates/https.conf.template
mkdir -p /etc/nginx/ssl
cat /etc/nginx/certs/certificate.crt > /etc/nginx/ssl/fullchain.pem
printf '\n' >> /etc/nginx/ssl/fullchain.pem
cat /etc/nginx/certs/certificate_ca.crt >> /etc/nginx/ssl/fullchain.pem
printf '%s\n' 'return 308 https://dvizzh.space$request_uri;' > /etc/nginx/http-route.conf
