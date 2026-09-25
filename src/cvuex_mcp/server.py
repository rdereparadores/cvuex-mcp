"""MCP server exposing the student's Virtual Campus to an AI assistant."""

import logging

from mcp.server.mcpserver import MCPServer

from cvuex_mcp.runtime import lifespan
from cvuex_mcp.tools import register_all

# httpx logs every request URL, and file downloads carry the token in the URL.
logging.getLogger("httpx").setLevel(logging.WARNING)

INSTRUCTIONS = """\
Acceso de solo lectura a las aulas virtuales (AVUEx) del Campus Virtual de la Universidad
de Extremadura, con la cuenta del propio alumno. Nada de lo que hagas modifica el campus,
salvo leer_debate, que puede marcar como leídos los mensajes del debate.

Qué herramienta usar:
- mis_asignaturas: qué asignaturas cursa y su id, que las demás aceptan para filtrar.
- contenido_asignatura: qué hay en una asignatura (temas, materiales, actividades), como
  en su página del campus.

"¿Qué tengo que hacer?"
- proximos_plazos: "¿qué tengo esta semana?": entregas, aperturas y cierres de
  actividades y eventos del calendario, por fecha.
- estado_entregas: qué tareas faltan por entregar y la nota y comentarios de las entregadas.

"¿Cómo voy?"
- calificaciones: nota total de cada asignatura; con asignatura_id, el detalle de cada
  actividad (nota, peso, comentarios del profesor). No son las notas oficiales: las
  del acta están en la Secretaría Virtual.
- cuestionarios: cuestionarios con sus fechas y los intentos terminados (nota).
- revisar_cuestionario: preguntas de un intento terminado, con lo que respondió y la
  corrección, para explicarle sus fallos. Solo muestra lo que el profesor deja revisar.

"¿Qué hay de nuevo?"
- avisos: lo que publican los profesores y los debates de los foros generales, con el
  comienzo de cada mensaje. Para "¿hay avisos?".
- leer_debate: un debate completo, con sus respuestas. Úsala solo cuando el alumno
  quiera leerlo entero.
- novedades: qué ha cambiado en las asignaturas (materiales, actividades, notas...);
  por defecto, desde la última consulta.
- notificaciones: las notificaciones del campus (la campana de Moodle).

- quien_soy: con qué cuenta está conectado el servidor.

Integridad académica: no ayudes a responder cuestionarios, tareas ni exámenes en curso.
No hay herramientas para ver intentos sin terminar; si te lo pide, explícaselo.

Las fechas están en hora de España (ISO 8601). Da al alumno los enlaces (url) cuando le
ayuden a llegar a la actividad. Si una herramienta dice que no hay sesión o que ha
caducado, pídele que ejecute `cvuex-mcp login` en una terminal.
"""

mcp = MCPServer(name="cvuex", instructions=INSTRUCTIONS, lifespan=lifespan)
register_all(mcp)
