# HTTP and automatic HTTPS

Start with the same command in either mode:

```bash
docker compose up -d --build
```

HTTP always works on NGINX_PORT (default 8080).
HTTPS additionally works on NGINX_HTTPS_PORT (default 8021) when all three nonempty files exist in the project-root certs directory:

- certificate.crt: domain certificate
- certificate_ca.crt: intermediate certificate chain
- certificate.key: matching private key without a password

Without the complete set, Nginx starts in HTTP-only mode and logs why HTTPS is disabled.
Port 8021 is published by Docker, but does not serve HTTPS in that mode.
Invalid certificates or a mismatched key fail Nginx startup rather than silently disabling TLS.

The directory is ignored by Git and mounted read-only. A missing directory is created by Compose.
CSR is not needed. The container assembles the certificate chain at startup.

For this server, use /srv/projects/dvizh/certs and set .env:

```dotenv
NGINX_PORT=8020
NGINX_HTTPS_PORT=8021
```

Router forwarding: public TCP 443 -> server TCP 8021; public TCP 80 -> server TCP 8020.
Nginx uses ports 80/443 inside its container; Docker maps these to server ports.
The application does not need to know the router's external ports.
There is no automatic HTTP-to-HTTPS redirect.

DNS for dvizzh.space and www.dvizzh.space must point to the public server address.
The public URL with this router configuration is https://dvizzh.space without a port.

```bash
docker compose exec nginx nginx -t
curl -I https://dvizzh.space
```

After adding, removing or replacing certificate files, run docker compose restart nginx.
Automatic renewal is not configured. The current certificate expires on May 28, 2027.
