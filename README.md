# cvuex-mcp

**Tu Campus Virtual de la UEx, dentro de tu asistente de IA.**

Conecta asistentes como Claude Code o Codex con tus aulas de **AVUEx** para que puedas preguntarles en lenguaje natural: *"¿qué tengo que entregar esta semana?"*, *"¿hay avisos nuevos?"* o *"explícame este concepto según los apuntes"*.

Funciona en tu equipo, con tu propia cuenta, y **solo consulta**: no envía, publica ni entrega nada por ti.

> IMPORTANTE: este proyecto no es oficial y no lo desarrolla ni lo respalda la Universidad de Extremadura.

## Qué puedes preguntarle

**¿Qué tengo que hacer?**
- "¿Qué tengo que entregar esta semana?"
- "¿Qué tareas me quedan por entregar?"
- "Pásame los plazos a Google Calendar."

**¿Cómo voy?**
- "¿Qué nota llevo en cada asignatura?"
- "Explícame los fallos de mi último cuestionario de Estadística."

**¿Qué hay de nuevo?**
- "¿Hay avisos nuevos de los profesores?"
- "¿Qué ha cambiado en el campus desde la última vez?"
- "¿Alguien ha preguntado ya en el foro por la práctica 2?"

**Ayúdame con el temario**
- "¿Qué hay en el tema 3 de Redes?"
- "Descárgate los apuntes de mis asignaturas."
- "¿Dónde explica el profesor el algoritmo de Dijkstra?"
- "Explícame la normalización según los apuntes." El asistente cita el documento y la página.

**Mis asignaturas y profesores**
- "¿Qué asignaturas tengo este curso?"
- "¿Quién da Programación y cómo le escribo?"

## Instalación

