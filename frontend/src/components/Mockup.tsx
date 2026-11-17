// Maquetas de pantallas: dibuja cómo se vería cada pantalla a partir de su especificación
// (secciones, campos y acciones). No es una imagen generada: es HTML, así que siempre
// coincide con lo que dice la etapa y se actualiza solo cuando la especificación cambia.

import type { Screen, UIAction } from "../types";

type Section = Screen["sections"][number];

const norm = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

// Valor de ejemplo verosímil según el nombre del campo. Si no reconoce el campo, muestra una barra gris.
const SAMPLES: [RegExp, string[]][] = [
  [/correo|email|mail/, ["camila@correo.cl", "diego@correo.cl", "sofia@correo.cl"]],
  [/contrasen|password|clave/, ["••••••••"]],
  [/telefono|celular|fono|whatsapp/, ["+56 9 8765 4321", "+56 9 1234 5678"]],
  [/rut\b/, ["12.345.678-9", "9.876.543-2"]],
  [/fecha|dia\b|vence|vencimiento/, ["24 nov 2026", "25 nov 2026", "28 nov 2026"]],
  [/hora|horario|inicio|fin\b|bloque/, ["18:00", "19:00", "20:30"]],
  [/precio|monto|total|valor|costo|tarifa|pago|saldo|presupuesto/, ["$12.990", "$8.500", "$24.000"]],
  [/cantidad|stock|cupos|unidades|personas|invitados/, ["12", "4", "30"]],
  [/estado|status/, ["Confirmada", "Pendiente", "Cancelada"]],
  [/socio|usuario|cliente|nombre completo|responsable|autor|vendedor|profesor|alumno|paciente/, ["Camila Rojas", "Diego Muñoz", "Sofía Pérez"]],
  [/cancha/, ["Cancha 1", "Cancha 2", "Cancha 3"]],
  [/deporte/, ["Fútbol", "Tenis", "Pádel"]],
  [/direccion|ubicacion|lugar|comuna/, ["Av. Grecia 8735, Peñalolén", "Los Presidentes 7400"]],
  [/categoria|tipo|rol/, ["General", "Premium", "Básico"]],
  [/descripcion|comentario|motivo|nota|detalle|mensaje/, ["Mantención programada", "Sin observaciones"]],
  [/activa|activo|habilitad|disponible/, ["Sí", "Sí", "No"]],
  [/porcentaje|avance|progreso/, ["75 %", "40 %", "100 %"]],
  [/foto|imagen|logo|avatar/, ["[imagen]"]],
];

// Nombre genérico ("Nombre", "Título") según la pantalla: en "Canchas" da "Cancha 1", "Cancha 2"...
let context = "";
const singular = (w: string) => {
  const first = (w.split(/\s+/).find((x) => x.length > 3 && !/^(mis|mi|tus|los|las|del|de|ver|nueva?|editar|gestion|admin)$/i.test(x)) ?? "Elemento").replace(/[^\p{L}]/gu, "");
  const one = /(on|or|al|el|ad|ar|er|ion)es$/i.test(first) ? first.slice(0, -2) : first.replace(/s$/i, "");
  return one.charAt(0).toUpperCase() + one.slice(1);
};

export function sample(label: string, i = 0): string | null {
  const n = norm(label);
  for (const [re, values] of SAMPLES) if (re.test(n)) return values[i % values.length];
  if (/^(nombre|titulo)\b/.test(n)) return `${singular(context)} ${i + 1}`;
  return null;
}

const STATE_TONE = (v: string) => {
  const n = norm(v);
  if (/confirm|activ|aprob|pagad|si$|listo|complet/.test(n)) return "ok";
  if (/pendien|revis|espera/.test(n)) return "wait";
  if (/cancel|rechaz|no$|vencid|bloque/.test(n)) return "off";
  return "";
};

function Value({ label, i }: { label: string; i: number }) {
  const v = sample(label, i);
  if (!v) return <span className="mk-bar" style={{ width: `${45 + ((label.length * 7 + i * 13) % 40)}%` }} />;
  if (/estado|status|activa|activo/.test(norm(label))) return <span className={`mk-chip ${STATE_TONE(v)}`}>{v}</span>;
  return <>{v}</>;
}

// --- Acciones -------------------------------------------------------------------------

const rowLevel = (a: UIAction) => !a.target_screen && (a.kind === "submit" || a.kind === "delete" || a.kind === "open_modal" || a.kind === "download");

