FROM postgres:17-alpine

COPY postgres/init-recsys-reader.sh /opt/dvizh/init-recsys-reader.sh
COPY database-init/init.sh /opt/dvizh/init.sh

ENTRYPOINT ["/bin/sh", "/opt/dvizh/init.sh"]