Necesitas [uv](https://docs.astral.sh/uv/getting-started/installation/), que se encarga también de instalar Python, y [git](https://git-scm.com/downloads). Funciona en Linux, macOS y Windows.

### Instalación rápida

Copia este mensaje en tu asistente (Claude Code, Codex, OpenCode u otro que admita servidores MCP) y te guiará por todo el proceso:

```text
Instala el servidor MCP cvuex-mcp (Campus Virtual de la UEx) en este asistente:
1. Comprueba que uv y git están instalados. Si falta alguno, dime cómo instalarlo
   en mi sistema y espera a que lo haga.
2. Ejecuta: uvx --from git+https://github.com/rdereparadores/cvuex-mcp cvuex-mcp login
   Abre el navegador para que inicie sesión con mi cuenta de la UEx y termina
   cuando lo haya hecho, lo que puede llevar unos minutos. Si no puedes esperar
   tanto, pídeme que lo ejecute yo en una terminal.
3. Ejecuta: uvx --from git+https://github.com/rdereparadores/cvuex-mcp cvuex-mcp whoami
   Debe mostrar mi nombre.
4. Configura en este asistente un servidor MCP local (stdio) llamado "cvuex":
   - Comando: uvx
   - Argumentos: --from git+https://github.com/rdereparadores/cvuex-mcp cvuex-mcp serve
   - No necesita variables de entorno ni claves: la sesión queda guardada en mi equipo.
   - Si hay un límite de tiempo por llamada, que sea de al menos 15 segundos.
   Busca en la documentación de este asistente cómo se añaden servidores MCP.
5. Dime si tengo que reiniciarte y, después, comprueba que funciona con su
   herramienta quien_soy.
```

### Instalación manual

1. Inicia sesión.

   ```bash
   uvx --from git+https://github.com/rdereparadores/cvuex-mcp cvuex-mcp login
   ```
   Se abrirá Google Chrome o Microsoft Edge para guardar tus credenciales.

2. Comprueba que funciona: debe mostrar tu nombre.

   ```bash
   uvx --from git+https://github.com/rdereparadores/cvuex-mcp cvuex-mcp whoami
   ```

3. Conéctalo a tu asistente con una de estas opciones. Después, reinicia el asistente y pregúntale *"¿Con qué cuenta del campus estás conectado?"* para comprobar que la configuración fue exitosa.

   **Claude Code**

   ```bash
   claude mcp add --scope user cvuex -- uvx --from git+https://github.com/rdereparadores/cvuex-mcp cvuex-mcp serve
   ```

   **Codex CLI**

   ```bash
   codex mcp add cvuex -- uvx --from git+https://github.com/rdereparadores/cvuex-mcp cvuex-mcp serve
   ```

   **OpenCode:** añade esto a `~/.config/opencode/opencode.json`:

   ```json
   {
     "$schema": "https://opencode.ai/config.json",
     "mcp": {
       "cvuex": {
         "type": "local",
         "command": ["uvx", "--from", "git+https://github.com/rdereparadores/cvuex-mcp", "cvuex-mcp", "serve"],
         "enabled": true,
         "timeout": 15000
       }
     }
   }
   ```

## Tus archivos

- **Apuntes:** se descargan en la carpeta `Documentos/CVUEx`, ordenados por asignatura y tema. Cada vez solo baja lo nuevo o lo que ha cambiado. Si el profesor quita un fichero del campus, conservas tu copia, y nunca toca lo que pongas tú en la carpeta.
- **Calendario:** `calendario.ics` se guarda en esa misma carpeta. Si cambian los plazos, vuelve a exportarlo.
- **Tu sesión** queda guardada en tu equipo y da acceso a tu cuenta del campus. Si usas un ordenador compartido, ciérrala con la orden `logout`.

## Órdenes de la terminal

Todas se escriben tras `uvx --from git+https://github.com/rdereparadores/cvuex-mcp cvuex-mcp`, como en la instalación.

| Orden | Para qué |
|---|---|
| `login` | Iniciar sesión con tu cuenta UEx |
| `whoami` | Comprobar con qué cuenta está conectado |
| `logout` | Borrar la sesión de este equipo |
| `sincronizar [--asignatura ID]` | Descargar los materiales nuevos o modificados, sin usar el asistente |
| `calendario [--dias N] [--asignatura ID]` | Guardar los plazos de los próximos días (90 por defecto) en `calendario.ics` |

Si las usas a menudo, instala la orden una vez con `uv tool install git+https://github.com/rdereparadores/cvuex-mcp` y escribe solo `cvuex-mcp login`, `cvuex-mcp calendario`… En ese caso, se actualiza con `uv tool upgrade cvuex-mcp`.

## Si algo no va

- **"La sesión ha caducado" o "no hay sesión":** vuelve a iniciar sesión con la orden `login`. No hace falta reiniciar el asistente.
- **La búsqueda en los apuntes no encuentra nada:** busca palabras, no significados. Prueba con sinónimos o en inglés, que es el idioma de algunos materiales. Los PDF escaneados y los formatos antiguos `.doc` y `.ppt` no se pueden buscar: la descarga te avisa de cuáles son para que los abras tú.
- **La descarga o la búsqueda en los foros tarda:** siguen en segundo plano. Vuelve a preguntar al cabo de un rato por cómo va.
- **No aparecen las tutorías de un profesor:** solo salen si las pone en su perfil del campus; si no, están en la guía docente de la asignatura.

## Herramientas disponibles

| Herramienta | Qué hace |
|---|---|
| `mis_asignaturas` | Tus asignaturas en curso, pasadas o futuras |
| `contenido_asignatura` | Los temas de una asignatura, con sus materiales y actividades |
| `contacto_profesorado` | Los profesores de cada asignatura, con su correo y su perfil |
| `proximos_plazos` | Entregas, aperturas, cierres y eventos del calendario, por fecha |
| `estado_entregas` | Tareas sin entregar, en borrador o entregadas, con nota y comentarios |
| `exportar_calendario` | Tus plazos en un fichero `.ics` |
| `calificaciones` | Tu nota en cada asignatura y el detalle por actividad |
| `cuestionarios` | Tus cuestionarios, con sus fechas y los intentos terminados |
| `revisar_cuestionario` | Las preguntas de un intento terminado, con la corrección |
| `avisos` | Los anuncios de los profesores y los debates de los foros generales |
| `leer_debate` | Un debate entero, con sus respuestas |
| `buscar_en_foros` | Busca en los mensajes de los foros |
| `novedades` | Qué ha cambiado en tus asignaturas desde la última vez |
| `notificaciones` | Las notificaciones del campus (la campana) |
| `sincronizar_materiales` | Descarga tus materiales y los prepara para buscar en ellos |
| `buscar_en_materiales` | En qué documento y página aparece un concepto |
| `leer_material` | El texto de esas páginas, para explicarlas y citarlas |
| `quien_soy` | Con qué cuenta está conectado |

## Desarrollo

¿Quieres revisar o modificar el código? Mira [DESARROLLO.md](DESARROLLO.md).

## Licencia

[MIT](LICENSE).
