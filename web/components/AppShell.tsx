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
import MenuIcon from "@mui/icons-material/Menu";
import LightModeIcon from "@mui/icons-material/LightMode";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LogoutIcon from "@mui/icons-material/Logout";
import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import DescriptionIcon from "@mui/icons-material/Description";
import FactCheckIcon from "@mui/icons-material/FactCheck";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import TravelExploreIcon from "@mui/icons-material/TravelExplore";
import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import AdminPanelSettingsIcon from "@mui/icons-material/AdminPanelSettings";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { useThemeMode } from "@/app/theme-mode";
import { useActionBarContent } from "@/app/action-bar";
import { useLogout } from "@/hooks/useAuth";

const DRAWER_WIDTH = 240;

const NAV_ITEMS = [
  { href: "/", label: "Documents", icon: DescriptionIcon },
  { href: "/eval", label: "Evaluation", icon: FactCheckIcon },
  { href: "/pipelines", label: "Pipelines", icon: AccountTreeIcon },
  { href: "/retrieval", label: "Retrieval", icon: TravelExploreIcon },
  { href: "/observability", label: "Observability", icon: MonitorHeartIcon },
  { href: "/admin", label: "Admin", icon: AdminPanelSettingsIcon },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { mode, toggle } = useThemeMode();
  const logout = useLogout();
  const actionBarContent = useActionBarContent();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenuAnchor, setUserMenuAnchor] = useState<HTMLElement | null>(null);

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  const navList = (
    <List>
      {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
        <ListItemButton
          key={href}
          component={Link}
          href={href}
          selected={isActive(href)}
          aria-current={isActive(href) ? "page" : undefined}
        >
          <ListItemIcon>
            <Icon />
          </ListItemIcon>
          <ListItemText primary={label} />
        </ListItemButton>
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
          <Typography variant="subtitle1" sx={{ fontFamily: "var(--font-mono)", fontWeight: 700, mr: 2 }}>
            doc-pipeline
          </Typography>
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <Breadcrumbs />
          </Box>
          <IconButton color="inherit" onClick={toggle} aria-label="Toggle theme">
            {mode === "dark" ? <LightModeIcon /> : <DarkModeIcon />}
          </IconButton>
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
          width: DRAWER_WIDTH,
          flexShrink: 0,
          "& .MuiDrawer-paper": { width: DRAWER_WIDTH, boxSizing: "border-box" },
        }}
      >
        <Toolbar />
        {navList}
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, p: 2, width: { sm: `calc(100% - ${DRAWER_WIDTH}px)` } }}>
        <Toolbar />
        {actionBarContent && <Toolbar variant="dense" />}
        {children}
      </Box>
    </Box>
  );
}
