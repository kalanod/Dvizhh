# HTTPS для dvizzh.space

В каталоге `certs` в корне проекта должны находиться:

- `certificate.crt` — сертификат домена;
- `certificate_ca.crt` — промежуточные сертификаты;
- `certificate.key` — соответствующий приватный ключ без пароля.

CSR для работы Nginx не нужен. Каталог исключён из Git и монтируется только для чтения. При старте контейнер собирает полную цепочку сертификатов вне этого каталога.

На сервере `/srv/projects/dvizh` файлы должны лежать в `/srv/projects/dvizh/certs`. Если они находятся в `/certs`, скопируйте их в каталог проекта отдельно от Git.

DNS для `dvizzh.space` и `www.dvizzh.space` должен указывать на сервер. Откройте TCP 443. Для стандартного HTTP и редиректа откройте TCP 80 и задайте в `.env`:

```dotenv
NGINX_PORT=8020
NGINX_HTTPS_PORT=8021
```

```bash
docker compose build nginx web-app
docker compose run --rm --no-deps nginx nginx -t
docker compose up -d --no-deps nginx web-app
curl -I https://dvizzh.space
curl -I http://dvizzh.space
```

Проверка `nginx -t` требует доступного имени `web-app` в сети Compose. Если проект ещё не запущен, после сборки выполните `docker compose up -d`, затем `docker compose exec nginx nginx -t`.

HTTP `/health` остаётся доступным без редиректа для проверки контейнера. Остальные HTTP-запросы перенаправляются на стандартный HTTPS-порт 443.

После обновления сертификатов выполните `docker compose restart nginx`: цепочка создаётся заново при старте. Автоматическое продление не настроено. Текущий сертификат истекает 28 мая 2027 года.

Router NAT: public TCP 443 -> server TCP 8021; public TCP 80 -> server TCP 8020. Public URL: https://dvizzh.space (no port). HTTP redirects to public port 443.
