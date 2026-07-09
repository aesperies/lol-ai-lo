import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

/**
 * Role-based route protection:
 *   /dashboard, /new-request, /documents, /tabular-reviews → client
 *   /review, /counsel                    → counsel
 *   /admin                               → admin
 * Unauthenticated → redirect to /login.
 *
 * Dev stub mode (NEXT_PUBLIC_SUPABASE_URL unset): the simulated role is read
 * from the `lolailo_dev_role` cookie set by the login screen / role switcher.
 */

type Role = "client" | "counsel" | "admin";

const DEV_ROLE_COOKIE = "lolailo_dev_role";

const ROUTE_ROLES: Array<{ prefix: string; role: Role }> = [
  { prefix: "/dashboard", role: "client" },
  { prefix: "/new-request", role: "client" },
  { prefix: "/documents", role: "client" },
  { prefix: "/chat", role: "client" },
  { prefix: "/funds", role: "client" },
  { prefix: "/tabular-reviews", role: "client" },
  { prefix: "/account", role: "client" },
  { prefix: "/review", role: "counsel" },
  { prefix: "/counsel", role: "counsel" },
  { prefix: "/admin", role: "admin" },
];

const ROLE_HOME: Record<Role, string> = {
  client: "/dashboard",
  counsel: "/counsel",
  admin: "/admin/gestoras",
};

function isRole(value: string | undefined): value is Role {
  return value === "client" || value === "counsel" || value === "admin";
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const match = ROUTE_ROLES.find(
    (r) => pathname === r.prefix || pathname.startsWith(`${r.prefix}/`),
  );
  if (!match) return NextResponse.next();

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  let response = NextResponse.next({ request });
  let role: Role | undefined;

  if (!supabaseUrl || !supabaseAnonKey) {
    // Dev stub mode — simulated session via cookie.
    const cookieRole = request.cookies.get(DEV_ROLE_COOKIE)?.value;
    if (isRole(cookieRole)) role = cookieRole;
  } else {
    const supabase = createServerClient(supabaseUrl, supabaseAnonKey, {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(
          cookiesToSet: { name: string; value: string; options?: object }[],
        ) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value),
          );
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options),
          );
        },
      },
    });
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (user) {
      // TODO: read the role from a custom JWT claim (or the public.users
      // table via the backend) once auth wiring is final.
      const claimed =
        (user.app_metadata?.role as string | undefined) ??
        (user.user_metadata?.role as string | undefined) ??
        "client";
      if (isRole(claimed)) role = claimed;
    }
  }

  if (!role) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = "/login";
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (role !== match.role) {
    const homeUrl = request.nextUrl.clone();
    homeUrl.pathname = ROLE_HOME[role];
    homeUrl.search = "";
    return NextResponse.redirect(homeUrl);
  }

  return response;
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/dashboard",
    "/new-request/:path*",
    "/new-request",
    "/documents/:path*",
    "/documents",
    "/chat/:path*",
    "/chat",
    "/tabular-reviews/:path*",
    "/tabular-reviews",
    "/account/:path*",
    "/account",
    "/review/:path*",
    "/review",
    "/counsel/:path*",
    "/counsel",
    "/admin/:path*",
    "/admin",
  ],
};
