import { useEffect, useState } from "react";
import { api, type SessionInfo } from "../api";
import TopBar from "../components/TopBar";

const dateTime = (seconds: number) =>
  new Date(seconds * 1000).toLocaleString("es-CL", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });

function remaining(exp: number): string {
  const s = Math.max(0, Math.round(exp - Date.now() / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return s === 0 ? "ya venció" : `vence en ${h ? `${h} h ` : ""}${m} min`;
}

/** Explica, campo por campo, el token de la sesión actual (lo que se ve al pegarlo en jwt.io). */
export default function SessionPage() {
  const [info, setInfo] = useState<SessionInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.session().then(setInfo).catch((e) => setError(e.message));
  }, []);

  const readable = (claim: string, value: unknown): string => {
    if (!info) return "";
    if ((claim === "iat" || claim === "exp") && typeof value === "number") {
      return `${dateTime(value)}${claim === "exp" ? ` (${remaining(value)})` : ""}`;
    }
    if (claim === "sub") return `Tú: ${info.user.name}`;
    if (claim === "jti") return "Esta sesión, en este navegador";
    if (claim === "type") return "Sesión de usuario";
    return "";
  };

  return (
    <>
      <TopBar>
        <span className="crumb">
          <strong>Mi sesión</strong>
        </span>
      </TopBar>
      <main className="page session-page">
        <h1>Mi sesión</h1>
        <p className="lead">
          Al iniciar sesión, el backend crea un token JWT firmado y lo guarda en la cookie <code>{info?.storage.cookie_name ?? "ideator_session"}</code>.
          El navegador la envía sola en cada llamada a <code>/api</code>, y con ella el backend sabe quién eres.
        </p>
        {error && <p className="muted">{error}</p>}
        {!info && !error && <p className="muted">Cargando…</p>}
        {info && (
          <>
            <section>
              <h2>El token tiene tres partes separadas por puntos</h2>
              <p className="jwt-shape mono" aria-label="encabezado punto contenido punto firma">
                <span className="jwt-h">encabezado</span>.<span className="jwt-p">contenido</span>.<span className="jwt-s">firma</span>
              </p>
              <dl className="jwt-legend">
                <div>
                  <dt className="jwt-h">Encabezado</dt>
                  <dd>
                    <code>alg: {info.header.alg}</code> y <code>typ: {info.header.typ}</code>: el algoritmo de la firma y que es un JWT.
                  </dd>
                </div>
                <div>
                  <dt className="jwt-p">Contenido</dt>
                  <dd>Los campos de la tabla de abajo. Solo está en base64: cualquiera que tenga el token lo puede leer, por eso no lleva la contraseña ni nada secreto.</dd>
                </div>
                <div>
                  <dt className="jwt-s">Firma</dt>
                  <dd>{info.signature} Si alguien cambia un campo, la firma deja de calzar y el backend responde 401.</dd>
                </div>
              </dl>
              <p className="note">No está cifrado, está firmado: se puede leer, pero no se puede modificar sin la clave.</p>
            </section>

            <section>
              <h2>Qué dice tu token</h2>
              <div className="table-scroll">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Campo</th>
                      <th>Qué es</th>
                      <th>Valor en tu sesión</th>
                    </tr>
                  </thead>
                  <tbody>
                    {info.fields.map((f) => (
                      <tr key={f.claim}>
                        <td>
                          <code>{f.claim}</code>
                        </td>
                        <td>
                          <strong>{f.label}.</strong> {f.meaning}
                        </td>
                        <td>
                          <code className="claim-value">{String(f.value)}</code>
                          {readable(f.claim, f.value) && <div className="small muted">{readable(f.claim, f.value)}</div>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h2>Dónde se guarda cada cosa</h2>
              <div className="table-scroll">
                <table className="data">
                  <tbody>
                    <tr>
                      <td>El token de sesión</td>
                      <td>
                        En tu navegador, en la cookie <code>{info.storage.cookie_name}</code>: HttpOnly (el código de la página no la puede leer), SameSite=Lax (otros
                        sitios no la pueden usar) y dura {Math.round(info.storage.max_age_seconds / 3600)} horas.
                      </td>
                    </tr>
                    <tr>
                      <td>La clave que firma el token</td>
                      <td>
                        <code>SECRET_KEY</code> en <code>backend/.env</code>. Solo la tiene el servidor; nunca llega al navegador.
                      </td>
                    </tr>
                    <tr>
                      <td>Tu usuario y contraseña</td>
                      <td>
                        Tabla <code>users</code>. La contraseña se guarda como hash argon2, nunca en texto.
                      </td>
                    </tr>
                    <tr>
                      <td>Las sesiones cerradas</td>
                      <td>
                        Tabla <code>revoked_tokens</code>: al cerrar sesión se guarda el <code>jti</code> y ese token deja de servir aunque alguien lo haya copiado.
                      </td>
                    </tr>
                    <tr>
                      <td>Proyectos, etapas y su historial</td>
                      <td>
                        Tablas <code>projects</code>, <code>project_members</code>, <code>stages</code>, <code>stage_revisions</code>, <code>questions</code> y{" "}
                        <code>activity_log</code>, en <code>backend/ideator.db</code> (SQLite) o en PostgreSQL con Docker.
                      </td>
                    </tr>
                    <tr>
                      <td>Los permisos</td>
                      <td>
                        No van en el token. En cada llamada el backend busca tu rol en <code>project_members</code>: sin sesión responde 401, sin permiso 403 y si el
                        proyecto no existe 404.
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h2>Qué vas a ver en Network</h2>
              <div className="table-scroll">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Llamada</th>
                      <th>Qué pasa</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>
                        <code>POST /api/auth/register</code> o <code>/login</code>
                      </td>
                      <td>
                        La respuesta trae la cabecera <code>Set-Cookie: {info.storage.cookie_name}=…; HttpOnly; SameSite=lax</code>: ahí nace la sesión. En Payload se ve la
                        contraseña porque es lo que envía tu navegador; en producción viaja por HTTPS, cifrada en el camino, y el servidor solo guarda su hash.
                      </td>
                    </tr>
                    <tr>
                      <td>Cualquier otra llamada a <code>/api</code></td>
                      <td>
                        Lleva la cabecera <code>Cookie: {info.storage.cookie_name}=…</code>. El backend revisa la firma, <code>iss</code>, <code>aud</code>, <code>exp</code> y que el{" "}
                        <code>jti</code> no esté revocado.
                      </td>
                    </tr>
                    <tr>
                      <td>
                        <code>GET /api/projects/…/sync</code> cada 4 segundos
                      </td>
                      <td>Revisa si otro integrante cambió algo, para mostrarlo sin recargar la página.</td>
                    </tr>
                    <tr>
                      <td>
                        <code>POST …/product/start</code>, <code>…/turn</code> o <code>…/generate</code>
                      </td>
                      <td>Demora unos segundos porque el backend le pregunta a GPT-5. El navegador nunca llama a Azure: no hay llamadas a openai.azure.com en Network.</td>
                    </tr>
                    <tr>
                      <td>
                        <code>POST /api/auth/logout</code>
                      </td>
                      <td>
                        Responde 204 con <code>Set-Cookie: {info.storage.cookie_name}=""; Max-Age=0</code>, que borra la cookie, y guarda el <code>jti</code> en{" "}
                        <code>revoked_tokens</code>.
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h2>Cómo verlo tú mismo</h2>
              <ol className="steps">
                <li>
                  Abre las herramientas del navegador con F12 y ve a <strong>Application</strong>, <strong>Cookies</strong>, <code>{window.location.origin}</code>. Copia el valor de{" "}
                  <code>{info.storage.cookie_name}</code>. También aparece en <strong>Network</strong>: elige cualquier llamada a <code>/api</code>, pestaña Headers,
                  cabecera <code>Cookie</code>.
                </li>
                <li>
                  Pégalo en jwt.io. En <strong>Claims Breakdown</strong> se ven las fechas de <code>iat</code> y <code>exp</code>.
                </li>
                <li>
                  Esta misma explicación sale en Network en la llamada <code>GET /api/auth/session</code>, y todas las rutas de la API están en{" "}
                  <a href="/api/docs" target="_blank" rel="noreferrer">
                    /api/docs
                  </a>
                  .
                </li>
              </ol>
            </section>
          </>
        )}
      </main>
    </>
  );
}
