"""
Extractor de presentaciones incrustadas en un aula virtual Moodle.

Entra al aula con usuario y contraseña (Playwright), abre la página que le
pases, busca TODAS las presentaciones de Google Slides incrustadas, saca una
captura de cada diapositiva y las junta en UN SOLO documento:

    <salida>/<nombre>.pdf    (todas las diapositivas, en orden)
    <salida>/<nombre>.pptx   (lo mismo, una imagen por diapositiva)

Se usa desde la interfaz web (app.py) o desde la consola:

    python extractor.py "https://campus.ejemplo.edu.ar/mod/page/view.php?id=12345"
    python extractor.py URL --nombre "Clase 3 - Didáctica" --salida "D:\\Slides"
    python extractor.py URL --ver         (muestra el navegador mientras trabaja)

Usuario y contraseña van en el archivo .env (ver .env.example), nunca en el código.
"""
import argparse
import hashlib
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

BASE = Path(__file__).resolve().parent
SALIDA_DEFAULT = BASE / "salida"
VIEWPORT = {"width": 1600, "height": 900}
MAX_SLIDES = 300                # tope de seguridad por presentación
INTERVALO_MS = 400              # cada cuánto se compara mientras se espera que la diapositiva se asiente
ESPERA_MAX_MS = 8000            # tope por si una diapositiva nunca termina de asentarse
PATRON_SLIDES = re.compile(r"docs\.google\.com/presentation/", re.I)


# ---------------------------------------------------------------------------
# Login en Moodle
# ---------------------------------------------------------------------------

def _esperar_red(page, ms: int = 5000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=ms)
    except Exception:  # noqa: BLE001 -- páginas con conexiones abiertas: seguimos igual
        pass


def aceptar_cookies(page, timeout: int = 4000) -> None:
    """Popup 'Preferencias de datos' de algunos Moodle: si aparece, aprieta 'Sí'."""
    try:
        page.locator("text=Preferencias de datos").wait_for(state="visible", timeout=timeout)
        page.get_by_role("button", name="Sí", exact=True).click()
        page.wait_for_timeout(300)
    except Exception:  # noqa: BLE001
        pass


def hay_formulario_login(page) -> bool:
    return page.locator("#username").count() > 0 and page.locator("#password").count() > 0


def url_login(url: str) -> str:
    """Login de Moodle: MOODLE_URL del .env o, si no hay, el sitio del link que se pasó."""
    base = os.environ.get("MOODLE_URL", "").strip().rstrip("/")
    if not base:
        u = urlparse(url)
        # Moodle instalado en una subcarpeta (ej. https://sitio/campus/mod/...): cortamos antes de /mod, /course, etc.
        m = re.match(r"(.*?)/(mod|course|my|pluginfile\.php|login)(/|$)", u.path)
        base = f"{u.scheme}://{u.netloc}{m.group(1) if m else ''}"
    return f"{base}/login/index.php"


def login(page, usuario: str, clave: str, url_destino: str, log=print) -> None:
    """Completa el formulario de Moodle (#username / #password / #loginbtn)."""
    if not hay_formulario_login(page):
        page.goto(url_login(url_destino), wait_until="load")
        _esperar_red(page)
    if not usuario or not clave:
        raise RuntimeError("Faltan usuario y contraseña: completá MOODLE_USER y MOODLE_PASS en el .env.")
    log("Iniciando sesión...")
    page.fill("#username", usuario)
    page.fill("#password", clave)
    page.click("#loginbtn")
    page.wait_for_load_state("load")
    _esperar_red(page)
    if "login/index.php" in page.url and hay_formulario_login(page):
        raise RuntimeError("El login falló (seguimos en la página de acceso). Revisá usuario y contraseña.")
    aceptar_cookies(page)


def sesion_caida(page) -> bool:
    """Las dos señales de sesión vencida: el cartel 'La sesión expiró' o el link 'Acceder'."""
    try:
        if page.locator("text=La sesión expiró").is_visible():
            try:
                page.get_by_role("button", name="Autenticarse nuevamente", exact=False).click()
                page.wait_for_timeout(500)
            except Exception:  # noqa: BLE001
                pass
            return True
    except Exception:  # noqa: BLE001
        pass
    return hay_formulario_login(page) or page.locator("a:text-is('Acceder')").count() > 0


