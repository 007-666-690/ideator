import { useState } from "react";
import { api } from "../../api";
import { Mermaid, Tabs } from "../../components/ui";
import type { FrontendSpec, Screen } from "../../types";
import type { StageCtx } from "../Project";
import { ChangeRequest, GenerateFirst, JsonEditor, StageIntro } from "./common";

function Sketch({ screen, start }: { screen: Screen; start: boolean }) {
  return (
    <article className="sketch" aria-label={`Boceto de ${screen.name}`}>
      <div className="bar">
        <strong>
          {screen.id} {screen.name}
        </strong>
        <span className="route">{screen.route}</span>
      </div>
      <p className="muted" style={{ margin: "0 0 8px" }}>
        {screen.purpose}
        {start ? " Es la pantalla inicial." : ""}
      </p>
      {screen.sections.map((sec, i) => (
        <div className="block" key={i}>
          <div className="bt">
            {sec.title} <span className="muted">({sec.kind})</span>
          </div>
          {sec.elements.map((e) => (
            <span className="placeholder" key={e}>
              {e}
            </span>
          ))}
          <div>
            {sec.actions.map((a) => (
              <span className="act" key={a.label} title={[a.endpoint_id && `Llama a ${a.endpoint_id}`, a.target_screen && `Va a ${a.target_screen}`].filter(Boolean).join(", ")}>
                {a.label}
                {a.endpoint_id ? ` (${a.endpoint_id})` : ""}
                {a.roles.length ? ` (${a.roles.join(", ")})` : ""}
              </span>
            ))}
          </div>
        </div>
      ))}
      <div className="who">
        Acceso: {screen.roles.join(", ")}
        {screen.data_endpoints.length > 0 && `. Carga ${screen.data_endpoints.join(", ")}`}
        {screen.journey_steps.length > 0 && `. Pasos del recorrido: ${screen.journey_steps.join(", ")}`}.
      </div>
      {screen.states.length > 0 && <div className="who">Estados: {screen.states.join("; ")}</div>}
    </article>
  );
}

export default function FrontendStage({ ctx }: { ctx: StageCtx }) {
  const { project, view, run } = ctx;
  const spec: FrontendSpec | null = view.content.data;
  const [tab, setTab] = useState<"map" | "screens" | "json">("screens");

  if (!spec) {
    return (
      <>
        <StageIntro title="Pantallas y navegación">Ideator propone las pantallas del MVP, qué muestra cada una, qué acciones llaman a qué endpoint y cómo se navega entre ellas.</StageIntro>
        <GenerateFirst ctx={ctx} what="pantallas definidas" button="Proponer pantallas" />
      </>
    );
  }

  return (
    <>
      <StageIntro title="Pantallas y navegación">
        {spec.summary} {spec.layout}
      </StageIntro>
      <Tabs
        tabs={[
          ["screens", `Bocetos (${spec.screens.length})`],
          ["map", "Mapa de navegación"],
          ["json", "JSON"],
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "screens" && (
        <div className="section">
          <div className="screens">
            {spec.screens.map((s) => (
              <Sketch key={s.id} screen={s} start={s.id === spec.start_screen} />
            ))}
          </div>
          {spec.design_guidelines.length > 0 && (
            <>
              <h4 style={{ marginTop: 20 }}>Lineamientos</h4>
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
