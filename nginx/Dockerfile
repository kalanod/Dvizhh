FROM nginx:1.27-alpine

ENV MEDIA_MAX_MIB=10
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --chmod=755 19-certificate-chain.sh /docker-entrypoint.d/19-certificate-chain.sh

EXPOSE 80
EXPOSE 443
