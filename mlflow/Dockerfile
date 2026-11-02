FROM ghcr.io/mlflow/mlflow:v3.17.2@sha256:2cc40b3208991940d824d04f339833a0b69507569012aa5ec545690608602fc0

RUN pip install --no-cache-dir --no-deps \
    Flask-WTF==1.3.0 \
    WTForms==3.3.1 \
    boto3==1.43.120 \
    botocore==1.43.120 \
    jmespath==1.1.0 \
    s3transfer==0.19.0 \
    psycopg2-binary==2.9.13 && \
    pip check && \
    groupadd --system app && \
    useradd --system --gid app --home-dir /app --create-home app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY --chown=app:app startup.py ./startup.py

USER app
EXPOSE 5000

CMD ["python", "startup.py"]
