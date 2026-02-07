FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .
COPY linksync/ linksync/

RUN pip install --no-cache-dir .

ENTRYPOINT ["python", "-m", "linksync", "--config", "/config/config.toml"]
CMD ["--interval", "300"]
