"""What the tools return: the data the assistant sees, with Spanish field names.

Descriptions end up in each tool's output schema, so they are written for the assistant.
"""

from typing import Literal

from pydantic import BaseModel, Field


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
