"""Settings model for storing connection configurations."""

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bsupervisor.models.base import Base, UUIDPrimaryKeyMixin


class Settings(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
