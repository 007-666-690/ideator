import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import type { ReactNode } from "react";
import { APP_NAME } from "../util";

export function Logo() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#1E2A5A" />
      <path d="M9.5 7.5 H19 L23.5 12 V24.5 H9.5 Z" fill="none" stroke="#F6F7F9" strokeWidth="2" strokeLinejoin="round" />
      <path d="M19 7.5 V12 H23.5" fill="none" stroke="#F6F7F9" strokeWidth="2" strokeLinejoin="round" />
      <path d="M12.5 15.5 H20.5" stroke="#F6F7F9" strokeWidth="2" strokeLinecap="round" strokeDasharray="2.2 2.2" />
      <path d="M12.5 20 H18" stroke="#FFE45C" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

export default function TopBar({ children }: { children?: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <header className="topbar">
      <Link to="/" className="wordmark">
        <Logo />
        {APP_NAME}
        <span className="by">Ideator</span>
      </Link>
      {children}
      <span className="spacer" />
      {user && (
        <span className="row">
          <Link to="/sesion" className="small muted session-link" title={`${user.email}: ver mi sesión`}>
            {user.name}
          </Link>
          <button
            className="btn ghost small"
            onClick={async () => {
              await logout();
              navigate("/login");
            }}
          >
            Cerrar sesión
          </button>
        </span>
      )}
    </header>
  );
}
