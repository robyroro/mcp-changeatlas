FROM python:3.13-slim

RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && git init -q \
    && git add pyproject.toml README.md LICENSE src \
    && git -c user.name='Container fixture' \
           -c user.email='fixture@localhost.invalid' \
           commit -qm 'Container snapshot' \
    && useradd --system --uid 10001 --home-dir /app changeatlas \
    && chown -R changeatlas:changeatlas /app

USER changeatlas
ENV CHANGEATLAS_ROOT=/app
CMD ["mcp-changeatlas", "serve"]
