import { useEffect, useState } from "react";
import { api } from "../../api";
import Mockup, { menuFrom } from "../../components/Mockup";
import { Mermaid, Tabs } from "../../components/ui";
import type { FrontendSpec, Screen } from "../../types";
import type { StageCtx } from "../Project";
import { ChangeRequest, GenerateFirst, JsonEditor, StageIntro } from "./common";

type TabKey = "proto" | "all" | "map" | "json";

function ScreenNotes({ screen, spec }: { screen: Screen; spec: FrontendSpec }) {
  const out = spec.navigation.filter((n) => n.from_screen === screen.id);
  const name = (id: string) => spec.screens.find((s) => s.id === id)?.name ?? id;
  return (
    <dl className="screen-notes">
      <div>
        <dt>Ruta</dt>
        <dd className="mono">{screen.route}</dd>
      </div>
      <div>
        <dt>Quién entra</dt>
        <dd>{screen.roles.join(", ")}</dd>
      </div>
      {screen.data_endpoints.length > 0 && (
        <div>
          <dt>Datos que carga</dt>
          <dd className="mono">{screen.data_endpoints.join(", ")}</dd>
        </div>
      )}
      {out.length > 0 && (
        <div>
          <dt>Lleva a</dt>
          <dd>{out.map((n) => `${name(n.to_screen)} (${n.trigger})`).join(" · ")}</dd>
        </div>
      )}
      {screen.states.length > 0 && (
        <div>
          <dt>Estados</dt>
          <dd>
            <ul>
              {screen.states.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </dd>
        </div>
      )}
    </dl>
  );
}

export default function FrontendStage({ ctx }: { ctx: StageCtx }) {
  const { project, view, run } = ctx;
  const spec: FrontendSpec | null = view.content.data;
  const [tab, setTab] = useState<TabKey>("proto");
  const [current, setCurrent] = useState<string | null>(null);
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [history, setHistory] = useState<string[]>([]);

  useEffect(() => {
    setCurrent(spec?.start_screen ?? spec?.screens[0]?.id ?? null);
    setHistory([]);
  }, [view.version]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!spec) {
    return (
      <>
        <StageIntro title="Pantallas y navegación">Plano propone las pantallas del MVP, dibuja cómo se vería cada una y arma un prototipo navegable con sus botones.</StageIntro>
        <GenerateFirst ctx={ctx} what="pantallas definidas" button="Proponer pantallas" />
      </>
    );
  }

  const screen = spec.screens.find((s) => s.id === current) ?? spec.screens[0];
  const menu = menuFrom(spec.screens);
  const go = (id: string) => {
    if (!spec.screens.some((s) => s.id === id) || id === screen?.id) return;
    setHistory((h) => [...h, screen.id]);
    setCurrent(id);
  };
  const back = () =>
    setHistory((h) => {
      const prev = h[h.length - 1];
      if (prev) setCurrent(prev);
      return h.slice(0, -1);
    });

  return (
    <>
      <StageIntro title="Pantallas y navegación">
        {spec.summary} {spec.layout}
      </StageIntro>
      <Tabs<TabKey>
        tabs={[
          ["proto", "Prototipo"],
          ["all", `Todas las pantallas (${spec.screens.length})`],
          ["map", "Mapa de navegación"],
          ["json", "JSON"],
        ]}
        value={tab}
        onChange={setTab}
      />

      {tab === "proto" && screen && (
        <div className="section proto">
          <div className="proto-bar">
            <div className="segmented" role="group" aria-label="Dispositivo">
              <button aria-pressed={device === "desktop"} onClick={() => setDevice("desktop")}>
                Computador
              </button>
              <button aria-pressed={device === "mobile"} onClick={() => setDevice("mobile")}>
                Celular
              </button>
            </div>
            <button className="btn ghost small" disabled={!history.length} onClick={back}>
              ← Atrás
            </button>
            <button className="btn ghost small" disabled={screen.id === spec.start_screen} onClick={() => go(spec.start_screen)}>
              Ir al inicio
            </button>
            <span className="small muted grow">Haz clic en los botones de la maqueta para navegar como lo haría un usuario.</span>
          </div>
          <div className="proto-grid">
            <nav className="screen-index" aria-label="Pantallas">
              {spec.screens.map((s) => (
                <button key={s.id} aria-current={s.id === screen.id ? "page" : undefined} onClick={() => go(s.id)}>
                  <span className="sid">{s.id}</span>
                  <span>{s.name}</span>
                  {s.id === spec.start_screen && <span className="start">inicio</span>}
                </button>
              ))}
            </nav>
            <div className="proto-stage">
              <Mockup screen={screen} appName={project.name} device={device} menu={menu} onGo={go} />
              <ScreenNotes screen={screen} spec={spec} />
            </div>
          </div>
        </div>
      )}

      {tab === "all" && (
        <div className="section">
          <div className="mockup-wall">
            {spec.screens.map((s) => (
              <button
                key={s.id}
                className="wall-item"
                onClick={() => {
                  setCurrent(s.id);
                  setHistory([]);
                  setTab("proto");
                }}
              >
                <span className="wall-label">
                  <span className="sid">{s.id}</span> {s.name}
                  {s.id === spec.start_screen && <span className="start">inicio</span>}
                </span>
                <span className="wall-frame" aria-hidden="true">
                  <Mockup screen={s} appName={project.name} device="desktop" menu={menu} compact />
                </span>
              </button>
            ))}
          </div>
          {spec.design_guidelines.length > 0 && (
            <>
              <h4 style={{ marginTop: 24 }}>Lineamientos de diseño</h4>
              <ul>
                {spec.design_guidelines.map((g, i) => (
                  <li key={i}>{g}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {tab === "map" && <div className="section">{view.navigation_map && <Mermaid code={view.navigation_map} />}</div>}
      {tab === "json" && (
        <div className="section">
          <JsonEditor ctx={ctx} value={spec} onSave={(d) => run(() => api.saveStage(project.id, "frontend", view.version, d, "Edición de pantallas"), "Pantallas guardadas.")} />
        </div>
      )}
      <ChangeRequest ctx={ctx} placeholder="Ej.: separa la grilla de disponibilidad en una pantalla por deporte" />
    </>
  );
}
