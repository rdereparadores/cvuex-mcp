"""Ready-made requests the student can pick in the MCP client (in opencode, as the
slash commands /cvuex:resumen_semanal, /cvuex:preparar_examen and /cvuex:ponerme_al_dia).

They are instructions: they tell the assistant which tools to use and how to
present the result, and the assistant fetches the data when it runs them.
"""

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

CITE_AND_DONT_INVENT = (
    "No inventes fechas, notas ni contenidos: usa solo lo que den las herramientas, y si "
    "algo no aparece, dilo."
)


def resumen_semanal() -> str:
    """Plan de la semana: plazos, entregas pendientes y avisos de los profesores."""
    return f"""\
Prepárame un plan para esta semana con lo que tengo en el Campus Virtual.

1. Usa proximos_plazos con dias=7 para ver entregas, cierres de actividades y eventos.
2. Usa estado_entregas para saber qué tareas me faltan por entregar.
3. Usa avisos con dias=7 por si los profesores han anunciado algún cambio.

Preséntalo por días, de hoy al domingo, empezando por lo vencido o más urgente. Para
cada cosa, indica la asignatura, qué hay que hacer, la hora límite y el enlace. Termina
con los avisos importantes y una propuesta de cómo repartir el trabajo. Si le vendría
bien tener los plazos en su calendario, ofrécele exportarlos con exportar_calendario.
{CITE_AND_DONT_INVENT}"""


def preparar_examen(
    asignatura: Annotated[str, Field(description="Nombre (o id) de la asignatura.")],
    tema: Annotated[
        str, Field(description="Tema o parte que entra; si se deja vacío, toda la asignatura.")
    ] = "",
) -> str:
    """Esquema, preguntas de repaso y tarjetas de un tema, a partir de los apuntes, citándolos."""
    what = (
        f"el tema «{tema}» de {asignatura}" if tema.strip() else f"toda la asignatura {asignatura}"
    )
    return f"""\
Ayúdame a preparar el examen: {what}.

1. Busca la asignatura con mis_asignaturas y mira con contenido_asignatura qué incluye.
2. Si aún no hay materiales descargados, usa sincronizar_materiales y espera a que termine.
3. Usa buscar_en_materiales con los conceptos clave (prueba también en inglés si no
   encuentras nada) y leer_material para leer las páginas que importen.
4. Si en cuestionarios hay intentos terminados de la asignatura, mira con
   revisar_cuestionario en qué fallé, para insistir en eso.

Con todo ello prepara:
a) un esquema del contenido;
b) 10 preguntas de repaso, con su respuesta;
c) tarjetas de estudio (pregunta / respuesta breve).

Cita siempre el documento y la página de cada idea (p. ej. «Tema3.pdf, p. 12»).
{CITE_AND_DONT_INVENT} No uses esto para responder un cuestionario o examen en curso."""


def ponerme_al_dia(
    asignatura: Annotated[str, Field(description="Nombre (o id) de la asignatura.")],
) -> str:
    """Lo que ha pasado en una asignatura: materiales nuevos, avisos, plazos y lo pendiente."""
    return f"""\
Ponme al día de {asignatura}.

1. Busca la asignatura con mis_asignaturas para tener su id.
2. Usa novedades con asignatura_id para ver qué ha cambiado, y contenido_asignatura para
   situar cada novedad en su tema.
3. Usa avisos con asignatura_id y dias=30; si algún debate con respuestas parece
   importante, léelo con leer_debate.
4. Usa proximos_plazos y estado_entregas con asignatura_id para lo que viene y lo que
   me falta.

Resúmelo en: qué se ha publicado, qué han avisado los profesores, qué toca ahora y qué
tengo pendiente, con los enlaces.
{CITE_AND_DONT_INVENT}"""


PROMPTS = (resumen_semanal, preparar_examen, ponerme_al_dia)


def register(mcp: MCPServer) -> None:
    for prompt in PROMPTS:
        mcp.prompt()(prompt)
