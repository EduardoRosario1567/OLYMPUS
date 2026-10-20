FROM mcr.microsoft.com/playwright:v1.63.0-noble
ENV NODE_ENV=development PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY integrations/browser_verifier/server.cjs ./server.cjs
USER pwuser
ENV NODE_ENV=production PORT=8080
CMD ["node", "server.cjs"]
