# Extractor de presentaciones de Moodle

Entra a tu aula virtual **Moodle** con tu usuario y contraseña (usando [Playwright](https://playwright.dev/python/)),
abre la página que le indiques, busca **todas las presentaciones de Google Slides incrustadas**, saca una captura de
cada diapositiva y las junta en **un solo documento** (PDF y/o PPTX).

Sirve para tener las clases del campus en un archivo para leer, imprimir o subir a NotebookLM.

## Qué hace

1. Abre el link. Si Moodle pide iniciar sesión, completa usuario y contraseña (`#username` / `#password`, el formulario
   estándar de Moodle) y vuelve a la página. También acepta el cartel de cookies («Preferencias de datos») y se vuelve a
   loguear si aparece «La sesión expiró».
2. Busca las presentaciones en la página **y dentro de los iframes** (también las que están anidadas). Si la misma
   presentación aparece dos veces, la toma una sola vez.
3. Abre cada una en modo *embed* (sin autoplay ni loop) y va avanzando con la flecha →. Antes de cada captura espera a que
   la diapositiva termine de dibujarse (compara capturas seguidas hasta que dos salen iguales). Termina cuando la flecha
   ya no cambia nada.
4. Junta todas las capturas, en el orden de la página, en `<nombre>.pdf` y `<nombre>.pptx`. Las imágenes sueltas se
   borran solas.

El nombre del documento, por defecto, es el título de la página del aula.

## Requisitos

- **Python 3.10 a 3.12** (en Windows: instalador de [python.org](https://www.python.org/downloads/), tildando
  *Add python.exe to PATH*).
- Un usuario del aula con acceso a esa página.

## Instalación con entorno virtual (venv)

### Windows (PowerShell)

```powershell
git clone https://github.com/cynthiavillagra/extractor-slides-moodle.git
cd extractor-slides-moodle

py -3 -m venv .venv                     # crea el entorno virtual (o: python -m venv .venv)
.\.venv\Scripts\Activate.ps1            # lo activa: el prompt empieza con (.venv)
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium   # descarga el navegador que usa Playwright (una sola vez)
```

> Si PowerShell dice que *la ejecución de scripts está deshabilitada*, corré una sola vez
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y volvé a activar.
> En el CMD clásico se activa con `.venv\Scripts\activate.bat`.

### Linux / macOS

```bash
git clone https://github.com/cynthiavillagra/extractor-slides-moodle.git
cd extractor-slides-moodle

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium   # en Linux puede pedir: python -m playwright install-deps
```

### Atajo

`iniciar.bat` (Windows, doble clic) o `./iniciar.sh` (Linux/macOS) hacen todo lo de arriba la primera vez
(venv + dependencias + navegador) y después abren la interfaz, donde cargás tu usuario y contraseña.

## Usuario y contraseña

**La forma fácil: desde la interfaz web.** En la sección «Acceso» escribí usuario y contraseña y tocá
**Guardar en esta PC**. Se guardan en el archivo `.env` de la carpeta y la próxima vez ya aparecen cargados
(«✔ Guardado en esta PC: …»). Desde ahí mismo los podés cambiar cuando quieras.

**A mano**, si preferís: copiá `.env.example` como `.env` (`copy .env.example .env` en Windows,
`cp .env.example .env` en Linux/macOS) y completalo:

```ini
MOODLE_USER=tu_usuario_o_dni
MOODLE_PASS=tu_contraseña
# MOODLE_URL=https://campus.udelaciudad.edu.ar   (opcional)
```

- `MOODLE_URL` es opcional: si no está, el login se busca en el mismo sitio del link que pegás
  (también funciona con Moodle instalado en una subcarpeta, ej. `https://sitio/campus/...`).
- El `.env` está en `.gitignore`: **nunca se sube a GitHub**. Guardá una copia en un lugar seguro
  (por ejemplo tu Drive) para usarlo en otra PC.
- El `.env` es texto plano: queda solo en tu PC, no lo compartas.
- Si escribís usuario y contraseña en la interfaz **sin** tocar «Guardar», se usan solo para esa extracción.

## Uso

### Interfaz web

Con el venv activado:

```bash
python app.py
```

Se abre el navegador en `http://127.0.0.1:5056`. Pegá el link de la página del aula (curso, sección o actividad),
opcionalmente un nombre para el documento, elegí la carpeta de salida y **Extraer presentaciones**. El progreso se ve en
pantalla y al final aparecen los links al PDF y al PPTX.

«Mostrar el navegador mientras trabaja» abre Chromium a la vista (sirve para ver qué está pasando si algo falla).

Para cerrar: `Ctrl+C` en la consola. Para salir del venv: `deactivate`.

### Consola

```bash
python extractor.py "https://campus.ejemplo.edu.ar/mod/page/view.php?id=12345"
python extractor.py URL --nombre "Clase 3 - Didáctica" --salida "D:\Slides"
python extractor.py URL --solo pdf
python extractor.py URL --ver            # muestra el navegador
```

Sin URL, la pregunta por consola. `python extractor.py -h` muestra todas las opciones.

## Límites

- Toma **presentaciones de Google Slides** (`docs.google.com/presentation`), que es como suelen incrustarse en Moodle.
  Un PowerPoint subido como archivo no hace falta capturarlo: se descarga directo desde el aula.
- Las diapositivas quedan como **imágenes** (no texto editable). Para buscar texto, pasá el PDF por OCR o subilo a
  NotebookLM, que lo lee igual.
- Las animaciones dentro de una diapositiva se capturan como pasos separados si Google Slides las muestra así.
- Si la presentación no es pública y tu cuenta de Google no tiene acceso, Google muestra «Solicitar acceso» en vez de las
  diapositivas: el navegador de Playwright no tiene tu sesión de Google.

## Estructura

```
app.py              interfaz web (Flask, solo en 127.0.0.1)
extractor.py        login en Moodle + búsqueda de presentaciones + captura + PDF/PPTX (también por consola)
templates/          página de la interfaz
iniciar.bat / .sh   primera instalación y arranque
.env.example        modelo del .env (MOODLE_USER, MOODLE_PASS, MOODLE_URL, PUERTO)
salida/             carpeta de salida por defecto (no se sube a GitHub)
```

## Privacidad

El material de las cátedras es de cada aula: `salida/` está en `.gitignore` para que los documentos no terminen en el
repo por error. Usá la herramienta solo con aulas a las que tengas acceso.

## Origen

Extraído del scraper de UNICABA (`extract_ppts.py` + el login de `moodle_common.py`), sin el resto del crawler ni la
subida a Drive. Se le agregó que tome todas las presentaciones de la página y las junte en un solo documento.

Licencia MIT.
