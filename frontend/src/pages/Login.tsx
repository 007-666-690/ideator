import { useEffect, useState, type FormEvent } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { Logo } from "../components/TopBar";
import { APP_NAME } from "../util";

const SSO_ERRORS: Record<string, string> = {
  sso_failed: "El proveedor rechazó el inicio de sesión. Intenta de nuevo.",
  sso_unavailable: "El proveedor de identidad no respondió. Puedes entrar con tu correo y contraseña.",
  sso_email_in_use: "Ese correo ya tiene una cuenta con contraseña. Entra con tu correo y contraseña.",
  sso_missing_claims: "El proveedor no entregó tu correo. Usa otro método para entrar.",
};

export default function Login() {
  const { user, login, register } = useAuth();
  const [params] = useSearchParams();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>(SSO_ERRORS[params.get("error") ?? ""] ?? "");
  const [busy, setBusy] = useState(false);
  const [providers, setProviders] = useState<{ id: string; name: string; enabled: boolean }[]>([]);

  useEffect(() => {
    api.providers().then(setProviders).catch(() => setProviders([]));
  }, []);

  if (user) return <Navigate to="/" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "login") await login(email, password);
      else await register(name, email, password);
    } catch (err) {
      if (err instanceof ApiError && err.code === "validation_error") {
        setError(mode === "register" ? "Revisa los datos: el correo debe ser válido y la contraseña tener al menos 8 caracteres." : "Revisa el correo y la contraseña.");
      } else setError(err instanceof Error ? err.message : "No se pudo continuar.");
    } finally {
      setBusy(false);
    }
  };

  const enabled = providers.filter((p) => p.enabled);

  return (
    <main className="auth-wrap">
      <section className="auth-hero" aria-label={`Qué es ${APP_NAME}`}>
        <div className="wordmark light">
          <Logo />
          {APP_NAME}
          <span className="by">Ideator</span>
        </div>
        <p className="hero-title">De la idea al plano.</p>
        <p className="hero-lead">Cuenta tu idea. {APP_NAME} te hace las preguntas que faltan y la convierte en una especificación que otra IA puede construir sin adivinar.</p>
        <ol className="hero-path" aria-label="Etapas">
          {["Definición", "Datos", "API", "Pantallas", "Arquitectura", "Revisión", "Documentos"].map((s, i) => (
            <li key={s} className={i < 3 ? "done" : ""}>
              {s}
            </li>
          ))}
        </ol>
      </section>
      <div className="auth">
        <h1 style={{ fontSize: 26 }}>{mode === "login" ? "Inicia sesión" : "Crea tu cuenta"}</h1>
        <p className="lead">{mode === "login" ? "Entra para seguir con tus proyectos." : "Es gratis y toma un minuto."}</p>
        {error && <div className="banner error">{error}</div>}
        {enabled.length > 0 && (
          <>
            <div className="sso">
              {enabled.map((p) => (
                <a key={p.id} className="btn secondary" href={`/api/auth/sso/${p.id}/login`}>
                  Entrar con {p.name}
                </a>
              ))}
            </div>
            <div className="divider">o con tu correo</div>
          </>
        )}
        <form onSubmit={submit}>
          {mode === "register" && (
            <div className="field">
              <label htmlFor="name">Nombre</label>
              <input id="name" type="text" value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} autoComplete="name" />
            </div>
          )}
          <div className="field">
            <label htmlFor="email">Correo</label>
            <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
          </div>
          <div className="field">
            <label htmlFor="password">Contraseña</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={mode === "register" ? 8 : 1}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
            {mode === "register" && <small className="muted">Mínimo 8 caracteres.</small>}
          </div>
          <button className="btn" type="submit" disabled={busy} style={{ width: "100%", justifyContent: "center" }}>
            {mode === "login" ? "Entrar" : "Crear cuenta"}
          </button>
        </form>
        <p className="small muted" style={{ marginTop: 18, marginBottom: 0 }}>
          {mode === "login" ? "¿No tienes cuenta? " : "¿Ya tienes cuenta? "}
          <button
            className="btn ghost small"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError("");
            }}
          >
            {mode === "login" ? "Crear cuenta" : "Iniciar sesión"}
          </button>
        </p>
        {enabled.length === 0 && providers.length > 0 && (
          <p className="small muted" style={{ marginTop: 8 }}>
            El inicio de sesión con Microsoft o Google se habilita al configurar el SSO en el servidor.
          </p>
        )}
      </div>
    </main>
  );
}
