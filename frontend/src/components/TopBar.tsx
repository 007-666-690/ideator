import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import type { ReactNode } from "react";

export function Logo() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="#1E2A5A" />
      <path d="M9 22 L16 9 L23 22" fill="none" stroke="#F6F7F9" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="3 2.6" />
      <path d="M11.6 17.4 H20.4" stroke="#FFE45C" strokeWidth="2.4" strokeLinecap="round" />
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
        Ideator
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
