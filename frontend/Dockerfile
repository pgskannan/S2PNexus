# S2PNexus Frontend Dockerfile

FROM node:20-alpine

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci

# Copy application code
COPY . .

# NEXT_PUBLIC_* vars are inlined into the client bundle at build time, so the
# backend URL has to be known when this image is built (pass with
# --build-arg NEXT_PUBLIC_API_URL=https://<backend>/api/v1).
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

# Build application
RUN npm run build

# Cloud Run injects $PORT (usually 8080); default to 3000 for local docker-compose
ENV PORT=3000
EXPOSE 3000

# Run application - npx so it resolves the locally installed `next` binary
CMD ["sh", "-c", "npx next start -p ${PORT}"]