import { cookies } from "next/headers";

const COOKIE = "uid";

export async function setUserCookie(userId: string) {
  const jar = await cookies();
  jar.set(COOKIE, userId, {
    httpOnly: true,
    path: "/",
    sameSite: "lax",
    maxAge: 60 * 60 * 24 * 30,
  });
}

export async function getUserId(): Promise<string | null> {
  const jar = await cookies();
  return jar.get(COOKIE)?.value ?? null;
}

export async function clearUserCookie() {
  const jar = await cookies();
  jar.delete(COOKIE);
}
