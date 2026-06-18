# Build context = repo kökü (compose: context: ../..)
FROM node:20.18-alpine

WORKDIR /app
# pnpm'i npm ile kuruyoruz; corepack'in imza doğrulama bug'ını ('Cannot find
# matching keyid') tamamen atlar.
RUN npm install -g pnpm@9.15.9

COPY apps/web/package.json ./
RUN pnpm install

COPY apps/web/ ./

EXPOSE 3000
CMD ["pnpm", "dev"]
