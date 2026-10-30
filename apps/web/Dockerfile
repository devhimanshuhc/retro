# Retro web app (Next.js standalone build).
FROM node:25-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
# npm install, not npm ci: a lock file made on macOS leaves out Linux-only optional packages (npm bug), which ci rejects
RUN npm install --no-audit --no-fund
COPY . .
# The browser calls the API at this URL, so it is fixed at build time (change it and rebuild for another port)
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_NANGO_HOST=http://localhost:3003
ARG NEXT_PUBLIC_NANGO_CONNECT_URL=http://localhost:3009
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_PUBLIC_NANGO_HOST=$NEXT_PUBLIC_NANGO_HOST \
    NEXT_PUBLIC_NANGO_CONNECT_URL=$NEXT_PUBLIC_NANGO_CONNECT_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:25-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
