# Desarrollo de cvuex-mcp

## Puesta en marcha

```bash
uv sync
uv run playwright install chromium   # solo para los tests marcados "browser"
uv run pytest
uv run ruff check . && uv run ruff format .
```

GitHub Actions (`.github/workflows/tests.yml`) pasa ruff y los tests en Linux, macOS y Windows en cada push a `main` y en cada pull request.

Para probar tu copia en un cliente MCP, configúralo con `uv --directory /ruta/a/cvuex-mcp run cvuex-mcp serve` en lugar del `uvx` del README. Reinicia el cliente tras cada cambio de código; tras un `login`, no hace falta.

## Principios

- **Solo lectura frente al campus.** Solo se llama a las funciones de Moodle de `campus/allowlist.py`, que es lo primero que hay que auditar. Nunca a las que modifican datos ni a las `*_view_*`, que registran accesos y pueden completar actividades. Única excepción: `mod_forum_get_discussion_posts` marca los mensajes como leídos si el alumno sigue el foro.
- **Local:** un servidor por alumno con su propio token, el de la app oficial de Moodle. No hay servidor central.
- **El token nunca se registra:** los logs de `httpx` están silenciados y las descargas lo envían en el cuerpo de la petición.
- **Peticiones espaciadas y en caché:** el campus corta las conexiones si recibe demasiadas seguidas.
- **Tareas largas en segundo plano** (descargas, índice de los foros): la herramienta devuelve el progreso a los pocos segundos, porque los clientes cortan las llamadas largas (opencode, a los 15 s).

## Estructura de `src/cvuex_mcp/`

| Módulo | Responsabilidad |
|---|---|
| `server.py` · `prompts.py` | Instrucciones del servidor, registro de herramientas y prompts |
| `tools/` | Herramientas MCP, un módulo por área; cada función se llama como su herramienta |
| `runtime.py` | Estado compartido, anotaciones y acceso de una herramienta al campus (`campus_session`) |
| `campus/core.py` | `Campus`: única puerta a Moodle (lista de funciones permitidas, caché), alumno y asignaturas |
| `campus/allowlist.py` | Funciones de Moodle permitidas y su caché |
| `campus/<área>.py` | Consulta y conversión de los datos de cada área |
| `materials/` | Descarga, registro, extracción de texto, índice y búsqueda de los materiales |
| `forum_search/` | Índice local de los foros y su búsqueda |
| `calendar_export.py` | Los plazos como `.ics` |
| `fulltext.py` · `jobs.py` | Consultas FTS5 comunes a ambos índices y tareas en segundo plano |
| `models.py` | Lo que devuelven las herramientas |
| `formatting.py` · `question_html.py` | Fechas, textos y enlaces; lectura del HTML de las preguntas de cuestionario |
| `moodle.py` | Cliente REST de Moodle y descargas |
| `auth.py` · `credentials.py` · `session.py` | Login SSO y sesión guardada |
| `cache.py` · `rate_limit.py` · `state.py` · `storage.py` | Infraestructura |

**Login** (`auth.py`): abre Chrome o Edge si están instalados, siempre con un perfil nuevo; si no, descarga la primera vez el Chromium de Playwright sin la versión headless (unos 400 MB).

## Añadir una herramienta

1. Comprobar en el código de Moodle que sus funciones no tienen efectos secundarios y añadirlas a `campus/allowlist.py`.
2. Escribir la lógica en `campus/<área>.py` y el modelo de salida en `models.py`.
3. Crear la herramienta en `tools/<área>.py` con su `register` y añadir el módulo a `tools/__init__.py`.
4. Mencionarla en `INSTRUCTIONS` (`server.py`); un test lo exige.

## Fixtures de test

```bash
uv run scripts/moodle_fixtures.py explorar core_course_get_contents courseid=1234   # a fixtures/raw/, fuera de git
uv run scripts/moodle_fixtures.py anonimizar fixtures/raw/avuex/<fichero>.json     # a tests/fixtures/
```

**Revisa a mano cada fixture antes de hacer commit:** el anonimizador trabaja por nombre de campo y no detecta nombres dentro de textos libres.

## Dónde guarda cada cosa

- **`Documentos/CVUEx`**, o la carpeta que indique `CVUEX_MCP_MATERIALES`: los materiales (hasta 100 MB por fichero) y `calendario.ics`.
- **Carpeta de configuración** (`~/.config/cvuex-mcp`, `~/Library/Application Support/cvuex-mcp` o `%LOCALAPPDATA%\cvuex-mcp`), o la que indique `CVUEX_MCP_HOME`:
  - `credentials.json`: el token, con permisos 0600.
  - `state.json`: la última consulta de `novedades`.
  - `materiales.sqlite`: el registro de descargas y el índice de los materiales.
  - `foros.sqlite`: el índice de los foros, con mensajes de otros alumnos. Es local porque la búsqueda global de Moodle está desactivada en el campus.