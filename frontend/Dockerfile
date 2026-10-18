# Root repository is the Docker build context, even though Dockerfile is in frontend/.
FROM node:24-alpine AS builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ARG NEXT_PUBLIC_API_BASE_URL=/api/olympus
ARG OLYMPUS_BACKEND_INTERNAL_URL=http://olympus-cloud-backend.railway.internal:8000
ENV NEXT_PUBLIC_API_BASE_URL=/api/olympus
ENV OLYMPUS_BACKEND_INTERNAL_URL=http://olympus-cloud-backend.railway.internal:8000
ENV OLYMPUS_FRONTEND_CLOUD_PROXY=1
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:24-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
RUN chown -R node:node /app
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD wget -q -O /dev/null http://127.0.0.1:3000/login || exit 1
CMD ["npm","run","start"]
