"""Recorrido de punta a punta en el navegador (Playwright) con el modelo simulado.

Uso: python e2e/walkthrough.py http://localhost:8000 carpeta_capturas
"""
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "e2e-shots")
OUT.mkdir(parents=True, exist_ok=True)


def shot(page, name):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)


def approve(page):
    btn = page.get_by_role("button", name="Aprobar etapa")
    expect(btn).to_be_enabled(timeout=15000)
    btn.click()
    expect(page.locator(".stamp").first).to_be_visible(timeout=15000)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{BASE}/login")
    shot(page, "01-login")
    page.get_by_role("button", name="Crear cuenta").click()
    page.get_by_label("Nombre").fill("Jefe Vergara")
    page.get_by_label("Correo").fill(f"jefe{int(time.time())}@demo.cl")
    page.get_by_label("Contraseña").fill("clave-segura-1")
    page.locator("form").get_by_role("button", name="Crear cuenta").click()
    expect(page.get_by_role("heading", name="Tus proyectos")).to_be_visible()
    page.get_by_label("Nombre").fill("ReservaCancha")
    page.get_by_label("La idea, como la contarías en voz alta").fill(
        "Una app para que los socios de un club reserven canchas de tenis y pádel sin llamar a la secretaría."
    )
    shot(page, "02-dashboard")
    page.get_by_role("button", name="Crear proyecto").click()

    page.get_by_role("button", name="Comenzar la definición").click()
    expect(page.locator(".question").first).to_be_visible(timeout=15000)
    shot(page, "03-preguntas")
    # Responder: opción en la primera, delegar la segunda, texto en la tercera
    q = page.locator(".question")
    q.nth(0).get_by_role("button", name="Socios y un administrador del club").click()
    q.nth(1).get_by_role("button", name="Que decida Plano").click()
    q.nth(2).locator("textarea").fill("60 minutos")
    page.get_by_role("button", name="Enviar 3 respuestas").click()
    expect(page.get_by_text("No hay preguntas pendientes")).to_be_visible(timeout=15000)
    shot(page, "04-definicion")
    approve(page)

    for kind, label in (("data_model", "Proponer modelo de datos"), ("api", "Proponer API"), ("frontend", "Proponer pantallas")):
        page.goto(page.url.rsplit("/", 1)[0] + f"/{kind}")
        page.get_by_role("button", name=label).click()
        expect(page.get_by_role("button", name="Aprobar etapa")).to_be_enabled(timeout=15000)
        if kind == "data_model":
            page.wait_for_selector(".entity-card", timeout=15000)
            shot(page, "05-datos-diagrama")
            page.get_by_role("tab", name="Tablas (5)").click()
            shot(page, "06-datos-tablas")
        if kind == "api":
            page.get_by_role("button", name="EP-08").click()
            shot(page, "07-api")
        if kind == "frontend":
            page.get_by_role("button", name="PA-03 Disponibilidad").click()
            page.locator(".mk").get_by_role("button", name="Reservar bloque").click()
            expect(page.locator(".mk-h1")).to_have_text("Confirmar reserva")
            shot(page, "08-pantallas")
            page.get_by_role("tab", name="Mapa de navegación").click()
            page.wait_for_selector(".diagram svg", timeout=15000)
            shot(page, "09-mapa")
        approve(page)

    page.goto(page.url.rsplit("/", 1)[0] + "/architecture")
    page.get_by_role("button", name="Evaluar las cinco con IA").click()
    expect(page.get_by_text("Recomendada")).to_be_visible(timeout=15000)
    page.get_by_role("button", name="Detallar A1").click()
    expect(page.get_by_text("Por qué esta arquitectura")).to_be_visible(timeout=15000)
    shot(page, "10-arquitectura")
    approve(page)

    page.goto(page.url.rsplit("/", 1)[0] + "/review")
    page.get_by_role("button", name="Ejecutar revisión").click()
    expect(page.get_by_text("Hallazgos")).to_be_visible(timeout=15000)
    page.get_by_role("button", name="Aceptar todos los supuestos").click()
    page.wait_for_timeout(800)
    page.get_by_role("button", name="Aceptar sin cambios").click()
    page.get_by_label("¿Por qué se acepta sin cambios? Queda registrado.").fill("Se resuelve al implementar")
    page.get_by_role("button", name="Aceptar hallazgo").click()
    page.wait_for_timeout(800)
    shot(page, "11-revision")
    approve(page)

    page.goto(page.url.rsplit("/", 1)[0] + "/documents")
    page.get_by_role("button", name="Generar documentos").click()
    expect(page.locator(".doc-view h1")).to_be_visible(timeout=15000)
    page.wait_for_timeout(1500)
    shot(page, "12-documentos")

    mobile = browser.new_page(viewport={"width": 390, "height": 844})
    mobile.context.add_cookies(page.context.cookies())
    mobile.goto(page.url.rsplit("/", 1)[0] + "/product")
    mobile.wait_for_timeout(1500)
    shot(mobile, "13-movil")
    print("OK", page.url)
    browser.close()
