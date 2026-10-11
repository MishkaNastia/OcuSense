# The OcuSense website for the VIScon VM: built once, served on port 8080.
# Build from the repository root (see ../docker-compose.yml): the face model lives in ../models.
FROM node:24-slim AS build
WORKDIR /app
COPY website/package.json website/package-lock.json website/
RUN cd website && npm ci
COPY models models
COPY website website
# Public values only (the URL and the publishable key ship to every browser anyway).
ARG NEXT_PUBLIC_SUPABASE_URL=""
ARG NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=""
ARG NEXT_PUBLIC_SITE_URL=""
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=$NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY \
    NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL \
    NEXT_TELEMETRY_DISABLED=1
RUN cd website && npm run build

FROM node:24-slim
WORKDIR /app/website
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app/website /app/website
EXPOSE 8080
CMD ["npx", "next", "start", "-p", "8080", "-H", "0.0.0.0"]
