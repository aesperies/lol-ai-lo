# Lol-AI-lo frontend image (Next.js 14, App Router).
# Multi-stage build: install + build in one stage, run with a slimmer layer.
FROM node:20-slim AS deps
WORKDIR /app
# Install dependencies based on the lockfile for reproducible builds.
COPY package.json package-lock.json* ./
# Use npm ci when a lockfile is present; fall back to npm install otherwise.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

FROM node:20-slim AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* vars are inlined at build time. docker-compose passes
# NEXT_PUBLIC_API_URL as a build arg so the bundle points at the backend.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
# Copy the built app and runtime deps. (No public/ dir today; next.config.mjs
# is copied for `next start`. Add a public/ COPY here if you introduce one.)
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.mjs ./next.config.mjs

EXPOSE 3000

# `next start` serves the production build on port 3000.
CMD ["npm", "run", "start"]
