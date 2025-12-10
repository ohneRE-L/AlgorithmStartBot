from sqlalchemy import Column, BigInteger, String, DateTime, Text, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database.base import Base
import uuid


class User(Base):
    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, default='OPERATOR')
    registered_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связь: Один пользователь -> Много заявок
    requests = relationship("AnalysisRequest", back_populates="user")

    __table_args__ = (
        CheckConstraint("role IN ('OPERATOR', 'MODERATOR')", name='check_user_role'),
    )


class Region(Base):
    __tablename__ = "regions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, nullable=False)

    # Связь: Один регион -> Много заявок
    requests = relationship("AnalysisRequest", back_populates="region")


class SourceImage(Base):
    __tablename__ = "source_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_path = Column(Text, nullable=False)
    file_size = Column(BigInteger, nullable=True)
    file_extension = Column(String(10), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связь: Одна картинка -> Одна заявка
    request = relationship("AnalysisRequest", back_populates="source_image", uselist=False)


class AnalysisRequest(Base):
    __tablename__ = "analysis_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False, index=True)
    region_id = Column(UUID(as_uuid=True), ForeignKey('regions.id'), nullable=True)
    source_image_id = Column(UUID(as_uuid=True), ForeignKey('source_images.id'), unique=True, nullable=False)

    algorithm_name = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False, default='PENDING', index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    user = relationship("User", back_populates="requests")
    region = relationship("Region", back_populates="requests")
    source_image = relationship("SourceImage", back_populates="request")

    # Cascade delete: если удаляем заявку, результат тоже удаляется
    result = relationship("Result", back_populates="request", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'ERROR')", name='check_request_status'),
    )


class Result(Base):
    __tablename__ = "results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_request_id = Column(UUID(as_uuid=True), ForeignKey('analysis_requests.id'), unique=True, nullable=False)

    # Важно: имя колонки в БД 'metadata', а в Python 'result_metadata', чтобы избежать конфликта имен
    result_metadata = Column("metadata", JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    request = relationship("AnalysisRequest", back_populates="result")