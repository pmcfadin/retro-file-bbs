FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends gkermit lrzsz && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir telnetlib3

COPY indexer/ /app/indexer/
COPY server/ /app/server/
COPY entrypoint.sh /app/

WORKDIR /app
RUN chmod +x entrypoint.sh

EXPOSE 2323 8080

ENTRYPOINT ["/app/entrypoint.sh"]
