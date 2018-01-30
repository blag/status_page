from sqlalchemy import event
from sqlalchemy import (Column, ForeignKey, Index, text, UniqueConstraint)
from sqlalchemy.dialects.postgresql import (ENUM, JSONB, TEXT, UUID)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.types import (Boolean, TIMESTAMP)

from slugify import slugify


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

    def __str__(self):
        return self.name


class ServiceServiceGroup(Base):
    __tablename__ = 'service_groups_services'
    __table_args__ = (UniqueConstraint('group_id', 'service_id'),)

    id = Column(UUID(as_uuid=True),
                primary_key=True,
                # This requires the uuid-ossp extension
                server_default=text('uuid_generate_v4()'))

    group_id = Column(UUID(as_uuid=True), ForeignKey('service_groups.id'), nullable=False)
    service_id = Column(UUID(as_uuid=True), ForeignKey('services.id'), nullable=False)

    def __str__(self):
        return f"{self.group_id}.{self.service_id}"


class Service(Base):
    __tablename__ = 'services'

    id = Column(UUID(as_uuid=True),
                primary_key=True,
                # This requires the uuid-ossp extension
                server_default=text('uuid_generate_v4()'))

    name = Column(TEXT, nullable=False)
    description = Column(TEXT, nullable=False)
    slug = Column(TEXT, nullable=False, unique=True)

    ix_services_slug = Index(slug)

    groups = relationship('ServiceGroup', backref='services', secondary='service_groups_services')

    events = relationship('Event', backref='service', cascade='delete, delete-orphan')
    ephemeral_notifications = relationship('EphemeralNotification', backref='service', cascade='delete, delete-orphan')
    allowed_users = relationship('Permission', backref='service', cascade='delete, delete-orphan')

    def __str__(self):
        return self.name


class Event(Base):
    __tablename__ = 'events'

    id = Column(UUID(as_uuid=True),
                primary_key=True,
                # This requires the uuid-ossp extension
                server_default=text('uuid_generate_v4()'))
    service_id = Column(UUID(as_uuid=True), ForeignKey('services.id'), nullable=False)
    # Index on the timestamp, BETWEEN
    when = Column(TIMESTAMP(timezone=True), nullable=False)
    status = Column(ENUM('up', 'down', 'limited', name='status_enum', create_type=False),
                    nullable=False)
    description = Column(TEXT, nullable=False)
    informational = Column(Boolean, nullable=False)
    extra = Column(JSONB, nullable=False)

    ix_events_when = Index(when.desc())

    # service = relationship('Service', backref='events', cascade='delete, delete-orphan')

    def __str__(self):
        return f"{self.service} -> {self.status.upper()}"


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

    # service = relationship('Service', backref='ephemeral_notifications', cascade='delete, delete-orphan')

    def __str__(self):
        return f"Notify {self.username} via {'chat' if self.chat else 'email' if self.email else 'None'} about {self.service}"


class DisplayPreferences(Base):
    __tablename__ = 'display_preferences'

    id = Column(UUID(as_uuid=True),
                primary_key=True,
                # This requires the uuid-ossp extension
                server_default=text('uuid_generate_v4()'))

    username = Column(TEXT, nullable=False, unique=True)
    preferences = Column(JSONB, nullable=False)

    def __str__(self):
        return f"{self.username} preferences"


class Permission(Base):
    __tablename__ = 'permissions'
    __table_args__ = ()

    id = Column(UUID(as_uuid=True),
                primary_key=True,
                # This requires the uuid-ossp extension
                server_default=text('uuid_generate_v4()'))
    username = Column(TEXT, nullable=False)
    service_id = Column(UUID(as_uuid=True), ForeignKey('services.id'), nullable=False)
    # service-admin - update specific service
    # updater       - add events to specific service
    type = Column(ENUM('service-admin', 'updater', name='role_enum', create_type=False),
                  nullable=False)

    # service = relationship('Service', backref='allowed_users', cascade='delete, delete-orphan')

    def __str__(self):
        return f"{self.username} ({self.permission} for {self.service})"


# http://docs.sqlalchemy.org/en/latest/orm/events.html#sqlalchemy.orm.events.AttributeEvents.set
@event.listens_for(ServiceGroup.name, 'set')
def set_service_group_slug(target, value, oldvalue, initiator):
    '''Set the slug when the name changes'''
    target.slug = slugify(value, to_lower=True)


@event.listens_for(Service.name, 'set')
def set_service_slug(target, value, oldvalue, initiator):
    '''Set the slug when the name changes'''
    target.slug = slugify(value, to_lower=True)
