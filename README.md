# cvuex-mcp

Servidor MCP para el Campus Virtual de la Universidad de Extremadura, centrado en el alumnado: trabaja con **AVUEx** (aulas regladas). Usa la sesión del propio alumno mediante el mismo inicio de sesión SSO que la app oficial de Moodle: la contraseña nunca pasa por este programa.

**Integridad académica:** no hay herramientas para intentos de cuestionario en curso ni para entregar nada; solo se revisa lo que Moodle ya deja revisar al alumno.

**Solo lectura:** el servidor no escribe, envía ni rellena nada en tu nombre: ni mensajes, ni foros, ni entregas. Únicamente puede llamar a una lista cerrada de funciones de consulta de Moodle, nunca a las que modifican datos ni a las que registran accesos. Las únicas excepciones son `leer_debate` y `buscar_en_foros`: si tienes activado el seguimiento de mensajes no leídos en un foro, Moodle marca como leídos los mensajes que leen, igual que al abrirlos en el navegador. `sincronizar_materiales` y `exportar_calendario` escriben, pero solo en tu equipo.

Estado: F1 a F4 implementadas; faltan las pruebas finales de la F2, la F3 y la F4 en opencode, y `simular_nota` está pospuesta hasta que haya notas reales. Ver [PLAN.md](PLAN.md) y el detalle de cada fase: [FASE1.md](FASE1.md), [FASE2.md](FASE2.md), [FASE3.md](FASE3.md) y [FASE4.md](FASE4.md).

## Herramientas

| Herramienta | Para qué |
|---|---|
| `mis_asignaturas` | Asignaturas en curso, pasadas o futuras, con su id |
| `contenido_asignatura` | Temas de una asignatura con sus materiales y actividades, fechas y restricciones |
| `contacto_profesorado` | Profesores de cada asignatura, con su correo y lo que pongan en su perfil (a veces, las tutorías) |
| `quien_soy` | Con qué cuenta está conectado el servidor |
| **¿Qué tengo que hacer?** | |
| `proximos_plazos` | Entregas, aperturas y cierres de actividades y eventos del calendario, por fecha |
| `estado_entregas` | Tareas sin entregar, en borrador o entregadas, con nota y comentarios del profesor |
| `exportar_calendario` | Guarda los próximos plazos en un fichero `.ics` para importarlo en Google Calendar u Outlook |
| **¿Cómo voy?** | |
| `calificaciones` | Nota total de cada asignatura o, de una, el detalle por actividad y categoría. No son las notas oficiales del acta (Secretaría Virtual) |
| `cuestionarios` | Cuestionarios con sus fechas y los intentos terminados, con su nota |
| `revisar_cuestionario` | Preguntas de un intento terminado con la corrección, según lo que el profesor deja revisar |
| **¿Qué hay de nuevo?** | |
| `avisos` | Anuncios de los profesores y debates de los foros generales, con el comienzo del mensaje |
| `leer_debate` | Un debate completo con sus respuestas; puede marcarlos como leídos (ver arriba) |
| `buscar_en_foros` | "¿Alguien preguntó ya por esto?": busca en los mensajes y respuestas de los foros |
| `novedades` | Qué ha cambiado en las asignaturas desde la última consulta (o en las últimas N horas) |
| `notificaciones` | Notificaciones del campus; consultarlas no las marca como leídas |
| **Ayúdame con el temario** | |
| `sincronizar_materiales` | Descarga a tu equipo los materiales nuevos o modificados, en segundo plano, y los indexa |
| `buscar_en_materiales` | En qué documento y página aparece un concepto, sin consultar el campus |
| `leer_material` | El texto de esas páginas, para explicar según los apuntes y citarlos |

## Prompts

Peticiones ya preparadas, que en opencode aparecen como comandos (`/cvuex:resumen_semanal`…). Le dicen al asistente qué herramientas usar y cómo presentar el resultado:

