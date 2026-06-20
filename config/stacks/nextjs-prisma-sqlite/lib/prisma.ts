import { PrismaClient } from "@prisma/client";

// PrismaClient singleton — Next.js dev hot-reload'da çoklu instance'ı önler.
const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };

export const prisma =
  globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