function ActionButton({ a, onGo, primary, small }: { a: UIAction; onGo?: (id: string) => void; primary?: boolean; small?: boolean }) {
  const cls = ["mk-btn", a.kind === "delete" ? "danger" : primary ? "primary" : "secondary", small ? "small" : ""].join(" ");
  const tip = [a.endpoint_id && `Llama a ${a.endpoint_id}`, a.target_screen && `Va a ${a.target_screen}`, a.roles.length && `Solo ${a.roles.join(", ")}`].filter(Boolean).join(" · ");
  return (
    <button
      type="button"
      className={cls}
      title={tip || undefined}
      data-link={a.target_screen ? "1" : undefined}
      onClick={() => a.target_screen && onGo?.(a.target_screen)}
      tabIndex={onGo ? 0 : -1}
    >
      {a.label}
    </button>
  );
}

function Actions({ actions, onGo }: { actions: UIAction[]; onGo?: (id: string) => void }) {
  if (!actions.length) return null;
  const firstPrimary = actions.findIndex((a) => a.kind === "submit");
  return (
    <div className="mk-actions">
      {actions.map((a, i) => (
        <ActionButton key={a.label + i} a={a} onGo={onGo} primary={i === (firstPrimary === -1 ? 0 : firstPrimary)} />
      ))}
    </div>
  );
}

// --- Secciones según su tipo ------------------------------------------------------------

function Form({ s, onGo }: { s: Section; onGo?: (id: string) => void }) {
  return (
    <div className="mk-form">
      {s.elements.map((e, i) => {
        const v = sample(e, i);
        const long = /descripcion|comentario|mensaje|motivo|detalle|nota/.test(norm(e));
        return (
          <label className="mk-field" key={e + i}>
            <span>{e}</span>
            <span className={`mk-input${long ? " long" : ""}`}>{v ?? ""}</span>
          </label>
        );
      })}
      <Actions actions={s.actions} onGo={onGo} />
    </div>
  );
}

function Table({ s, onGo }: { s: Section; onGo?: (id: string) => void }) {
  const cols = s.elements.length ? s.elements.slice(0, 6) : ["Columna"];
  const rowActs = s.actions.filter(rowLevel);
  const pageActs = s.actions.filter((a) => !rowLevel(a));
  return (
    <>
      <div className="mk-table" role="table">
        <div className="mk-tr head" role="row">
          {cols.map((c) => (
            <span key={c} role="columnheader">
              {c}
            </span>
          ))}
          {rowActs.length > 0 && <span />}
        </div>
        {[0, 1, 2].map((r) => (
          <div className="mk-tr" role="row" key={r}>
            {cols.map((c) => (
              <span key={c} role="cell">
                <Value label={c} i={r} />
              </span>
            ))}
            {rowActs.length > 0 && (
              <span className="mk-row-acts">
                {rowActs.map((a, i) => (
                  <ActionButton key={a.label + i} a={a} onGo={onGo} small />
                ))}
              </span>
            )}
          </div>
        ))}
      </div>
      {pageActs.length > 0 && <Actions actions={pageActs} onGo={onGo} />}
    </>
  );
}

function List({ s, onGo }: { s: Section; onGo?: (id: string) => void }) {
  const [title, ...rest] = s.elements.length ? s.elements : ["Elemento"];
  const rowActs = s.actions.filter(rowLevel);
  const pageActs = s.actions.filter((a) => !rowLevel(a));
  return (
    <>
      <div className="mk-list">
        {[0, 1, 2].map((r) => (
          <div className="mk-item" key={r}>
            <div>
              <strong>{sample(title, r) ?? `${title} ${r + 1}`}</strong>
              <div className="mk-meta">
                {rest.map((e, i) => (
                  <span key={e + i}>
                    <Value label={e} i={r + i} />
                  </span>
                ))}
              </div>
            </div>
            <span className="mk-row-acts">
              {rowActs.map((a, i) => (
                <ActionButton key={a.label + i} a={a} onGo={onGo} small />
              ))}
            </span>
          </div>
        ))}
      </div>
      {pageActs.length > 0 && <Actions actions={pageActs} onGo={onGo} />}
    </>
  );
}

