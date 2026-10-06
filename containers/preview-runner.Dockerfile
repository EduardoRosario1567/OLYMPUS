# Provisioning only. Olympus missions never pull or install dependencies.
ARG NODE_BASE
FROM ${NODE_BASE}
LABEL org.olympus.preview-runner="v1"
WORKDIR /opt/olympus-preview
COPY preview-runtime.package.json ./package.json
COPY preview-runtime.package-lock.json ./package-lock.json
RUN npm ci --ignore-scripts --no-audit --no-fund \
    && npm ls --depth=0 \
    && node -e "const fs=require('fs'),crypto=require('crypto');console.log('PREVIEW_LOCK_SHA256='+crypto.createHash('sha256').update(fs.readFileSync('package-lock.json')).digest('hex'))"
COPY preview-launch.mjs ./preview-launch.mjs
COPY preview-launch.mjs ./launch.mjs
COPY preview-fetch.mjs ./preview-fetch.mjs
COPY preview-fetch.mjs ./fetch.mjs
USER 65534:65534
WORKDIR /work
ENV HOME=/tmp TMPDIR=/tmp NEXT_TELEMETRY_DISABLED=1
ENTRYPOINT ["/usr/local/bin/node", "/opt/olympus-preview/launch.mjs"]
