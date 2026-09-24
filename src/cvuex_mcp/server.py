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
- proximos_plazos: "¿qué tengo esta semana?": entregas, aperturas y cierres de
  actividades y eventos del calendario, por fecha.
- estado_entregas: qué tareas faltan por entregar y la nota y comentarios de las entregadas.
- calificaciones: nota total de cada asignatura; con asignatura_id, el detalle de cada
  actividad (nota, peso, comentarios del profesor).
- novedades: qué ha cambiado en las asignaturas (por defecto, desde la última consulta).
- notificaciones: notificaciones del campus (foros, calificaciones...).
- avisos: anuncios de los profesores y debates de los foros generales, con el comienzo
  de cada mensaje.
- leer_debate: un debate completo, con sus respuestas. Úsala solo cuando el alumno
  quiera leerlo entero.
- quien_soy: con qué cuenta está conectado el servidor.

Las fechas están en hora de España (ISO 8601). Da al alumno los enlaces (url) cuando le
ayuden a llegar a la actividad. Si una herramienta dice que no hay sesión o que ha
caducado, pídele que ejecute `cvuex-mcp login` en una terminal.
"""

mcp = MCPServer(name="cvuex", instructions=INSTRUCTIONS, lifespan=lifespan)
register_all(mcp)
