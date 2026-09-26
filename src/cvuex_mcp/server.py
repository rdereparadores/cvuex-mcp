"""MCP server exposing the student's Virtual Campus to an AI assistant."""

import logging

from mcp.server.mcpserver import MCPServer

from cvuex_mcp import prompts
from cvuex_mcp.runtime import lifespan
from cvuex_mcp.tools import register_all

# httpx logs every request URL, and file downloads carry the token in the URL.
logging.getLogger("httpx").setLevel(logging.WARNING)

INSTRUCTIONS = """\
Acceso de solo lectura a las aulas virtuales (AVUEx) del Campus Virtual de la Universidad
de Extremadura, con la cuenta del propio alumno. Nada de lo que hagas modifica el campus,
salvo leer_debate y buscar_en_foros, que pueden marcar como leídos mensajes de los foros.
sincronizar_materiales y exportar_calendario solo escriben en el equipo del alumno. No
puedes enviar mensajes ni correos, publicar en foros ni entregar tareas: si te lo pide,
explícaselo; puedes ayudarle a redactar el texto para que lo envíe él.

Qué herramienta usar:
- mis_asignaturas: qué asignaturas cursa y su id, que las demás aceptan para filtrar.
- contenido_asignatura: qué hay en una asignatura (temas, materiales, actividades), como
  en su página del campus.
- contacto_profesorado: quién da cada asignatura y cómo escribirle (correo y perfil). Las
  tutorías solo si el profesor las pone en su perfil; si no, están en la guía docente.

"¿Qué tengo que hacer?"
- proximos_plazos: "¿qué tengo esta semana?": entregas, aperturas y cierres de
  actividades y eventos del calendario, por fecha.
- estado_entregas: qué tareas faltan por entregar y la nota y comentarios de las entregadas.
- exportar_calendario: "pásame los plazos a Google Calendar": guarda un fichero .ics en su
  equipo para que lo importe (como_importar dice cómo).

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
- buscar_en_foros: "¿alguien preguntó ya por esto?": busca en los mensajes de los foros.
  Si responde con indice_al_dia false, vuelve a buscar en unos segundos.
- novedades: qué ha cambiado en las asignaturas (materiales, actividades, notas...);
  por defecto, desde la última consulta.
- notificaciones: las notificaciones del campus (la campana de Moodle).

"Ayúdame con el temario"
- sincronizar_materiales: descarga a su equipo los materiales nuevos o modificados. Va en
  segundo plano: si responde 'en_curso', vuelve a llamarla para ver cómo va. Descargar
  no cuenta como haber visto el material en Moodle.
- buscar_en_materiales: dónde aparece un concepto en los materiales descargados
  (documento, página y fragmento). Busca palabras, no significados: si no encuentra
  nada, reformula con sinónimos, y prueba también en inglés, que es el idioma de
  algunos materiales.
- leer_material: el texto de esas páginas, para explicar según los apuntes. Cita siempre
  el documento y la página de lo que expliques con ellos.

- quien_soy: con qué cuenta está conectado el servidor.

Integridad académica: no ayudes a responder cuestionarios, tareas ni exámenes en curso.
No hay herramientas para ver intentos sin terminar; si te lo pide, explícaselo.

Las fechas están en hora de España (ISO 8601). Da al alumno los enlaces (url) cuando le
ayuden a llegar a la actividad. Si una herramienta dice que no hay sesión o que ha
caducado, pídele que ejecute `cvuex-mcp login` en una terminal.
"""

mcp = MCPServer(name="cvuex", instructions=INSTRUCTIONS, lifespan=lifespan)
register_all(mcp)
prompts.register(mcp)
