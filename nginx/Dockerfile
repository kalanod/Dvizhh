FROM nginx:1.30.6-alpine-otel

RUN sed -i '1i load_module modules/ngx_otel_module.so;' /etc/nginx/nginx.conf

ENV MEDIA_MAX_MIB=10 NGINX_OTEL_TRACE=off
COPY nginx.tls.conf /etc/nginx/nginx.tls.conf.template
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY gateway.conf /etc/nginx/gateway.conf
COPY --chmod=755 19-certificate-chain.sh /docker-entrypoint.d/19-certificate-chain.sh

EXPOSE 80
EXPOSE 443
