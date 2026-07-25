import { closeSync, mkdirSync, openSync } from "node:fs";
import { dirname } from "node:path";

const databaseUrl = process.env.DATABASE_URL;

if (!databaseUrl?.startsWith("file:/")) {
  throw new Error("DATABASE_URL must be an absolute SQLite file URL");
}

const databasePath = databaseUrl.slice("file:".length);
mkdirSync(dirname(databasePath), { recursive: true });
closeSync(openSync(databasePath, "a"));
