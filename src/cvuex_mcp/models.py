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
    fecha: str = Field(description="Fecha límite (ISO 8601, hora de España).")
    asignatura: str | None
    asignatura_id: int | None
    actividad: str
    tipo: str = Field(description="Tipo de actividad: tarea, cuestionario, consulta...")
    evento: str = Field(
        description="Qué ocurre en esa fecha, p. ej. 'Práctica 1 está en fecha de entrega'."
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
