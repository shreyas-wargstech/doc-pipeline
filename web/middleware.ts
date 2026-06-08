import { NextResponse, type NextRequest } from "next/server";
import { redirectTarget } from "@/lib/auth-guard";

const COOKIE = "dash_session";

export function middleware(req: NextRequest) {
  const authed = req.cookies.has(COOKIE);
  const target = redirectTarget(req.nextUrl.pathname, authed);
  if (target) return NextResponse.redirect(new URL(target, req.url));
  return NextResponse.next();
}

export const config = { matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"] };
