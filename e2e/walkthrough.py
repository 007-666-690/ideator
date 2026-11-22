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
    before = page.url
    btn.click()
    # Al aprobar, la app pasa sola a la etapa siguiente (que la IA ya está preparando)
    page.wait_for_function("u => location.href !== u", arg=before, timeout=15000)


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
    ask = page.locator(".bubble.ask")
    expect(ask).to_be_visible(timeout=15000)
    shot(page, "03-chat")
    # Chat: una opción con un clic, la segunda delegada y la tercera escrita
    ask.get_by_role("button", name="Socios y un administrador del club").click()
    ask.get_by_role("button", name="Que decida Plano").click()
    page.get_by_label("Escribe tu respuesta").fill("60 minutos")
    page.get_by_role("button", name="Enviar", exact=True).click()  # la última respuesta se envía sola
    expect(page.locator(".bubble.done")).to_contain_text("Tengo todo lo necesario", timeout=15000)
    shot(page, "04-definicion")
    approve(page)

    # Piloto automático: después de aprobar, la siguiente etapa se genera sola y la app navega a ella
    for kind in ("data_model", "api", "frontend"):
        page.wait_for_url(f"**/{kind}", timeout=15000)
        expect(page.get_by_role("button", name="Aprobar etapa")).to_be_enabled(timeout=30000)
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
            page.get_by_role("button", name="Acercar").click()
            shot(page, "09-mapa")
        approve(page)

    page.wait_for_url("**/architecture", timeout=15000)
    expect(page.get_by_text("Por qué esta arquitectura")).to_be_visible(timeout=30000)  # evaluó, eligió y detalló sola
    shot(page, "10-arquitectura")
    approve(page)

    page.wait_for_url("**/testing", timeout=15000)
    expect(page.get_by_role("tab", name="Casos de prueba", exact=False)).to_be_visible(timeout=15000)
    page.locator(".test-case summary").first.click()
    shot(page, "10b-pruebas")
    page.get_by_role("tab", name="Datos ficticios").click()
    shot(page, "10c-datos")
    approve(page)

    page.wait_for_url("**/review", timeout=15000)
    expect(page.get_by_role("heading", name="Hallazgos")).to_be_visible(timeout=30000)
    page.get_by_role("button", name="Aceptar sin cambios").click()
    page.get_by_label("¿Por qué se acepta sin cambios? Queda registrado.").fill("Se resuelve al implementar")
    page.get_by_role("button", name="Aceptar hallazgo").click()
    page.wait_for_timeout(800)
    shot(page, "11-revision")
    approve(page)

    page.wait_for_url("**/documents", timeout=15000)
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
