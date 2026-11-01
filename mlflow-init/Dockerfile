FROM ghcr.io/coollabsio/minio@sha256:69b55a1c1c5dc285ce04db96689f5b2102317fc77a50680a1874ca6efd1c87f9 AS minio

FROM postgres:17-alpine@sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24

COPY --from=minio /usr/bin/mc /usr/local/bin/mc
COPY init.sh policy.json /opt/dvizh/

ENTRYPOINT ["/bin/sh", "/opt/dvizh/init.sh"]
