"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";
import MenuIcon from "@mui/icons-material/Menu";
import LogoutIcon from "@mui/icons-material/Logout";
import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import DescriptionIcon from "@mui/icons-material/Description";
import FactCheckIcon from "@mui/icons-material/FactCheck";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import TravelExploreIcon from "@mui/icons-material/TravelExplore";
import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import AdminPanelSettingsIcon from "@mui/icons-material/AdminPanelSettings";
import BookmarkBorderIcon from "@mui/icons-material/BookmarkBorder";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { useActionBarContent } from "@/app/action-bar";
import { useLogout, useRole } from "@/hooks/useAuth";
import { useCollapsible } from "@/hooks/useCollapsible";

const DRAWER_WIDTH = 240;
const COLLAPSED_WIDTH = 64;

const NAV_ITEMS = [
  { href: "/", label: "Documents", icon: DescriptionIcon },
  { href: "/bookmarks", label: "Bookmarks", icon: BookmarkBorderIcon },
  { href: "/eval", label: "Evaluation", icon: FactCheckIcon },
  { href: "/pipelines", label: "Pipelines", icon: AccountTreeIcon },
  { href: "/retrieval", label: "Retrieval", icon: TravelExploreIcon },
  { href: "/observability", label: "Observability", icon: MonitorHeartIcon },
  { href: "/admin", label: "Admin", icon: AdminPanelSettingsIcon },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const logout = useLogout();
  const actionBarContent = useActionBarContent();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenuAnchor, setUserMenuAnchor] = useState<HTMLElement | null>(null);
  const { collapsed, toggle } = useCollapsible("app-sidebar", false);
  const sidebarWidth = collapsed ? COLLAPSED_WIDTH : DRAWER_WIDTH;
  const role = useRole();
  const visibleNavItems = NAV_ITEMS.filter(
    ({ href }) => href !== "/admin" || role === "administrator",
  );

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  const navList = (
    <List>
      {visibleNavItems.map(({ href, label, icon: Icon }) => (
        <Tooltip key={href} title={collapsed ? label : ""} placement="right">
          <ListItemButton
            component={Link}
            href={href}
            selected={isActive(href)}
            aria-current={isActive(href) ? "page" : undefined}
            sx={{ justifyContent: collapsed ? "center" : "flex-start", px: collapsed ? 1.5 : 2 }}
          >
            <ListItemIcon sx={{ minWidth: collapsed ? 0 : undefined }}>
              <Icon />
            </ListItemIcon>
            {!collapsed && <ListItemText primary={label} />}
          </ListItemButton>
        </Tooltip>
      ))}
    </List>
  );

  return (
    <Box sx={{ display: "flex" }}>
      <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }} color="default" elevation={1}>
        <Toolbar sx={{ gap: 1 }}>
          <IconButton
            color="inherit"
            edge="start"
            sx={{ display: { sm: "none" } }}
            onClick={() => setMobileOpen((open) => !open)}
            aria-label="Toggle navigation"
          >
            <MenuIcon />
          </IconButton>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mr: 2 }}>
            <Box
              aria-hidden
              sx={{
                width: 26,
                height: 26,
                borderRadius: "8px",
                background: "linear-gradient(135deg, rgb(94 234 212), rgb(13 148 136))",
                boxShadow: "0 3px 10px rgba(13,148,136,.45)",
              }}
            />
            <Typography
              component="span"
              sx={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.05rem", letterSpacing: "0.2px" }}
            >
              Docintel
            </Typography>
          </Box>
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <Breadcrumbs />
          </Box>
          <IconButton color="inherit" onClick={(e) => setUserMenuAnchor(e.currentTarget)} aria-label="Account menu">
            <AccountCircleIcon />
          </IconButton>
          <Menu anchorEl={userMenuAnchor} open={Boolean(userMenuAnchor)} onClose={() => setUserMenuAnchor(null)}>
            <MenuItem
              onClick={() => {
                setUserMenuAnchor(null);
                logout.mutate();
              }}
            >
              <ListItemIcon>
                <LogoutIcon fontSize="small" />
              </ListItemIcon>
              Sign out
            </MenuItem>
          </Menu>
        </Toolbar>
        {actionBarContent && (
          <Toolbar variant="dense" sx={{ borderTop: 1, borderColor: "divider", gap: 1 }}>
            {actionBarContent}
          </Toolbar>
        )}
      </AppBar>

      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        ModalProps={{ keepMounted: true }}
        sx={{ display: { xs: "block", sm: "none" }, "& .MuiDrawer-paper": { width: DRAWER_WIDTH } }}
      >
        {navList}
      </Drawer>
      <Drawer
        variant="permanent"
        sx={{
          display: { xs: "none", sm: "block" },
          width: sidebarWidth,
          flexShrink: 0,
          whiteSpace: "nowrap",
          "& .MuiDrawer-paper": {
            width: sidebarWidth,
            boxSizing: "border-box",
            display: "flex",
            flexDirection: "column",
            overflowX: "hidden",
            transition: (theme) =>
              theme.transitions.create("width", { duration: theme.transitions.duration.shorter }),
          },
        }}
      >
        <Toolbar />
        <Box sx={{ display: "flex", justifyContent: collapsed ? "center" : "flex-end", px: 1, py: 0.5 }}>
          <IconButton
            onClick={toggle}
            size="small"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <ChevronRightIcon /> : <ChevronLeftIcon />}
          </IconButton>
        </Box>
        {navList}
        {!collapsed && (
          <Box sx={{ mt: "auto", p: 2, fontSize: 11, color: "text.secondary", fontFamily: "var(--font-mono)" }}>
            92,431 registry rows
          </Box>
        )}
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, p: 2, width: { sm: `calc(100% - ${sidebarWidth}px)` } }}>
        <Toolbar />
        {actionBarContent && <Toolbar variant="dense" />}
        {children}
      </Box>
    </Box>
  );
}