| Prompt | Para qué |
|---|---|
| `resumen_semanal` | Plan de la semana por días: plazos, entregas pendientes y avisos. Ofrece pasar los plazos al calendario |
| `preparar_examen(asignatura, tema)` | Esquema, preguntas de repaso y tarjetas a partir de los apuntes, citando documento y página |
| `ponerme_al_dia(asignatura)` | Qué se ha publicado y avisado, qué toca ahora y qué falta por hacer |

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
uv run cvuex-mcp sincronizar [--asignatura ID]   # descarga los materiales nuevos o modificados
uv run cvuex-mcp calendario [--dias N] [--asignatura ID]   # guarda los próximos plazos en un .ics
```

Los ficheros se guardan en la carpeta de configuración del usuario (`~/.config/cvuex-mcp` en Linux, `~/Library/Application Support/cvuex-mcp` en macOS, `%LOCALAPPDATA%\cvuex-mcp` en Windows); se puede cambiar con `CVUEX_MCP_HOME`:

- `credentials.json`: el token de la sesión. **Da acceso a tu cuenta: no compartas este fichero.**
- `state.json`: la fecha de la última consulta de `novedades`.
- `materiales.sqlite`: qué materiales se han descargado y de dónde, y el índice para buscar en ellos.
- `foros.sqlite`: el índice de los foros para `buscar_en_foros` (la búsqueda global del campus está desactivada). Se pone al día al buscar, si tiene más de 10 minutos. Contiene mensajes de tus compañeros: como los materiales, es solo para tu uso.

**Materiales:** se descargan en `Documentos/CVUEx` (se puede cambiar con `CVUEX_MCP_MATERIALES`), por asignatura y sección. Solo se descarga lo nuevo o modificado, hasta 100 MB por fichero. Si el profesor quita un fichero del campus, la copia local se conserva, y nada que pongas tú en la carpeta se sobrescribe. **Son para tu estudio personal: la normativa del Campus Virtual prohíbe redistribuirlos.** Ten en cuenta que lo que el asistente lea de ellos llega al proveedor del modelo que uses, y que descargarlos no cuenta como haberlos visto en Moodle.

**Calendario:** `exportar_calendario` y `cvuex-mcp calendario` guardan `calendario.ics` en esa misma carpeta, con lo que viene en los próximos días (90 por defecto; lo vencido no entra). Es una copia: si cambian los plazos, vuelve a exportarlo e importarlo. No se usa el enlace de suscripción de Moodle, porque da acceso a tu calendario sin iniciar sesión y, al entrar por SSO, no puedes revocarlo.

**Búsqueda:** se indexa el texto de los PDF (por páginas), PowerPoint (por diapositivas), Word, páginas y libros de Moodle, TXT y Markdown (por apartados). Busca palabras, sin tener en cuenta tildes ni mayúsculas, no significados. No se pueden buscar los PDF escaneados (no hay OCR) ni los formatos antiguos `.doc`/`.ppt`: la sincronización los avisa para que los abras tú.

## Conectarlo a un cliente MCP

El servidor se arranca con `uv --directory /ruta/a/cvuex-mcp run cvuex-mcp serve` (stdio). Tras cambiar el código, reinicia el cliente MCP; tras un nuevo `login`, no hace falta. Las tareas largas (descargar materiales, indexar los foros) siguen en segundo plano, así que el límite de tiempo por llamada del cliente no las corta.

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
| `server.py` | Instrucciones del servidor y registro de las herramientas y los prompts |
| `prompts.py` | Los prompts |
| `tools/` | Herramientas MCP, un módulo por área. Cada función se llama como la herramienta |
| `runtime.py` | Estado compartido entre llamadas y acceso de una herramienta al campus (`campus_session`) |
| `campus/core.py` | `Campus`: única puerta a Moodle (funciones permitidas, caché), alumno y asignaturas |
| `campus/allowlist.py` | Funciones de Moodle permitidas y su caché: **lo primero que hay que auditar** |
| `campus/<área>.py` | Consulta y conversión de datos de cada área (plazos, entregas, novedades…) |
| `materials/` | Materiales: qué se descarga y dónde, registro, bloqueo, extracción de texto, índice y búsqueda |
| `forum_search/` | Índice local de los foros: actualización incremental desde el campus y búsqueda |
| `calendar_export.py` | Los plazos como fichero `.ics` |
| `fulltext.py` · `jobs.py` | Lo común a ambos índices (consulta FTS5) y las tareas en segundo plano |
| `models.py` | Lo que devuelven las herramientas |
| `formatting.py` | Fechas, textos y enlaces |
| `question_html.py` | Lectura de las preguntas de un cuestionario, que Moodle envía en HTML |
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
