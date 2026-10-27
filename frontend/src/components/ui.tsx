import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChecklistItem, Issue } from "../types";
import { initials } from "../util";

// --- Avisos ---------------------------------------------------------------------

interface Toast {
  id: number;
  text: string;
  kind: "info" | "error";
}
const ToastContext = createContext<(text: string, kind?: "info" | "error") => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, kind: "info" | "error" = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "error" ? 7000 : 4000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

// --- Modal ------------------------------------------------------------------------

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    ref.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <div className="row between">
          <h3 style={{ margin: 0 }}>{title}</h3>
          <button className="btn ghost" onClick={onClose} aria-label="Cerrar">
            Cerrar
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

// --- Piezas pequeñas ------------------------------------------------------------------

export function Avatar({ name }: { name: string }) {
  return (
    <span className="avatar" title={name}>
      {initials(name)}
    </span>
  );
}

export function Busy({ text }: { text?: string }) {
  return (
    <div className="busy" role="status">
      <span>{text ?? "La IA está trabajando. Puede tardar hasta un par de minutos."}</span>
      <span className="line" aria-hidden="true" />
    </div>
  );
}

export function Checklist({ items }: { items: ChecklistItem[] }) {
  return (
    <ul className="checklist">
      {items.map((c) => (
        <li key={c.key} className={c.ok ? "ok" : "no"}>
          <span className="mark" aria-hidden="true">
            {c.ok ? "✓" : ""}
          </span>
          <span>
            {c.label}
            <span className="sr-only">{c.ok ? " (listo)" : " (pendiente)"}</span>
            {c.detail && !c.ok && <span className="detail">{c.detail}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function IssueList({ issues, empty }: { issues: Issue[]; empty?: string }) {
  const sorted = [...issues].sort((a, b) => (a.severity === b.severity ? 0 : a.severity === "error" ? -1 : 1));
  if (!sorted.length) return <p className="muted small">{empty ?? "Sin problemas detectados."}</p>;
  return (
    <ul className="issues">
      {sorted.map((i, idx) => (
        <li key={`${i.code}-${idx}`} className={i.severity}>
          <span className="dot" aria-hidden="true" />
          <span>
            <span className="sr-only">{i.severity === "error" ? "Error: " : "Advertencia: "}</span>
            {i.message}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: [T, string][]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map(([key, label]) => (
        <button key={key} role="tab" className="tab" aria-selected={value === key} onClick={() => onChange(key)}>
          {label}
        </button>
      ))}
    </div>
  );
}

export function ConfirmButton({
  label,
  confirmLabel,
  onConfirm,
  className = "btn secondary",
  disabled,
  question,
}: {
  label: string;
  confirmLabel: string;
  onConfirm: () => void;
  className?: string;
  disabled?: boolean;
  question: string;
}) {
  const [asking, setAsking] = useState(false);
  if (!asking)
    return (
      <button className={className} onClick={() => setAsking(true)} disabled={disabled}>
        {label}
      </button>
    );
  return (
    <span className="row">
      <span className="small">{question}</span>
      <button
        className="btn danger small"
        onClick={() => {
          setAsking(false);
          onConfirm();
        }}
      >
        {confirmLabel}
      </button>
      <button className="btn ghost small" onClick={() => setAsking(false)}>
        Cancelar
      </button>
    </span>
  );
}

// --- Mermaid y Markdown ------------------------------------------------------------------

let mermaidPromise: Promise<any> | null = null;
function loadMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import("mermaid").then((m) => {
      m.default.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: "base",
        fontFamily: "Instrument Sans, system-ui, sans-serif",
        themeVariables: {
          primaryColor: "#ffffff",
          primaryBorderColor: "#1e2a5a",
          primaryTextColor: "#1e2a5a",
          lineColor: "#5d6675",
          fontSize: "13px",
        },
        er: { useMaxWidth: true },
        flowchart: { useMaxWidth: true, htmlLabels: true },
      });
      return m.default;
    });
  }
  return mermaidPromise;
}

export function Mermaid({ code }: { code: string }) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string>("");
  useEffect(() => {
    let alive = true;
    const renderId = `m${id}${Date.now()}`;
    loadMermaid()
      .then(async (mermaid) => {
        await mermaid.parse(code);
        return mermaid.render(renderId, code);
      })
      .then((res: { svg: string }) => {
        if (alive) {
          setSvg(res.svg);
          setError("");
        }
      })
      .catch((e: unknown) => {
        // Mermaid deja nodos temporales en el body cuando falla
        document.getElementById(renderId)?.remove();
        document.getElementById(`d${renderId}`)?.remove();
        if (alive) setError(String(e));
      });
    return () => {
      alive = false;
    };
  }, [code, id]);
  if (error)
    return (
      <div className="diagram">
        <p className="muted small">No se pudo dibujar el diagrama. Este es su código:</p>
        <pre>{code}</pre>
      </div>
    );
  return <div className="diagram" aria-label="Diagrama" dangerouslySetInnerHTML={{ __html: svg }} />;
}

export function Markdown({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        pre({ node, children }) {
          const codeNode: any = node?.children?.[0];
          const cls = codeNode?.properties?.className;
          if (Array.isArray(cls) && cls.includes("language-mermaid")) return <>{children}</>;
          return <pre>{children}</pre>;
        },
        code({ className, children }) {
          const lang = /language-(\w+)/.exec(className ?? "")?.[1];
          const content = String(children).replace(/\n$/, "");
          if (lang === "mermaid") return <Mermaid code={content} />;
          return <code className={className}>{children}</code>;
        },
      }}
    >
      {text}
    </ReactMarkdown>
  );
}
