"""What the tools return: the data the assistant sees, with Spanish field names.

Descriptions end up in each tool's output schema, so they are written for the assistant.
"""

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
