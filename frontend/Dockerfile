FROM node:22-alpine AS build

WORKDIR /app

RUN --mount=type=cache,id=frontend-corepack-cache,target=/root/.cache/node/corepack \
    corepack enable

COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,id=frontend-pnpm-store,target=/pnpm/store \
    pnpm config set store-dir /pnpm/store && \
    pnpm install --frozen-lockfile

ARG VITE_API_BASE_URL=/api/v1
ARG VITE_API_MODE=real
ARG VITE_CSRF_COOKIE_NAME=datatrace_csrf
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_API_MODE=$VITE_API_MODE \
    VITE_CSRF_COOKIE_NAME=$VITE_CSRF_COOKIE_NAME

COPY . .
RUN pnpm build

FROM nginx:1.31.4-alpine-slim AS runtime

COPY nginx-main.conf /etc/nginx/nginx.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

RUN mkdir -p /tmp/nginx/client_temp /tmp/nginx/proxy_temp \
    /tmp/nginx/fastcgi_temp /tmp/nginx/uwsgi_temp /tmp/nginx/scgi_temp \
    && chown -R nginx:nginx /tmp/nginx

USER nginx

EXPOSE 8080

ENTRYPOINT []
CMD ["nginx", "-g", "daemon off;"]
