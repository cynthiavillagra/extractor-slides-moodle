"""
Interfaz web del extractor de presentaciones de Moodle.

    python app.py            -> abre http://127.0.0.1:5056 en el navegador

Corre solo en tu PC (127.0.0.1): nadie de afuera puede entrar.
"""
import os
import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file

import extractor as ex

ex.cargar_env()
PUERTO = int(os.environ.get("PUERTO", "5056"))
app = Flask(__name__)

estado = {"corriendo": False, "log": [], "resultado": None}
candado = threading.Lock()


def _log(msg) -> None:
    print(msg, flush=True)
    estado["log"].append(str(msg))
    del estado["log"][:-2000]


@app.get("/")
def inicio():
    return render_template("index.html", salida=str(ex.SALIDA_DEFAULT),
                           hay_credenciales=bool(os.environ.get("MOODLE_USER") and os.environ.get("MOODLE_PASS")),
                           usuario_env=os.environ.get("MOODLE_USER", ""),
                           moodle_url=os.environ.get("MOODLE_URL", ""))


@app.post("/extraer")
def extraer():
    d = request.get_json(force=True)
    url = (d.get("url") or "").strip()
    if not url.startswith("http"):
        return jsonify({"ok": False, "error": "Pegá el link completo de la página (https://...)."}), 400
    with candado:
        if estado["corriendo"]:
            return jsonify({"ok": False, "error": "Ya hay una extracción en curso."}), 409
        estado.update(corriendo=True, log=[], resultado=None)

    formatos = tuple(f for f in ("pdf", "pptx") if d.get(f, True)) or ("pdf",)

    def trabajo():
        try:
            estado["resultado"] = ex.extraer(
                url, Path(d.get("salida") or ex.SALIDA_DEFAULT), d.get("nombre", ""), bool(d.get("ver")),
                d.get("usuario", ""), d.get("clave", ""), formatos, _log)
        except Exception as e:  # noqa: BLE001
            _log(f"❌ {e}")
        finally:
            estado["corriendo"] = False

    threading.Thread(target=trabajo, daemon=True).start()
    return jsonify({"ok": True})


ENV = ex.BASE / ".env"
CLAVES_ENV = ("MOODLE_USER", "MOODLE_PASS", "MOODLE_URL")


def guardar_env(valores: dict) -> None:
    """Escribe/actualiza esas variables en .env sin tocar las demás líneas (comentarios, PUERTO, etc.)."""
    lineas = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    # entre comillas dobles y con escape: así una contraseña con #, espacios, comillas o \ se lee tal cual
    pendientes = {k: '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"' for k, v in valores.items()}
    for i, linea in enumerate(lineas):
        clave = linea.split("=", 1)[0].strip().lstrip("#").strip()
        if clave in pendientes and "=" in linea:
            lineas[i] = f"{clave}={pendientes.pop(clave)}"
    lineas += [f"{k}={v}" for k, v in pendientes.items()]
    ENV.write_text("\n".join(lineas) + "\n", encoding="utf-8")


@app.post("/credenciales")
def credenciales():
    """Guarda usuario/contraseña (y opcionalmente la dirección del aula) en el .env de esta PC."""
    d = request.get_json(force=True)
    usuario, clave, url = (d.get("usuario") or "").strip(), d.get("clave") or "", (d.get("moodle_url") or "").strip()
    if not usuario or not clave:
        return jsonify({"ok": False, "error": "Completá usuario y contraseña."}), 400
    if any(c in usuario + clave + url for c in "\r\n"):
        return jsonify({"ok": False, "error": "Usuario o contraseña con saltos de línea."}), 400
    valores = {"MOODLE_USER": usuario, "MOODLE_PASS": clave}
    if url:
        valores["MOODLE_URL"] = url.rstrip("/")
    guardar_env(valores)
    os.environ.update(valores)
    return jsonify({"ok": True, "usuario": usuario})


@app.get("/estado")
def ver_estado():
    desde = int(request.args.get("desde", 0))
    return jsonify({"corriendo": estado["corriendo"], "log": estado["log"][desde:],
                    "total": len(estado["log"]), "resultado": estado["resultado"]})


@app.get("/archivo")
def archivo():
    """Descarga/abre un documento generado (solo .pdf o .pptx)."""
    p = Path(request.args.get("ruta", ""))
    if p.suffix.lower() not in (".pdf", ".pptx") or not p.is_file():
        abort(404)
    return send_file(p, as_attachment=p.suffix.lower() == ".pptx")


@app.get("/elegir")
def elegir():
    """Selector de carpeta del sistema (la app corre en tu PC)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        raiz = tk.Tk()
        raiz.withdraw()
        raiz.attributes("-topmost", True)
        ruta = filedialog.askdirectory(title="Elegí la carpeta")
        raiz.destroy()
    except Exception as e:  # noqa: BLE001
        return jsonify({"ruta": "", "error": f"No se pudo abrir el selector ({e}): escribí la ruta a mano."})
    return jsonify({"ruta": str(Path(ruta)) if ruta else "", "error": ""})


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    url = f"http://127.0.0.1:{PUERTO}"
    print(f"Extractor de slides en {url}  (Ctrl+C para cerrar)")
    if "--no-abrir" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=PUERTO, debug=False, threaded=True)