function Cards({ s, onGo }: { s: Section; onGo?: (id: string) => void }) {
  const [title, ...rest] = s.elements.length ? s.elements : ["Tarjeta"];
  return (
    <>
      <div className="mk-cards">
        {[0, 1, 2].map((r) => (
          <div className="mk-card" key={r}>
            <div className="mk-thumb" aria-hidden="true" />
            <strong>{sample(title, r) ?? `${title} ${r + 1}`}</strong>
            {rest.slice(0, 3).map((e, i) => (
              <div className="mk-meta" key={e + i}>
                {e}: <Value label={e} i={r} />
              </div>
            ))}
          </div>
        ))}
      </div>
      <Actions actions={s.actions} onGo={onGo} />
    </>
  );
}

function Detail({ s, onGo }: { s: Section; onGo?: (id: string) => void }) {
  return (
    <>
      <dl className="mk-detail">
        {s.elements.map((e, i) => (
          <div key={e + i}>
            <dt>{e}</dt>
            <dd>
              <Value label={e} i={i} />
            </dd>
          </div>
        ))}
      </dl>
      <Actions actions={s.actions} onGo={onGo} />
    </>
  );
}

function Filters({ s, onGo }: { s: Section; onGo?: (id: string) => void }) {
  return (
    <div className="mk-filters">
      {s.elements.map((e, i) => (
        <span className="mk-select" key={e + i}>
          <small>{e}</small>
          {sample(e, 0) ?? "Todos"} <span aria-hidden="true">▾</span>
        </span>
      ))}
      {s.actions.map((a, i) => (
        <ActionButton key={a.label + i} a={a} onGo={onGo} small />
      ))}
    </div>
  );
}

function Chart({ s, onGo }: { s: Section; onGo?: (id: string) => void }) {
  const bars = [62, 80, 45, 92, 70, 55, 85];
  return (
    <>
      <div className="mk-chart" aria-hidden="true">
        {bars.map((h, i) => (
          <span key={i} style={{ height: `${h}%` }} />
        ))}
      </div>
      {s.elements.length > 0 && <p className="mk-meta">{s.elements.join(" · ")}</p>}
      <Actions actions={s.actions} onGo={onGo} />
    </>
  );
}

function Calendar({ s, onGo }: { s: Section; onGo?: (id: string) => void }) {
  const days = ["L", "M", "M", "J", "V", "S", "D"];
  const busy = new Set([3, 9, 10, 16, 22, 24]);
  return (
    <>
      <div className="mk-cal">
        {days.map((d, i) => (
          <b key={i}>{d}</b>
        ))}
        {Array.from({ length: 28 }, (_, i) => (
          <span key={i} className={busy.has(i) ? "busy" : i === 12 ? "sel" : ""}>
            {i + 1}
          </span>
        ))}
      </div>
      {s.elements.length > 0 && <p className="mk-meta">{s.elements.join(" · ")}</p>}
      <Actions actions={s.actions} onGo={onGo} />
    </>
  );
}

function MapBox({ s, onGo }: { s: Section; onGo?: (id: string) => void }) {
  return (
    <>
      <div className="mk-map" aria-hidden="true">
        <i style={{ left: "28%", top: "40%" }} />
        <i style={{ left: "62%", top: "30%" }} />
        <i style={{ left: "48%", top: "66%" }} />
      </div>
      {s.elements.length > 0 && <p className="mk-meta">{s.elements.join(" · ")}</p>}
      <Actions actions={s.actions} onGo={onGo} />
    </>
  );
}

function Chat({ s, onGo }: { s: Section; onGo?: (id: string) => void }) {
  return (
    <div className="mk-chat">
      <span className="them">Hola, ¿en qué te puedo ayudar?</span>
      <span className="me">Quiero {norm(s.elements[0] ?? "reservar")}</span>
      <span className="mk-input">Escribe un mensaje…</span>
      <Actions actions={s.actions} onGo={onGo} />
    </div>
  );
}

function TabsBox({ s, onGo }: { s: Section; onGo?: (id: string) => void }) {
  return (
    <>
      <div className="mk-tabs">
        {(s.elements.length ? s.elements : ["Pestaña 1", "Pestaña 2"]).map((e, i) => (
          <span key={e + i} className={i === 0 ? "on" : ""}>
            {e}
          </span>
        ))}
      </div>
      <span className="mk-bar" style={{ width: "80%" }} />
      <span className="mk-bar" style={{ width: "60%" }} />
      <Actions actions={s.actions} onGo={onGo} />
    </>
  );
}

