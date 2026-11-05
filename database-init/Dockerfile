FROM postgres:17-alpine

COPY postgres/init-recsys-reader.sh /opt/dvizh/init-recsys-reader.sh
COPY pgvector/init.sql /opt/dvizh/vector.sql
COPY database-init/init.sh /opt/dvizh/init.sh

ENTRYPOINT ["/bin/sh", "/opt/dvizh/init.sh"]
