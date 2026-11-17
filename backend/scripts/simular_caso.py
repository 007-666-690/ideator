"""Recorre todo Ideator con el modelo real (GPT-5 en Azure) y guarda los documentos.

Sirve para probar la calidad de punta a punta sin usar la interfaz: crea un
proyecto con la idea indicada, responde las preguntas (eligiendo la primera
opción o delegando a la IA), genera y aprueba cada etapa, corre la revisión y
escribe los dos Markdown en la carpeta de salida.

Uso (desde la carpeta backend, con el .env configurado con LLM_PROVIDER=azure o gemini):
    python scripts/simular_caso.py --idea "Una app para ..." --salida salida
    python scripts/simular_caso.py --idea-archivo caso.txt --rondas 4
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def check(r, what: str):
    if r.status_code >= 400:
        log(f"ERROR en {what}: {r.status_code} {r.text[:1500]}")
        sys.exit(1)
    return r.json() if r.content else None


def errors(stage: dict) -> list[str]:
    return [i["message"] for i in stage["issues"] if i["severity"] == "error"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--idea", help="Texto de la idea")
    parser.add_argument("--idea-archivo", help="Archivo con la idea")
    parser.add_argument("--nombre", default="Caso de prueba")
    parser.add_argument("--rondas", type=int, default=4, help="Máximo de rondas de preguntas")
    parser.add_argument("--delegar", action="store_true", help="Delegar todas las respuestas a la IA")
    parser.add_argument("--arquitectura", default=None, help="Forzar escenario (A1..A5)")
    parser.add_argument("--salida", default="salida")
    args = parser.parse_args()

    idea = args.idea or (Path(args.idea_archivo).read_text(encoding="utf-8") if args.idea_archivo else None)
    if not idea:
        parser.error("Indica --idea o --idea-archivo")

    tmp = Path(tempfile.mkdtemp())
    settings = Settings(database_url=f"sqlite:///{tmp / 'sim.db'}", log_level="WARNING", login_max_attempts=100)
    if settings.llm_provider not in ("azure", "gemini"):
        log("Aviso: LLM_PROVIDER no es 'azure' ni 'gemini'; se usará el modelo simulado.")
    out = Path(args.salida)
    out.mkdir(parents=True, exist_ok=True)
    trace: list[dict] = []

    with TestClient(create_app(settings)) as c:
        check(c.post("/api/auth/register", json={"email": "simulador@example.com", "name": "Simulador", "password": "simulador-123"}), "registro")
        pid = check(c.post("/api/projects", json={"name": args.nombre, "idea": idea}), "crear proyecto")["id"]
        stage = lambda kind: check(c.get(f"/api/projects/{pid}/stages/{kind}"), kind)  # noqa: E731

        t = time.time()
        s = check(c.post(f"/api/projects/{pid}/product/start", json={"version": stage("product")["version"]}), "inicio")
        log(f"Ronda 1 lista en {time.time() - t:.0f}s")
        for rnd in range(1, args.rondas + 1):
            open_q = [q for q in s["questions"] if q["status"] == "open"]
            trace.append({"ronda": rnd, "preguntas": [{k: q[k] for k in ("code", "text", "blocking", "options", "rationale")} for q in open_q]})
            for q in open_q:
                log(f"  {q['code']} {'[BLOQUEANTE] ' if q['blocking'] else ''}{q['text']}")
                for o in q["options"]:
                    log(f"      · {o}")
            if not open_q:
                break
            answers = []
            for q in open_q:
                text = "[DELEGADO] El equipo delega esta decisión a Ideator." if args.delegar or not q["options"] else q["options"][0]
                answers.append({"question_id": q["id"], "answer": text})
            t = time.time()
            s = check(c.post(f"/api/projects/{pid}/product/turn", json={"version": s["version"], "answers": answers}), f"ronda {rnd + 1}")
            log(f"Ronda {rnd + 1} lista en {time.time() - t:.0f}s. Mensaje: {s['messages'][-1]['content'] if s['messages'] else ''}")

        s = stage("product")
        if errors(s):
            log("La definición quedó incompleta:\n  - " + "\n  - ".join(errors(s)))
            (out / "definicion.json").write_text(json.dumps(s["content"]["brief"], ensure_ascii=False, indent=2), encoding="utf-8")
            sys.exit(2)
        check(c.post(f"/api/projects/{pid}/stages/product/approve", json={"version": s["version"]}), "aprobar producto")

        def generate_and_approve(kind: str) -> None:
            t = time.time()
            st = check(c.post(f"/api/projects/{pid}/stages/{kind}/generate", json={"version": stage(kind)["version"]}), kind)
            log(f"{kind} generado en {time.time() - t:.0f}s ({len(errors(st))} errores, {len(st['issues']) - len(errors(st))} advertencias)")
            if errors(st):
                fix = "Corrige estos problemas manteniendo todo lo demás igual:\n- " + "\n- ".join(errors(st))
                log("  Pidiendo corrección a la IA:\n  - " + "\n  - ".join(errors(st)))
                st = check(c.post(f"/api/projects/{pid}/stages/{kind}/generate", json={"version": st["version"], "instructions": fix}), f"{kind} corrección")
            if errors(st):
                log(f"{kind} sigue con errores:\n  - " + "\n  - ".join(errors(st)))
                sys.exit(3)
            check(c.post(f"/api/projects/{pid}/stages/{kind}/approve", json={"version": st["version"]}), f"aprobar {kind}")

        for kind in ("data_model", "api", "frontend"):
            generate_and_approve(kind)

        t = time.time()
        a = check(c.post(f"/api/projects/{pid}/architecture/evaluate", json={"version": stage("architecture")["version"]}), "evaluar arquitectura")
        ev = a["content"]["evaluation"]
        log(f"Arquitecturas evaluadas en {time.time() - t:.0f}s: " + ", ".join(f"{x['scenario_id']}={x['fit']}" for x in ev["scores"]) + f" → {ev['recommended']}")
        if args.arquitectura:
            a = check(c.post(f"/api/projects/{pid}/architecture/select", json={"version": a["version"], "scenario_id": args.arquitectura}), "seleccionar")
        generate_and_approve("architecture")

        t = time.time()
        rv = check(c.post(f"/api/projects/{pid}/review/run", json={"version": stage("review")["version"]}), "revisión")
        log(f"Revisión en {time.time() - t:.0f}s: {rv['content']['summary']}")
        for f in rv["content"]["findings"]:
            log(f"  [{f['severity']}] {f['description']}\n      → {f['suggestion']}")
        product = stage("product")
        if any(not x["accepted"] for x in product["content"]["brief"]["assumptions"]):
            check(c.post(f"/api/projects/{pid}/product/assumptions/accept", json={"version": product["version"], "ids": None}), "supuestos")
        rv = stage("review")
        for f in rv["content"]["findings"]:
            if f["status"] == "open" and f["source"] == "ia":
                rv = check(
                    c.post(f"/api/projects/{pid}/review/findings/{f['id']}", json={"version": rv["version"], "resolution": "accepted", "note": "Aceptado por el simulador"}),
                    "hallazgo",
                )
        if errors(rv):
            log("La revisión tiene errores:\n  - " + "\n  - ".join(errors(rv)))
            sys.exit(4)
        check(c.post(f"/api/projects/{pid}/stages/review/approve", json={"version": rv["version"]}), "aprobar revisión")
        docs = check(c.post(f"/api/projects/{pid}/documents"), "documentos")
        for d in docs:
            (out / d["filename"]).write_text(d["content"], encoding="utf-8")
        (out / "preguntas.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "revision.json").write_text(json.dumps(rv["content"], ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"Listo. Documentos en {out.resolve()}")


if __name__ == "__main__":
    main()