function TextBox({ s, onGo }: { s: Section; onGo?: (id: string) => void }) {
  return (
    <>
      {s.elements.map((e, i) => (
        <p className="mk-text" key={e + i}>
          {e}
        </p>
      ))}
      <Actions actions={s.actions} onGo={onGo} />
    </>
  );
}

const RENDER: Record<string, (p: { s: Section; onGo?: (id: string) => void }) => JSX.Element> = {
  form: Form,
  table: Table,
  list: List,
  cards: Cards,
  detail: Detail,
  filters: Filters,
  chart: Chart,
  calendar: Calendar,
  map: MapBox,
  chat: Chat,
  tabs: TabsBox,
  text: TextBox,
};

// Una sección "Menú" (o de tipo other con solo navegación) se dibuja como el menú de la app.
const isMenu = (s: Section) =>
  /menu|navegacion|barra/.test(norm(s.title)) || (s.kind === "other" && s.actions.length > 0 && s.actions.every((a) => a.kind === "navigate" || a.target_screen));

export interface MockupProps {
  screen: Screen;
  appName: string;
  device: "desktop" | "mobile";
  menu?: UIAction[];
  onGo?: (id: string) => void;
  compact?: boolean;
}

export function menuFrom(screens: Screen[]): UIAction[] {
  const seen = new Set<string>();
  const out: UIAction[] = [];
  for (const sc of screens)
    for (const s of sc.sections)
      if (isMenu(s))
        for (const a of s.actions)
          if (!seen.has(a.label)) {
            seen.add(a.label);
            out.push(a);
          }
  return out;
}

// Cada proyecto recibe un color de acento estable, para que sus maquetas no se vean como Ideator.
const ACCENTS = ["#0f766e", "#7c3aed", "#c2410c", "#0369a1", "#be185d", "#4d7c0f", "#b45309"];
export const accentFor = (name: string) => ACCENTS[[...name].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) % ACCENTS.length];

export default function Mockup({ screen, appName, device, menu = [], onGo, compact }: MockupProps) {
  context = screen.name;
  const isPublic = screen.roles.includes("publico") || screen.roles.length === 0;
  const own = screen.sections.filter(isMenu).flatMap((s) => s.actions);
  const nav = isPublic ? [] : own.length ? own : menu;
  const body = screen.sections.filter((s) => !isMenu(s));
  const centered = isPublic && body.length <= 2 && body.every((s) => s.kind === "form");
  return (
    <div className={`mk ${device}${compact ? " compact" : ""}`} style={{ ["--mk-accent" as string]: accentFor(appName) }} aria-label={`Maqueta de ${screen.name}`}>
      <div className="mk-chrome" aria-hidden="true">
        {device === "desktop" ? (
          <>
            <i />
            <i />
            <i />
            <span className="mk-url">
              {norm(appName).replace(/[^a-z0-9]+/g, "") || "app"}.cl{screen.route}
            </span>
          </>
        ) : (
          <span className="mk-notch" />
        )}
      </div>
      <div className="mk-app">
        {!isPublic && (
          <header className="mk-header">
            <strong>{appName}</strong>
            {device === "desktop" ? (
              <nav>
                {nav.slice(0, 5).map((a, i) => (
                  <ActionButton key={a.label + i} a={{ ...a, kind: "navigate" }} onGo={onGo} small />
                ))}
              </nav>
            ) : (
              <span className="mk-burger" aria-hidden="true">
                ☰
              </span>
            )}
          </header>
        )}
        <main className={centered ? "mk-main centered" : "mk-main"}>
          {centered && <div className="mk-brand">{appName}</div>}
          <h1 className="mk-h1">{screen.name}</h1>
          {!compact && <p className="mk-purpose">{screen.purpose}</p>}
          {body.map((s, i) => {
            const R = RENDER[s.kind];
            return (
              <section className={`mk-sec k-${s.kind}`} key={s.title + i}>
                {!centered && body.length > 1 && <h2 className="mk-h2">{s.title}</h2>}
                {R ? (
                  <R s={s} onGo={onGo} />
                ) : (
                  <>
                    {s.elements.map((e, j) => (
                      <div className="mk-meta" key={e + j}>
                        {e}
                      </div>
                    ))}
                    <Actions actions={s.actions} onGo={onGo} />
                  </>
                )}
              </section>
            );
          })}
        </main>
      </div>
    </div>
  );
}
