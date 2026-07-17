# Next.js frontend image for real-estate-viewer.
# Multi-stage build producing a slim standalone server (see next.config.mjs
# `output: "standalone"`). Built & pushed to GHCR by the app repo's workflow;
# the home-server stack only pulls it.

# --- deps: install node_modules from the lockfile ---
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# --- build: compile the Next.js app ---
FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# --- runner: minimal runtime with just the standalone server ---
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Standalone output bundles a minimal node_modules + server.js. It does NOT
# include public/ or .next/static; Next.js requires copying those manually.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

# Run as the built-in unprivileged node user.
USER node

EXPOSE 3000
CMD ["node", "server.js"]
