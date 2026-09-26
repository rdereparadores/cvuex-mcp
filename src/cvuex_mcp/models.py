"""What the tools return: the data the assistant sees, with Spanish field names.

Descriptions end up in each tool's output schema, so they are written for the assistant.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, SerializerFunctionWrapHandler, model_serializer


class Asignatura(BaseModel):
    id: int = Field(description="Identificador; sirve para filtrar otras herramientas.")
    nombre: str
    titulacion: str
    progreso: int | None = Field(
        description="Porcentaje de actividades completadas; null si la asignatura no lo registra."
    )
    url: str


class ListaAsignaturas(BaseModel):
    asignaturas: list[Asignatura]


class Profesor(BaseModel):
    nombre: str
    correo: str | None = Field(description="Solo si el profesor lo muestra en el campus.")
    perfil: str | None = Field(
        description="Lo que el profesor pone en su perfil del campus: a veces, tutorías y "
        "despacho. Si no habla de tutorías, están en la guía docente de la asignatura."
    )
    url: str = Field(description="Su perfil en el campus.")


class ProfesoradoAsignatura(BaseModel):
    asignatura: str
    asignatura_id: int
    profesores: list[Profesor] = Field(
        description="Los que el campus muestra como contacto de la asignatura."
    )


class ListaProfesorado(BaseModel):
    asignaturas: list[ProfesoradoAsignatura]


class Plazo(BaseModel):
    fecha: str = Field(description="Cuándo es (ISO 8601, hora de España).")
    asignatura: str | None
    asignatura_id: int | None
    actividad: str
    tipo: str = Field(
        description="tarea, cuestionario, consulta..., o evento de la asignatura, personal..."
    )
    evento: str = Field(
        description="Qué ocurre en esa fecha, p. ej. 'Práctica 1 está en fecha de entrega'."
    )
    descripcion: str | None
    requiere_accion: bool = Field(
        description="Moodle espera que el alumno haga algo (entregar, responder...). Si es false, "
        "es informativo: una apertura, un examen creado por el profesor, algo ya hecho..."
    )
    accion: str | None = Field(
        description="Lo que el alumno puede hacer ahora, si puede hacer algo."
    )
    vencido: bool
    url: str


class ListaPlazos(BaseModel):
    desde: str = Field(description="Inicio del periodo consultado (incluye vencidos recientes).")
    hasta: str
    plazos: list[Plazo]


class CalendarioExportado(BaseModel):
    fichero: str = Field(description="Ruta del .ics en el equipo del alumno.")
    eventos: int
    desde: str = Field(description="Primer momento incluido (ISO 8601): lo vencido no entra.")
    hasta: str
    como_importar: str


SubmissionState = Literal[
    "sin_entregar", "borrador", "entregada", "reabierta", "sin_entrega_online"
]


class EstadoEntrega(BaseModel):
    tarea: str
    asignatura: str
    asignatura_id: int
    fecha_limite: str | None = Field(
        description="Fecha límite (ISO 8601, hora de España), incluida la prórroga si la hay."
    )
    vencida: bool = Field(description="La fecha límite ya pasó.")
    estado: SubmissionState = Field(
        description="'sin_entrega_online': la tarea no se entrega por el campus (p. ej. un "
        "examen presencial). 'reabierta': el profesor permite una nueva entrega."
    )
    puede_entregar: bool = Field(
        description="Si ahora mismo puede entregar o modificar la entrega."
    )
    calificacion: str | None = Field(description="Nota publicada, si la hay.")
    comentarios_profesor: str | None
    url: str


class ListaEntregas(BaseModel):
    entregas: list[EstadoEntrega]
    avisos: list[str] = Field(description="Tareas que no se pudieron consultar, si las hay.")


class Novedad(BaseModel):
    actividad: str
    tipo: str
    cambios: list[str] = Field(description="Qué ha cambiado; entre paréntesis, cuántos elementos.")
    fecha: str | None = Field(description="Último cambio con fecha conocida (ISO 8601).")
    url: str


class NovedadesAsignatura(BaseModel):
    asignatura: str
    asignatura_id: int
    novedades: list[Novedad]


class ListaNovedades(BaseModel):
    desde: str = Field(description="Desde cuándo se buscan cambios (ISO 8601).")
    asignaturas: list[NovedadesAsignatura] = Field(description="Solo las que tienen cambios.")


class Notificacion(BaseModel):
    asunto: str
    resumen: str
    origen: str = Field(description="De dónde viene: foro, tarea, cuestionario, campus...")
    fecha: str | None = Field(description="Cuándo llegó (ISO 8601, hora de España).")
    leida: bool
    url: str | None


class ListaNotificaciones(BaseModel):
    sin_leer: int = Field(description="Total de notificaciones sin leer en el campus.")
    notificaciones: list[Notificacion] = Field(description="De la más reciente a la más antigua.")


class Aviso(BaseModel):
    asignatura: str | None
    asignatura_id: int
    foro: str
    titulo: str
    autor: str | None = Field(description="Quién lo publicó; null si el foro lo oculta.")
    fecha: str | None = Field(description="Cuándo se publicó (ISO 8601, hora de España).")
    ultima_respuesta: str | None = Field(description="Fecha de la última respuesta, si las hay.")
    mensaje: str = Field(description="El mensaje en texto, recortado; leer_debate lo da completo.")
    respuestas: int
    fijado: bool = Field(description="El profesor lo ha fijado arriba del foro.")
    debate_id: int = Field(description="Para leer el debate completo con leer_debate.")
    url: str


class ListaAvisos(BaseModel):
    desde: str = Field(
        description="Se incluyen los debates publicados o con respuestas desde aquí."
    )
    avisos: list[Aviso] = Field(description="Del más reciente al más antiguo.")


class MensajeForo(BaseModel):
    id: int
    autor: str | None
    fecha: str | None = Field(description="ISO 8601, hora de España.")
    asunto: str
    mensaje: str = Field(description="Completo, en texto.")
    en_respuesta_a: int | None = Field(description="id del mensaje al que responde.")
    privado: bool = Field(description="Respuesta privada, solo visible para algunos.")
    adjuntos: list[str] = Field(description="Nombres de los ficheros adjuntos.")


class Debate(BaseModel):
    titulo: str
    foro: str | None
    asignatura: str | None
    asignatura_id: int
    url: str
    mensajes: list[MensajeForo] = Field(description="En orden cronológico.")


class NotaAsignatura(BaseModel):
    asignatura: str | None
    asignatura_id: int
    nota: str | None = Field(
        description="Nota total de la asignatura, como la muestra el campus; null si aún no hay."
    )
    url: str = Field(description="Informe de calificaciones de la asignatura.")


class ItemCalificacion(BaseModel):
    actividad: str
    tipo: str = Field(
        description="tarea, cuestionario..., 'ítem manual' (p. ej. un examen presencial) o "
        "'total de categoría'."
    )
    categoria: str | None = Field(
        description="Categoría del libro de calificaciones (p. ej. 'Prácticas'); null si el "
        "ítem cuenta directamente en el total de la asignatura."
    )
    nota: str | None = Field(description="null si aún no está calificado.")
    rango: str | None = Field(description="Nota mínima y máxima posibles.")
    porcentaje: str | None
    peso: str | None = Field(
        description="Cuánto cuenta en su categoría (o en la asignatura), según lo calcula Moodle; "
        "entre paréntesis, si no cuenta y por qué."
    )
    comentarios: str | None = Field(description="Comentarios del profesor.")
    fecha: str | None = Field(description="Cuándo se calificó (ISO 8601, hora de España).")
    url: str | None = Field(description="Enlace a la actividad, si es una actividad.")


class Calificaciones(BaseModel):
    asignaturas: list[NotaAsignatura] = Field(
        description="Nota total de cada asignatura (solo la pedida, si se filtra)."
    )
    detalle: list[ItemCalificacion] = Field(
        description="Solo al pedir una asignatura: sus actividades y totales de categoría, en el "
        "orden del libro de calificaciones."
    )


class IntentoCuestionario(BaseModel):
    intento_id: int = Field(description="Para revisarlo con revisar_cuestionario.")
    numero: int = Field(description="Primer intento, segundo...")
    fecha: str | None = Field(description="Cuándo se terminó (ISO 8601, hora de España).")
    nota: float | None = Field(description="null si el profesor aún no deja ver la nota.")
    retroalimentacion: str | None = Field(description="Comentario general según la nota.")


class Cuestionario(BaseModel):
    cuestionario: str
    asignatura: str | None
    asignatura_id: int
    apertura: str | None = Field(description="Desde cuándo se puede hacer (ISO 8601).")
    cierre: str | None = Field(description="Hasta cuándo se puede hacer (ISO 8601).")
    intentos_permitidos: int | None = Field(description="null si son ilimitados.")
    nota_maxima: float | None
    intentos: list[IntentoCuestionario] = Field(description="Solo los terminados.")
    url: str


class ListaCuestionarios(BaseModel):
    cuestionarios: list[Cuestionario] = Field(description="Los más recientes primero.")
    avisos: list[str] = Field(description="Cuestionarios que no se pudieron consultar, si los hay.")


class PreguntaRevisada(BaseModel):
    numero: str | None
    tipo: str = Field(description="Tipo de pregunta en Moodle: multichoice, shortanswer, essay...")
    enunciado: str
    tu_respuesta: str = Field(
        description="Lo que respondió el alumno: [x] opción elegida, [ ] no elegida, "
        "[texto] lo escrito en un hueco."
    )
    estado: str | None = Field(description="Correcta, Incorrecta, Parcialmente correcta...")
    puntuacion: float | None
    puntuacion_maxima: float | None
    retroalimentacion: str | None
    respuesta_correcta: str | None
    comentario_profesor: str | None


class RevisionCuestionario(BaseModel):
    cuestionario: str | None
    asignatura: str | None
    intento_id: int
    intento_numero: int
    fecha: str | None = Field(description="Cuándo se terminó (ISO 8601, hora de España).")
    nota: float | None = Field(description="null si el profesor no deja ver la nota.")
    nota_maxima: float | None
    retroalimentacion_general: str | None
    preguntas: list[PreguntaRevisada]
    url: str


class CompactModel(BaseModel):
    """Leaves out empty fields (null, [], "") from the answer, for answers that can be big.

    Fields that can be empty have a default, so the schema doesn't require them.
    """

    @model_serializer(mode="wrap")
    def _without_empty_fields(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return {key: value for key, value in handler(self).items() if value not in (None, [], "")}


class Fichero(CompactModel):
    nombre: str = Field(description="Con su carpeta, si está dentro de una.")
    tamano: str | None = None
    fecha: str | None = Field(
        default=None, description="Última modificación (ISO 8601, hora de España)."
    )


class ElementoCurso(CompactModel):
    """Los campos vacíos no se envían."""

    nombre: str
    tipo: str = Field(description="archivo, carpeta, página, enlace, texto, tarea, foro...")
    disponible: bool = Field(description="false si el alumno aún no puede abrirlo.")
    restriccion: str | None = Field(
        default=None, description="Por qué no está disponible, si Moodle lo dice."
    )
    descripcion: str | None = Field(
        default=None, description="Texto visible en la página de la asignatura."
    )
    fechas: list[str] = Field(
        default_factory=list, description="Apertura, cierre, entrega... como las muestra Moodle."
    )
    completado: bool | None = Field(
        default=None, description="Falta si la asignatura no registra su finalización."
    )
    ficheros: list[Fichero] = Field(default_factory=list)
    apartados: list[str] = Field(default_factory=list, description="Capítulos, si es un libro.")
    enlace: str | None = Field(default=None, description="Dirección externa, si es un enlace.")
    url: str | None = Field(default=None, description="Dónde abrirlo en el campus.")


class SeccionCurso(CompactModel):
    """Los campos vacíos no se envían."""

    numero: int
    nombre: str
    dentro_de: str | None = Field(
        default=None, description="Sección que la contiene, si es una subsección."
    )
    resumen: str | None = None
    disponible: bool
    restriccion: str | None = None
    elementos: list[ElementoCurso] = Field(default_factory=list)


class ContenidoAsignatura(CompactModel):
    asignatura: str | None = None
    asignatura_id: int
    url: str
    secciones: list[SeccionCurso] = Field(description="En el orden de la página de la asignatura.")
    avisos: list[str] = Field(default_factory=list)


class EstadoSincronizacion(BaseModel):
    estado: Literal["en_curso", "terminada", "error"] = Field(
        description="'en_curso': sigue descargando; vuelve a llamar a la herramienta para ver "
        "cómo va."
    )
    carpeta: str = Field(description="Dónde están los materiales en el equipo del alumno.")
    asignaturas: list[str]
    ficheros: int = Field(description="Ficheros encontrados en el campus.")
    revisados: int
    descargados: int = Field(description="Nuevos o modificados, descargados ahora.")
    al_dia: int = Field(description="Ya estaban descargados y no han cambiado.")
    retirados: int = Field(description="Ya no están en el campus; la copia local se conserva.")
    tamano_descargado: str | None
    indexados: int = Field(description="Documentos cuyo texto se ha indexado ahora para buscar.")
    no_buscables: list[str] = Field(
        description="Documentos en los que no se puede buscar, y por qué (PDF escaneados, "
        "formatos antiguos): el alumno tiene que abrirlos él mismo."
    )
    omitidos: list[str] = Field(description="Demasiado grandes: se descargan desde el campus.")
    avisos: list[str] = Field(description="Ficheros o asignaturas que fallaron.")
    error: str | None = Field(description="Por qué se detuvo, si se detuvo.")
    inicio: str | None
    fin: str | None


class CoincidenciaMaterial(BaseModel):
    documento_id: int = Field(description="Para leer el documento con leer_material.")
    documento: str = Field(description="Nombre del fichero.")
    asignatura: str
    seccion: str
    ubicacion: str = Field(
        description="Dónde está: 'página 12', 'diapositiva 3', 'apartado 2 (Introducción)'."
    )
    numero: int = Field(description="Página, diapositiva o apartado: el 'desde' de leer_material.")
    fragmento: str = Field(description="Texto alrededor de la coincidencia, marcada con «».")
    archivo: str = Field(description="Ruta del fichero en el equipo del alumno.")
    url: str | None = Field(description="El material en el campus.")


class ResultadosMateriales(BaseModel):
    todas_las_palabras: bool = Field(
        description="false si ningún fragmento las contiene todas: se muestran los que tienen "
        "alguna, y conviene reformular."
    )
    resultados: list[CoincidenciaMaterial] = Field(description="Los más relevantes primero.")
    avisos: list[str]


class TextoMaterial(BaseModel):
    documento_id: int
    documento: str
    asignatura: str
    seccion: str
    unidad: str = Field(description="Qué cuenta 'desde' y 'hasta': página, diapositiva o apartado.")
    total: int = Field(description="Última página, diapositiva o apartado con texto.")
    desde: int
    hasta: int
    texto: str = Field(description="Con una cabecera [Página N] (o similar) por cada parte.")
    continua_en: int | None = Field(
        description="Si el texto se ha cortado por tamaño, desde dónde seguir leyendo."
    )
    archivo: str
    url: str | None


class CoincidenciaForo(BaseModel):
    asignatura: str
    foro: str
    titulo: str = Field(description="Título del debate.")
    autor: str | None = Field(description="Quién escribió el mensaje que coincide.")
    fecha: str | None = Field(description="Cuándo lo escribió (ISO 8601, hora de España).")
    fragmento: str = Field(description="Texto alrededor de la coincidencia, marcada con «».")
    respuestas: int
    debate_id: int = Field(description="Para leer el debate entero con leer_debate.")
    url: str


class ResultadosForos(BaseModel):
    todas_las_palabras: bool = Field(
        description="false si ningún mensaje las contiene todas: se muestran los que tienen "
        "alguna, y conviene reformular."
    )
    indice_al_dia: bool = Field(
        description="false si el índice aún se está actualizando: vuelve a buscar en unos "
        "segundos para ver todos los resultados."
    )
    debates_indexados: int
    resultados: list[CoincidenciaForo] = Field(
        description="Un resultado por debate, los más relevantes primero."
    )
    avisos: list[str]
