# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# Непривилегированный nginx: отдаёт сборку и проксирует /api в backend.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime

ENV MEDIA_MAX_MIB=10
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8002
