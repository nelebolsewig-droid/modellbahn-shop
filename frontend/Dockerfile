# Next.js frontend (shop and admin) as a standalone Node server on port 3000.

ARG NODE_IMAGE=node:22-alpine

FROM ${NODE_IMAGE} AS deps

ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

COPY package.json package-lock.json ./

# Optional build secret "build_ca": an extra CA certificate for TLS-inspecting proxies (see
# README). Only the build stages trust it; the runtime stage starts from a clean image.
# It is added in the same step as the first download because BuildKit caches steps without
# regard to secrets: a separate step built once without the secret would be reused unchanged
# after the secret is added.
RUN --mount=type=secret,id=build_ca,required=false \
    --mount=type=cache,target=/root/.npm \
    if [ -s /run/secrets/build_ca ]; then \
        cat /run/secrets/build_ca >> /etc/ssl/certs/ca-certificates.crt; \
    fi \
    && npm ci --no-audit --no-fund


# Continues from deps: node_modules and the trusted CA are already in place, and
# `next build` may still download (next/font fetches Google Fonts at build time).
# .dockerignore keeps the host's node_modules out of the COPY.
FROM deps AS builder

COPY . .

# Inlined into the bundle by `next build`; when not passed, the frontend's default applies.
ARG NEXT_PUBLIC_SHOP_NAME

# The runtime stage copies public/, which a project does not have to contain.
RUN mkdir -p public \
    && npm run build


FROM ${NODE_IMAGE} AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

WORKDIR /app

COPY --from=builder /app/public ./public
# Owned by the unprivileged "node" user from the base image: Next.js writes its
# ISR and image caches below .next at runtime.
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static

USER node

EXPOSE 3000

# Any answer below 500 means the server is up and renders.
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/', { redirect: 'manual' }).then((r) => process.exit(r.status < 500 ? 0 : 1), () => process.exit(1))"]

CMD ["node", "server.js"]