def abrir_con_sesion(page, url: str, usuario: str, clave: str, log=print) -> None:
    """Va a `url`; si Moodle pide login, se loguea y vuelve a `url`."""
    log(f"Abriendo: {url}")
    page.goto(url, wait_until="load")
    _esperar_red(page)
    aceptar_cookies(page)
    if sesion_caida(page):
        login(page, usuario, clave, url, log)
        page.goto(url, wait_until="load")
        _esperar_red(page)
        aceptar_cookies(page)
        if sesion_caida(page):
            raise RuntimeError("No pude entrar a la página con ese usuario (¿tenés acceso a ese curso?).")


# ---------------------------------------------------------------------------
# Buscar las presentaciones
# ---------------------------------------------------------------------------

def id_presentacion(url: str) -> str:
    m = re.search(r"/presentation/d/(?:e/)?([^/?#]+)", url)
    return m.group(1) if m else url


def url_embed(url: str) -> str:
    """Normaliza el link al modo 'embed' de Google Slides, sin autoplay ni loop
    (con loop=true la última flecha volvería a la primera y no terminaría nunca)."""
    u = urlparse(url)
    path = u.path
    if "/embed" not in path:
        path = re.sub(r"/(edit|preview|present|pub|view)[^/]*$", "", path.rstrip("/")) + "/embed"
    q = dict(parse_qsl(u.query))
    q.update({"start": "false", "loop": "false"})
    q.pop("delayms", None)
    return urlunparse(u._replace(path=path, query=urlencode(q), fragment=""))


def buscar_presentaciones(page, patron=PATRON_SLIDES) -> list:
    """Todas las presentaciones incrustadas (en cualquier nivel de iframes), en el orden de la página."""
    vistos, salida = set(), []
    urls = []
    for frame in page.frames:
        try:   # el src de cada iframe (aunque todavía no haya cargado) ...
            urls += frame.eval_on_selector_all("iframe", "els => els.map(e => e.src || e.dataset.src || '')")
        except Exception:  # noqa: BLE001
            pass
        urls.append(frame.url)   # ... y la URL de los frames ya cargados
    for u in urls:
        if u and patron.search(u):
            clave = id_presentacion(u)
            if clave not in vistos:
                vistos.add(clave)
                salida.append(u)
    return salida


# ---------------------------------------------------------------------------
# Capturar diapositivas
# ---------------------------------------------------------------------------

def captura_estable(page, max_ms: int = ESPERA_MAX_MS) -> bytes:
    """Saca capturas seguidas hasta que dos consecutivas salen IDÉNTICAS (la diapositiva
    terminó de dibujarse / la transición terminó). Si nunca se asienta, sigue con la última."""
    actual = page.screenshot(full_page=False)
    t = 0
    while t < max_ms:
        page.wait_for_timeout(INTERVALO_MS)
        t += INTERVALO_MS
        previa, actual = actual, page.screenshot(full_page=False)
        if actual == previa:
            break
    return actual


def capturar_presentacion(context, url: str, carpeta: Path, prefijo: str, log=print, normalizar=True) -> list:
    """Abre la presentación en una pestaña aparte y saca una captura por diapositiva, avanzando con →.
    Termina cuando la flecha ya no cambia nada (última diapositiva)."""
    pagina = context.new_page()
    pagina.set_viewport_size(VIEWPORT)
    try:
        pagina.goto(url_embed(url) if normalizar else url, wait_until="load")
        _esperar_red(pagina, 15000)
        pagina.bring_to_front()   # foco para las flechas; NO clickeamos: un click avanza de diapositiva
        rutas, previo = [], None
        for i in range(1, MAX_SLIDES + 1):
            png = captura_estable(pagina)
            h = hashlib.sha256(png).hexdigest()
            if h == previo:
                break
            ruta = carpeta / f"{prefijo}_{i:03d}.png"
            ruta.write_bytes(png)
            rutas.append(ruta)
            previo = h
            if i % 5 == 0:
                log(f"   ... {i} diapositivas")
            pagina.keyboard.press("ArrowRight")
        return rutas
    finally:
        pagina.close()


# ---------------------------------------------------------------------------
# Armar el documento
# ---------------------------------------------------------------------------

def armar_pdf(imagenes: list, destino: Path) -> None:
    from PIL import Image
    imgs = [Image.open(p).convert("RGB") for p in imagenes]
    imgs[0].save(destino, save_all=True, append_images=imgs[1:], resolution=96)


def armar_pptx(imagenes: list, destino: Path) -> None:
    from PIL import Image
    from pptx import Presentation
    from pptx.util import Emu
    ancho, alto = Image.open(imagenes[0]).size
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(ancho * 9525), Emu(alto * 9525)   # 96 dpi
    for p in imagenes:
        diapo = prs.slides.add_slide(prs.slide_layouts[6])
        diapo.shapes.add_picture(str(p), 0, 0, width=prs.slide_width, height=prs.slide_height)
    prs.save(destino)


