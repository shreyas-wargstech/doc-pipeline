// TEMPORARY dev-only demo accounts for the login quick-login buttons.
// Keep usernames + password in sync with scripts/seed_demo_users.py.
// Remove (file + its use in app/login/page.tsx) before production.

export const DEMO_PASSWORD = "demo1234";

export const DEMO_USERS = [
  { name: "Aarav Sharma", username: "aarav", role: "Administrator" },
  { name: "Priya Patel", username: "priya", role: "Reviewer" },
  { name: "Rohan Mehta", username: "rohan", role: "Operator" },
  { name: "Sneha Iyer", username: "sneha", role: "Viewer" },
] as const;

// Hidden in production builds; shown in dev/test.
export const SHOW_DEMO_LOGINS = process.env.NODE_ENV !== "production";
