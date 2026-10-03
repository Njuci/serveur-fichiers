FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/var/lib/filehub/data \
    STORAGE_DIR=/var/lib/filehub/storage

WORKDIR /app

RUN groupadd --system filehub \
    && useradd --system --gid filehub --home-dir /app --shell /usr/sbin/nologin filehub

COPY requirements.txt .
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY app ./app
COPY static ./static
COPY scripts ./scripts
COPY data/users.json ./data/users.json
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN mkdir -p /var/lib/filehub/data /var/lib/filehub/storage \
    && chmod +x /usr/local/bin/docker-entrypoint.sh \
    && chown -R filehub:filehub /app /var/lib/filehub

USER filehub

EXPOSE 5000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]
