#!/bin/sh
set -eu

mkdir -p /etc/nginx/ssl
cat /etc/nginx/certs/certificate.crt > /etc/nginx/ssl/fullchain.pem
printf '\n' >> /etc/nginx/ssl/fullchain.pem
cat /etc/nginx/certs/certificate_ca.crt >> /etc/nginx/ssl/fullchain.pem
