from sqlalchemy import (Table, Column, ForeignKey, text, UniqueConstraint)
from sqlalchemy.types import (Boolean, Integer, TIMESTAMP)
from sqlalchemy.dialects.postgresql import (ENUM, JSONB, TEXT, UUID)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


Base = declarative_base()


class ServiceGroup(Base):
    __tablename__ = 'service_groups'

    id = Column(UUID(as_uuid=True),
                primary_key=True,
                # This requires the uuid-ossp extension
                server_default=text('uuid_generate_v4()'))

    name = Column(TEXT, nullable=False)
    description = Column(TEXT, nullable=False)
    slug = Column(TEXT, nullable=False, unique=True)


class ServiceServiceGroup(Base):
    __tablename__ = 'service_service_groups'
    __table_args__ = (UniqueConstraint('group_id', 'service_id'),)

    id = Column(UUID(as_uuid=True),
                primary_key=True,
                # This requires the uuid-ossp extension
                server_default=text('uuid_generate_v4()'))

    group_id = Column(UUID(as_uuid=True), ForeignKey('service_groups.id'), nullable=False)
    service_id = Column(UUID(as_uuid=True), ForeignKey('services.id'), nullable=False)


class Service(Base):
    __tablename__ = 'services'

    id = Column(UUID(as_uuid=True),
                primary_key=True,
                # This requires the uuid-ossp extension
                server_default=text('uuid_generate_v4()'))

    name = Column(TEXT, nullable=False)
    description = Column(TEXT, nullable=False)
    slug = Column(TEXT, nullable=False, unique=True)

    groups = relationship('Event', backref='services', secondary=ServiceServiceGroup)


class Event(Base):
    __tablename__ = 'events'

    id = Column(UUID(as_uuid=True),
                primary_key=True,
                # This requires the uuid-ossp extension
                server_default=text('uuid_generate_v4()'))
    service_id = Column(UUID(as_uuid=True), ForeignKey('services.id'), nullable=False)
    when = Column(TIMESTAMP(timezone=True), nullable=False)
    status = Column(ENUM('up', 'down', 'limited'), nullable=False)
    text = Column(TEXT, nullable=False)
    informational = Column(Boolean, nullable=False)
    extra = Column(JSONB, nullable=False)

    service = relationship('Service', backref='events')


class EphemeralNotification(Base):
    __tablename__ = 'ephemeral_notifications'
    __table_args__ = (UniqueConstraint('username', 'service_id'),)

    id = Column(UUID(as_uuid=True),
                primary_key=True,
                # This requires the uuid-ossp extension
                server_default=text('uuid_generate_v4()'))

    username = Column(TEXT, nullable=False)
    service_id = Column(UUID(as_uuid=True), ForeignKey('services.id'), nullable=False)
    chat = Column(Boolean, nullable=False)
    email = Column(Boolean, nullable=False)

    service = relationship('Service', backref='ephemeral_notifications')


class DisplayPreferences(Base):
    __tablename__ = 'display_preferences'

    id = Column(UUID(as_uuid=True),
                primary_key=True,
                # This requires the uuid-ossp extension
                server_default=text('uuid_generate_v4()'))

    username = Column(TEXT, nullable=False, unique=True)
    preferences = Column(JSONB, nullable=False)


class APIKeys(Base):
    __tablename__ = 'api_keys'
    __table_args__ = ()

    id = Column(UUID(as_uuid=True),
                primary_key=True,
                # This requires the uuid-ossp extension
                server_default=text('uuid_generate_v4()'))
    username = Column(TEXT, nullable=False)
    key = Column(TEXT, nullable=False)


class Permissions(Base):
    __tablename__ = 'permissions'
    __table_args__ = ()

    id = Column(UUID(as_uuid=True),
                primary_key=True,
                # This requires the uuid-ossp extension
                server_default=text('uuid_generate_v4()'))
    username = Column(TEXT, nullable=False)
    service_id = Column(UUID(as_uuid=True), ForeignKey('services.id'), nullable=True)
    # service-admin - update specific service
    # updater       - add events to specific service
    permission = Column(ENUM('service-admin', 'updater'), nullable=False)

    service = relationship('Service', backref='allowed_users')
