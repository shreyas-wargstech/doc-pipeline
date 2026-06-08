/** Pure routing decision. `authed` = the dash_session cookie is present.
 * Returns the path to redirect to, or null to allow the request. */
export function redirectTarget(pathname: string, authed: boolean): string | null {
  const onLogin = pathname === "/login";
  if (!authed && !onLogin) return "/login";
  if (authed && onLogin) return "/";
  return null;
}
