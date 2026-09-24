# cvuex-mcp

Servidor MCP para el Campus Virtual de la Universidad de Extremadura, centrado en el alumnado: trabaja con **AVUEx** (aulas regladas). Usa la sesión del propio alumno mediante el mismo inicio de sesión SSO que la app oficial de Moodle: la contraseña nunca pasa por este programa.

**Solo lectura:** el servidor únicamente puede llamar a una lista cerrada de funciones de consulta de Moodle, nunca a las que modifican datos ni a las que registran accesos.

Estado: F1 completada. Ver [PLAN.md](PLAN.md) y [FASE1.md](FASE1.md).

## Herramientas

| Herramienta | Para qué |
|---|---|
| `mis_asignaturas` | Asignaturas en curso, pasadas o futuras, con su id |
| `proximos_plazos` | Entregas, aperturas y cierres de actividades y eventos del calendario, por fecha |
| `estado_entregas` | Tareas sin entregar, en borrador o entregadas, con nota y comentarios del profesor |
| `novedades` | Qué ha cambiado en las asignaturas desde la última consulta (o en las últimas N horas) |
| `notificaciones` | Notificaciones del campus; consultarlas no las marca como leídas |
| `quien_soy` | Con qué cuenta está conectado el servidor |

## Instalación

Requiere [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run playwright install chromium   # navegador para el login (una sola vez)
```

## Uso

```bash
uv run cvuex-mcp login     # abre el navegador: inicia sesión con tu cuenta UEx
uv run cvuex-mcp whoami    # comprueba la sesión (--functions lista la API disponible)
uv run cvuex-mcp logout    # borra la sesión de este equipo
```

Los ficheros se guardan en la carpeta de configuración del usuario (`~/.config/cvuex-mcp` en Linux, `~/Library/Application Support/cvuex-mcp` en macOS, `%LOCALAPPDATA%\cvuex-mcp` en Windows); se puede cambiar con `CVUEX_MCP_HOME`:

- `credentials.json`: el token de la sesión. **Da acceso a tu cuenta: no compartas este fichero.**
- `state.json`: la fecha de la última consulta de `novedades`.

## Conectarlo a un cliente MCP

El servidor se arranca con `uv --directory /ruta/a/cvuex-mcp run cvuex-mcp serve` (stdio). Tras cambiar el código, reinicia el cliente MCP; tras un nuevo `login`, no hace falta.

**opencode** (`~/.config/opencode/opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "cvuex": {
      "type": "local",
      "command": ["uv", "--directory", "/ruta/a/cvuex-mcp", "run", "cvuex-mcp", "serve"],
      "enabled": true,
      "timeout": 15000
    }
  }
}
```

**Claude Code:**

```bash
claude mcp add cvuex -- uv --directory /ruta/a/cvuex-mcp run cvuex-mcp serve
```

## Desarrollo

```bash
uv run pytest            # tests (los marcados "browser" usan Chromium)
uv run ruff check . && uv run ruff format .
```

Estructura de `src/cvuex_mcp/`:

| Módulo | Responsabilidad |
|---|---|
| `server.py` | Instrucciones del servidor y registro de las herramientas |
| `tools/` | Herramientas MCP, un módulo por área. Cada función se llama como la herramienta |
| `runtime.py` | Estado compartido entre llamadas y acceso de una herramienta al campus (`campus_session`) |
| `campus/core.py` | `Campus`: única puerta a Moodle (funciones permitidas, caché), alumno y asignaturas |
| `campus/allowlist.py` | Funciones de Moodle permitidas y su caché: **lo primero que hay que auditar** |
| `campus/<área>.py` | Consulta y conversión de datos de cada área (plazos, entregas, novedades…) |
| `models.py` | Lo que devuelven las herramientas |
| `formatting.py` | Fechas, textos y enlaces |
| `moodle.py` | Cliente REST de Moodle |
| `auth.py` · `credentials.py` · `session.py` | Login SSO y sesión guardada |
| `cache.py` · `rate_limit.py` · `state.py` · `storage.py` | Infraestructura |

**Añadir una herramienta:**
1. Añadir las funciones de Moodle a `campus/allowlist.py`, tras comprobar en su código que no tienen efectos secundarios.
2. Escribir la lógica en `campus/<área>.py`.
3. Definir el modelo de salida en `models.py`.
4. Crear la herramienta en `tools/<área>.py` con su `register` y añadir el módulo a `tools/__init__.py`.
5. Mencionarla en `INSTRUCTIONS`; un test lo exige.

**Fixtures de test:** `scripts/moodle_fixtures.py explorar` guarda respuestas reales en `fixtures/raw/` (fuera de git) y `anonimizar` las convierte en fixtures para `tests/fixtures/`. **Revisa siempre a mano el resultado:** el anonimizador no detecta nombres dentro de textos libres.
