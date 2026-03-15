# Stage 1: Build React admin UI
FROM node:20-slim AS frontend
WORKDIR /build
COPY admin-ui/package.json admin-ui/package-lock.json ./
RUN npm ci
COPY admin-ui/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends gkermit lrzsz cpmtools && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir telnetlib3 fastapi uvicorn python-multipart

COPY indexer/ /app/indexer/
COPY server/ /app/server/
COPY entrypoint.sh /app/

# Copy built React app
COPY --from=frontend /build/dist /app/admin-ui/dist

WORKDIR /app
RUN chmod +x entrypoint.sh

EXPOSE 2323 8080

ENTRYPOINT ["/app/entrypoint.sh"]