def nombre_archivo(texto: str) -> str:
    texto = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", texto or "").strip(" .-")
    texto = re.sub(r"\s+", " ", texto)
    return texto[:90] or f"presentaciones {datetime.now():%Y-%m-%d %H-%M}"


# ---------------------------------------------------------------------------
# Proceso completo
# ---------------------------------------------------------------------------

def extraer(url: str, salida: Path = SALIDA_DEFAULT, nombre: str = "", ver: bool = False,
            usuario: str = "", clave: str = "", formatos=("pdf", "pptx"), log=print,
            patron=PATRON_SLIDES) -> dict:
    """Hace todo. Devuelve {"archivos": [...], "presentaciones": N, "diapositivas": N}."""
    from playwright.sync_api import sync_playwright
    usuario = usuario or os.environ.get("MOODLE_USER", "")
    clave = clave or os.environ.get("MOODLE_PASS", "")
    salida = Path(salida).expanduser()
    salida.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p, tempfile.TemporaryDirectory(prefix="slides_") as tmp:
        navegador = p.chromium.launch(headless=not ver)
        try:
            context = navegador.new_context(viewport=VIEWPORT)
            page = context.new_page()
            abrir_con_sesion(page, url, usuario, clave, log)
            page.wait_for_timeout(1500)   # iframes que se cargan tarde
            titulo = nombre or page.title()
            presentaciones = buscar_presentaciones(page, patron)
            if not presentaciones:
                log("❌ No encontré presentaciones de Google Slides incrustadas en esa página.")
                return {"archivos": [], "presentaciones": 0, "diapositivas": 0}
            log(f"Encontré {len(presentaciones)} presentación(es).")
            imagenes = []
            for n, pres in enumerate(presentaciones, 1):
                log(f"\n▶ Presentación {n}/{len(presentaciones)}")
                rutas = capturar_presentacion(context, pres, Path(tmp), f"p{n:02d}", log,
                                              normalizar=patron is PATRON_SLIDES)
                log(f"   ✅ {len(rutas)} diapositiva(s)")
                imagenes += rutas
        finally:
            navegador.close()

        if not imagenes:
            log("❌ Las presentaciones no tenían diapositivas visibles.")
            return {"archivos": [], "presentaciones": len(presentaciones), "diapositivas": 0}
        base = salida / nombre_archivo(titulo)
        archivos = []
        if "pdf" in formatos:
            armar_pdf(imagenes, base.with_suffix(".pdf"))
            archivos.append(str(base.with_suffix(".pdf")))
        if "pptx" in formatos:
            armar_pptx(imagenes, base.with_suffix(".pptx"))
            archivos.append(str(base.with_suffix(".pptx")))
        # las capturas sueltas se borran con la carpeta temporal: ya están dentro del PDF/PPTX
    for a in archivos:
        log(f"📄 {a}")
    log(f"\n=== {len(imagenes)} diapositiva(s) de {len(presentaciones)} presentación(es) en un solo documento ===")
    return {"archivos": archivos, "presentaciones": len(presentaciones), "diapositivas": len(imagenes)}


def cargar_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE / ".env")
    except ImportError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Junta en un PDF/PPTX las presentaciones incrustadas en una página de Moodle.")
    ap.add_argument("url", nargs="?", help="link de la página del aula (si no, lo pregunta)")
    ap.add_argument("--nombre", default="", help="nombre del documento (por defecto, el título de la página)")
    ap.add_argument("--salida", default=str(SALIDA_DEFAULT), help="carpeta donde guardar el documento")
    ap.add_argument("--solo", choices=["pdf", "pptx"], help="generar solo un formato")
    ap.add_argument("--ver", action="store_true", help="mostrar el navegador mientras trabaja")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = ap.parse_args()
    cargar_env()
    url = args.url or input("Pegá el link de la página del aula: ").strip()
    if not url.startswith("http"):
        print("❌ El link tiene que empezar con http:// o https://")
        return 1
    try:
        r = extraer(url, Path(args.salida), args.nombre, args.ver,
                    formatos=(args.solo,) if args.solo else ("pdf", "pptx"))
    except Exception as e:  # noqa: BLE001
        print(f"❌ {e}")
        return 1
    return 0 if r["archivos"] else 1


if __name__ == "__main__":
    sys.exit(main())
