FROM node:24.18.0-bookworm-slim

ENV NODE_ENV=production
WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json

RUN corepack enable \
    && corepack install --global pnpm@11.17.0 \
    && corepack pnpm install \
        --frozen-lockfile \
        --filter @ai-cto-cockpit/web...

COPY apps/web apps/web

RUN corepack pnpm --dir apps/web build

WORKDIR /app/apps/web
USER node
EXPOSE 3000

CMD ["./node_modules/.bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
