import uuid
from datetime import datetime

from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from . import db


class User(db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    is_verified                = db.Column(db.Boolean, default=False, nullable=False)
    verification_token         = db.Column(db.String(255), nullable=True)
    verification_token_expires = db.Column(db.DateTime, nullable=True)

    owned_files   = db.relationship("File",   back_populates="owner",      lazy="dynamic")
    owned_folders = db.relationship("Folder", back_populates="owner",      lazy="dynamic")
    shared_with   = db.relationship("FileShare", back_populates="shared_with_user", lazy="dynamic")
    reset_tokens  = db.relationship("PasswordResetToken", back_populates="user",    lazy="dynamic")

    def to_dict(self):
        return {"id": self.id, "email": self.email, "created_at": self.created_at.isoformat()}


class Folder(db.Model):
    __tablename__ = "folders"

    id         = db.Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name       = db.Column(db.String(255), nullable=False)
    owner_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    parent_id  = db.Column(PG_UUID(as_uuid=True), db.ForeignKey("folders.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner    = db.relationship("User",   back_populates="owned_folders")
    files    = db.relationship("File",   back_populates="folder", lazy="dynamic")
    # Self-referential adjacency list for nested folders
    parent   = db.relationship(
        "Folder",
        remote_side=[id],
        foreign_keys=[parent_id],
        back_populates="children",
    )
    children = db.relationship(
        "Folder",
        foreign_keys=[parent_id],
        back_populates="parent",
        lazy="dynamic",
    )

    def to_dict(self):
        return {
            "id":         str(self.id),
            "name":       self.name,
            "owner_id":   self.owner_id,
            "parent_id":  str(self.parent_id) if self.parent_id else None,
            "created_at": self.created_at.isoformat(),
        }


class File(db.Model):
    __tablename__ = "files"

    id           = db.Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    filename     = db.Column(db.String(512), nullable=False)
    s3_key       = db.Column(db.String(1024), nullable=False)
    size_bytes   = db.Column(db.BigInteger, default=0)
    content_type = db.Column(db.String(255), default="application/octet-stream")
    uploaded_at  = db.Column(db.DateTime, default=datetime.utcnow)
    is_deleted   = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at   = db.Column(db.DateTime, nullable=True)
    is_starred   = db.Column(db.Boolean, default=False, nullable=False)
    folder_id    = db.Column(PG_UUID(as_uuid=True), db.ForeignKey("folders.id"), nullable=True)

    owner  = db.relationship("User",   back_populates="owned_files")
    folder = db.relationship("Folder", back_populates="files")
    shares = db.relationship("FileShare", back_populates="file", lazy="dynamic",
                             cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id":           str(self.id),
            "filename":     self.filename,
            "size_bytes":   self.size_bytes,
            "content_type": self.content_type,
            "uploaded_at":  self.uploaded_at.isoformat(),
            "owner_id":     self.owner_id,
            "is_deleted":   self.is_deleted,
            "deleted_at":   self.deleted_at.isoformat() if self.deleted_at else None,
            "is_starred":   self.is_starred,
            "folder_id":    str(self.folder_id) if self.folder_id else None,
        }


class FileShare(db.Model):
    __tablename__ = "file_shares"

    id                  = db.Column(db.Integer, primary_key=True)
    file_id             = db.Column(PG_UUID(as_uuid=True), db.ForeignKey("files.id"), nullable=False)
    shared_with_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    permission          = db.Column(db.String(10), nullable=False, default="read")
    shared_at           = db.Column(db.DateTime, default=datetime.utcnow)

    file             = db.relationship("File", back_populates="shares")
    shared_with_user = db.relationship("User", back_populates="shared_with")

    __table_args__ = (
        db.UniqueConstraint("file_id", "shared_with_user_id", name="uq_file_share"),
    )

    def to_dict(self):
        return {
            "id":          self.id,
            "file_id":     str(self.file_id),
            "shared_with": self.shared_with_user_id,
            "permission":  self.permission,
            "shared_at":   self.shared_at.isoformat(),
        }


class RevokedToken(db.Model):
    __tablename__ = "revoked_tokens"

    jti        = db.Column(db.String(36), primary_key=True)
    revoked_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id         = db.Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    token      = db.Column(db.String(36), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used       = db.Column(db.Boolean, default=False)

    user = db.relationship("User", back_populates="reset_tokens")
