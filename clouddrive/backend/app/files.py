import logging
import uuid
from datetime import datetime
from uuid import UUID

import boto3
from botocore.exceptions import ClientError
from flask import Blueprint, request, jsonify, current_app

from . import db
from .auth import login_required
from .models import File, FileShare, Folder, User

files_bp   = Blueprint("files",   __name__, url_prefix="/api/files")
shares_bp  = Blueprint("shares",  __name__, url_prefix="/api/shares")
folders_bp = Blueprint("folders", __name__, url_prefix="/api/folders")
logger     = logging.getLogger(__name__)

MAX_UPLOAD_BYTES   = 10 * 1024 * 1024  # 10 MB (used only by the reupload endpoint)
ALLOWED_EXTENSIONS = {
    "pdf", "txt", "doc", "docx", "png", "jpg", "jpeg", "gif",
    "mp4", "mov", "zip", "csv", "xlsx", "pptx",
}
IMAGE_EXTENSIONS   = {"png", "jpg", "jpeg", "gif"}
TEXT_EXTENSIONS    = {"txt"}
PDF_EXTENSIONS     = {"pdf"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _s3_client():
    cfg = current_app.config
    return boto3.client(
        "s3",
        region_name           = cfg["AWS_REGION"],
        aws_access_key_id     = cfg["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key = cfg["AWS_SECRET_ACCESS_KEY"],
    )


def _parse_uuid(uid_str: str):
    """Return a UUID object from a string, or None if the string is invalid."""
    try:
        return UUID(uid_str)
    except (ValueError, AttributeError):
        return None


def _presigned_get(s3_key: str) -> str:
    s3 = _s3_client()
    return s3.generate_presigned_url(
        "get_object",
        Params    = {"Bucket": current_app.config["S3_BUCKET_NAME"], "Key": s3_key},
        ExpiresIn = current_app.config["S3_PRESIGNED_EXPIRY"],
    )


# ══════════════════════════════════════════════════════════════════════════════
#  FILES BLUEPRINT  (/api/files)
# ══════════════════════════════════════════════════════════════════════════════

# ── Get presigned POST URL (requires: owner) ──────────────────────────────────

@files_bp.route("/upload-url", methods=["GET"])
@login_required
def get_upload_url():
    filename     = (request.args.get("filename") or "").strip()
    content_type = request.args.get("content_type", "application/octet-stream")

    if not filename:
        return jsonify({"error": "filename is required"}), 400

    if not _allowed_file(filename):
        return jsonify({"error": "File type not allowed"}), 400

    user      = request.current_user
    file_uuid = uuid.uuid4()
    s3_key    = f"uploads/{user.email}/{file_uuid}/{filename}"
    bucket    = current_app.config["S3_BUCKET_NAME"]

    try:
        s3       = _s3_client()
        response = s3.generate_presigned_post(
            Bucket     = bucket,
            Key        = s3_key,
            Conditions = [["content-length-range", 1, 5368709120]],
            ExpiresIn  = 300,
        )
    except ClientError as e:
        logger.error("Presigned POST generation failed: %s", e)
        return jsonify({"error": "Could not generate upload URL"}), 500

    return jsonify({
        "upload_url": response["url"],
        "fields":     response["fields"],
        "s3_key":     s3_key,
    })


# ── Confirm upload after direct S3 PUT (requires: owner) ──────────────────────

@files_bp.route("/confirm-upload", methods=["POST"])
@login_required
def confirm_upload():
    data         = request.get_json(silent=True) or {}
    filename     = (data.get("filename") or "").strip()
    s3_key       = (data.get("s3_key") or "").strip()
    size_bytes   = data.get("size_bytes", 0)
    content_type = data.get("content_type", "application/octet-stream")

    if not filename or not s3_key:
        return jsonify({"error": "filename and s3_key are required"}), 400

    user = request.current_user
    file_record = File(
        owner_id     = user.id,
        filename     = filename,
        s3_key       = s3_key,
        size_bytes   = size_bytes,
        content_type = content_type,
        is_deleted   = False,
        is_starred   = False,
    )
    db.session.add(file_record)
    db.session.commit()

    logger.info("upload_success user=%d file=%s id=%s", user.id, filename, file_record.id)
    return jsonify({"file": file_record.to_dict()}), 201


# ── List files  (requires: owner) — supports ?starred=true ───────────────────

@files_bp.route("/", methods=["GET"])
@login_required
def list_files():
    user    = request.current_user
    starred = request.args.get("starred", "").lower() == "true"

    base_query = File.query.filter_by(owner_id=user.id, is_deleted=False)
    if starred:
        base_query = base_query.filter_by(is_starred=True)
    owned = base_query.all()

    shared_file_ids = db.session.query(FileShare.file_id).filter_by(
        shared_with_user_id=user.id
    ).subquery()
    shared = File.query.filter(
        File.id.in_(shared_file_ids), File.is_deleted == False
    ).all()

    owned_list = []
    for f in owned:
        d = f.to_dict()
        d["is_shared"] = f.shares.count() > 0
        owned_list.append(d)

    return jsonify({
        "owned":  owned_list,
        "shared": [f.to_dict() for f in shared],
    })


# ── Trash  (requires: owner) ──────────────────────────────────────────────────

@files_bp.route("/trash", methods=["GET"])
@login_required
def list_trash():
    user  = request.current_user
    files = File.query.filter_by(owner_id=user.id, is_deleted=True).all()
    return jsonify({"trash": [f.to_dict() for f in files]})


# ── Download (presigned URL) — requires: read or edit permission ──────────────

@files_bp.route("/<string:file_id>/download", methods=["GET"])
@login_required
def download(file_id):
    fid = _parse_uuid(file_id)
    if not fid:
        return jsonify({"error": "File not found"}), 404

    user        = request.current_user
    file_record = db.session.get(File, fid)
    if not file_record or file_record.is_deleted:
        return jsonify({"error": "File not found"}), 404

    is_owner = file_record.owner_id == user.id
    share    = FileShare.query.filter_by(file_id=fid, shared_with_user_id=user.id).first()

    if not is_owner and not share:
        return jsonify({"error": "Access denied"}), 403

    try:
        url = _presigned_get(file_record.s3_key)
    except ClientError as e:
        logger.error("Presigned URL generation failed: %s", e)
        return jsonify({"error": "Could not generate download link"}), 500

    logger.info("download_success user=%d file_id=%s", user.id, file_id)
    return jsonify({"download_url": url})


# ── Replace content in-place — requires: edit permission or owner ─────────────

@files_bp.route("/<string:file_id>/content", methods=["PUT"])
@login_required
def reupload(file_id):
    fid = _parse_uuid(file_id)
    if not fid:
        return jsonify({"error": "File not found"}), 404

    user        = request.current_user
    file_record = db.session.get(File, fid)
    if not file_record or file_record.is_deleted:
        return jsonify({"error": "File not found"}), 404

    is_owner = file_record.owner_id == user.id
    share    = FileShare.query.filter_by(file_id=fid, shared_with_user_id=user.id).first()
    has_edit = share and share.permission == "edit"

    if not is_owner and not has_edit:
        return jsonify({"error": "Edit permission required"}), 403

    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    if not _allowed_file(f.filename):
        return jsonify({"error": (
            "File type not allowed. Permitted: pdf, txt, doc, docx, png, jpg, jpeg, gif"
        )}), 400

    content = f.read()
    if len(content) > MAX_UPLOAD_BYTES:
        return jsonify({"error": "File exceeds the maximum allowed size of 10 MB"}), 400
    f.seek(0)

    bucket = current_app.config["S3_BUCKET_NAME"]
    try:
        s3 = _s3_client()
        # Overwrite the existing S3 object at the same key
        s3.upload_fileobj(
            f, bucket, file_record.s3_key,
            ExtraArgs={"ContentType": f.content_type or "application/octet-stream"},
        )
    except ClientError as e:
        logger.error("S3 re-upload failed: %s", e)
        return jsonify({"error": "Re-upload to S3 failed"}), 500

    file_record.size_bytes   = len(content)
    file_record.content_type = f.content_type or "application/octet-stream"
    db.session.commit()

    logger.info("File content replaced by user %d (file_id=%s)", user.id, file_id)
    return jsonify({"message": "re-uploaded", "file": file_record.to_dict()})


# ── Soft delete — requires: owner ─────────────────────────────────────────────

@files_bp.route("/<string:file_id>", methods=["DELETE"])
@login_required
def delete_file(file_id):
    fid = _parse_uuid(file_id)
    if not fid:
        return jsonify({"error": "File not found"}), 404

    user        = request.current_user
    file_record = db.session.get(File, fid)

    if not file_record or file_record.is_deleted:
        return jsonify({"error": "File not found"}), 404

    if file_record.owner_id != user.id:
        return jsonify({"error": "Only the owner can delete this file"}), 403

    file_record.is_deleted = True
    file_record.deleted_at = datetime.utcnow()
    db.session.commit()

    logger.info("File soft-deleted by user %d: file_id=%s", user.id, file_id)
    return jsonify({"message": "moved to trash"})


# ── Restore from trash — requires: owner ─────────────────────────────────────

@files_bp.route("/<string:file_id>/restore", methods=["POST"])
@login_required
def restore_file(file_id):
    fid = _parse_uuid(file_id)
    if not fid:
        return jsonify({"error": "File not found"}), 404

    user        = request.current_user
    file_record = db.session.get(File, fid)

    if not file_record or not file_record.is_deleted:
        return jsonify({"error": "File not found in trash"}), 404

    if file_record.owner_id != user.id:
        return jsonify({"error": "Only the owner can restore this file"}), 403

    file_record.is_deleted = False
    file_record.deleted_at = None
    db.session.commit()

    logger.info("File restored by user %d: file_id=%s", user.id, file_id)
    return jsonify({"message": "restored", "file": file_record.to_dict()})


# ── Permanent delete — requires: owner + file already in trash ────────────────

@files_bp.route("/<string:file_id>/permanent", methods=["DELETE"])
@login_required
def permanent_delete(file_id):
    fid = _parse_uuid(file_id)
    if not fid:
        return jsonify({"error": "File not found"}), 404

    user        = request.current_user
    file_record = db.session.get(File, fid)

    if not file_record:
        return jsonify({"error": "File not found"}), 404

    if not file_record.is_deleted:
        return jsonify({"error": "File must be in trash before permanent deletion"}), 400

    if file_record.owner_id != user.id:
        return jsonify({"error": "Only the owner can permanently delete this file"}), 403

    try:
        s3 = _s3_client()
        s3.delete_object(
            Bucket=current_app.config["S3_BUCKET_NAME"],
            Key=file_record.s3_key,
        )
    except ClientError as e:
        logger.error("S3 permanent delete failed: %s", e)

    db.session.delete(file_record)
    db.session.commit()

    logger.info("File permanently deleted by user %d: file_id=%s", user.id, file_id)
    return jsonify({"message": "permanently deleted"})


# ── Toggle star — requires: owner ─────────────────────────────────────────────

@files_bp.route("/<string:file_id>/star", methods=["PUT"])
@login_required
def toggle_star(file_id):
    fid = _parse_uuid(file_id)
    if not fid:
        return jsonify({"error": "File not found"}), 404

    user        = request.current_user
    file_record = db.session.get(File, fid)

    if not file_record or file_record.is_deleted:
        return jsonify({"error": "File not found"}), 404

    if file_record.owner_id != user.id:
        return jsonify({"error": "Only the owner can star this file"}), 403

    file_record.is_starred = not file_record.is_starred
    db.session.commit()

    return jsonify({"is_starred": file_record.is_starred})


# ── Move to folder — requires: owner ─────────────────────────────────────────

@files_bp.route("/<string:file_id>/move", methods=["PUT"])
@login_required
def move_file(file_id):
    fid = _parse_uuid(file_id)
    if not fid:
        return jsonify({"error": "File not found"}), 404

    user        = request.current_user
    file_record = db.session.get(File, fid)

    if not file_record or file_record.is_deleted:
        return jsonify({"error": "File not found"}), 404

    if file_record.owner_id != user.id:
        return jsonify({"error": "Only the owner can move this file"}), 403

    data          = request.get_json(silent=True) or {}
    folder_id_str = data.get("folder_id")

    if folder_id_str is None:
        file_record.folder_id = None
    else:
        folder_fid = _parse_uuid(folder_id_str)
        if not folder_fid:
            return jsonify({"error": "Invalid folder_id"}), 400
        folder = db.session.get(Folder, folder_fid)
        if not folder or folder.owner_id != user.id:
            return jsonify({"error": "Folder not found"}), 404
        file_record.folder_id = folder_fid

    db.session.commit()
    return jsonify({"message": "moved", "file": file_record.to_dict()})


# ── Preview — requires: read or edit permission ───────────────────────────────

@files_bp.route("/<string:file_id>/preview", methods=["GET"])
@login_required
def preview_file(file_id):
    fid = _parse_uuid(file_id)
    if not fid:
        return jsonify({"error": "File not found"}), 404

    user        = request.current_user
    file_record = db.session.get(File, fid)

    if not file_record or file_record.is_deleted:
        return jsonify({"error": "File not found"}), 404

    is_owner = file_record.owner_id == user.id
    share    = FileShare.query.filter_by(file_id=fid, shared_with_user_id=user.id).first()

    if not is_owner and not share:
        return jsonify({"error": "Access denied"}), 403

    ext    = _ext(file_record.filename)
    bucket = current_app.config["S3_BUCKET_NAME"]

    try:
        if ext in IMAGE_EXTENSIONS:
            url = _presigned_get(file_record.s3_key)
            return jsonify({"type": "image", "url": url})

        elif ext in TEXT_EXTENSIONS:
            s3  = _s3_client()
            obj = s3.get_object(Bucket=bucket, Key=file_record.s3_key)
            raw = obj["Body"].read(50 * 1024)  # first 50 KB
            return jsonify({"type": "text", "content": raw.decode("utf-8", errors="replace")})

        elif ext in PDF_EXTENSIONS:
            url = _presigned_get(file_record.s3_key)
            return jsonify({"type": "pdf", "url": url})

        else:
            url = _presigned_get(file_record.s3_key)
            return jsonify({"type": "download", "url": url})

    except ClientError as e:
        logger.error("Preview failed for file %s: %s", file_id, e)
        return jsonify({"error": "Could not generate preview"}), 500


# ── Share a file — requires: owner ───────────────────────────────────────────

@files_bp.route("/<string:file_id>/share", methods=["POST"])
@login_required
def share_file(file_id):
    fid = _parse_uuid(file_id)
    if not fid:
        return jsonify({"error": "File not found"}), 404

    user        = request.current_user
    file_record = db.session.get(File, fid)

    if not file_record or file_record.is_deleted:
        return jsonify({"error": "File not found"}), 404

    if file_record.owner_id != user.id:
        return jsonify({"error": "Only the owner can share this file"}), 403

    data         = request.get_json(silent=True) or {}
    target_email = (data.get("email") or "").strip().lower()
    permission   = data.get("permission", "read")

    if permission not in ("read", "edit"):
        return jsonify({"error": "permission must be 'read' or 'edit'"}), 400
    if not target_email:
        return jsonify({"error": "email is required"}), 400
    if target_email == user.email:
        return jsonify({"error": "Cannot share a file with yourself"}), 400

    target_user = User.query.filter_by(email=target_email).first()
    if not target_user:
        return jsonify({"error": "No user found with that email"}), 404

    existing = FileShare.query.filter_by(
        file_id=fid, shared_with_user_id=target_user.id
    ).first()
    if existing:
        existing.permission = permission
        db.session.commit()
        return jsonify({"message": "permission updated", "share": existing.to_dict()})

    share = FileShare(
        file_id             = fid,
        shared_with_user_id = target_user.id,
        permission          = permission,
    )
    db.session.add(share)
    db.session.commit()

    logger.info("File %s shared by user %d with user %d (%s)", file_id, user.id, target_user.id, permission)
    return jsonify({"message": "shared", "share": share.to_dict()}), 201


# ── List shares for a file — requires: owner ─────────────────────────────────

@files_bp.route("/<string:file_id>/shares", methods=["GET"])
@login_required
def list_shares(file_id):
    fid = _parse_uuid(file_id)
    if not fid:
        return jsonify({"error": "File not found"}), 404

    user        = request.current_user
    file_record = db.session.get(File, fid)

    if not file_record:
        return jsonify({"error": "File not found"}), 404
    if file_record.owner_id != user.id:
        return jsonify({"error": "Only the owner can view shares"}), 403

    result = []
    for s in FileShare.query.filter_by(file_id=fid).all():
        entry = s.to_dict()
        entry["shared_with_email"] = s.shared_with_user.email
        result.append(entry)

    return jsonify({"shares": result})


# ══════════════════════════════════════════════════════════════════════════════
#  SHARES BLUEPRINT  (/api/shares)
# ══════════════════════════════════════════════════════════════════════════════

# ── Outgoing shares (files I own that I've shared) ───────────────────────────

@shares_bp.route("/outgoing", methods=["GET"])
@login_required
def shares_outgoing():
    user = request.current_user

    rows = (
        db.session.query(FileShare, File)
        .join(File, FileShare.file_id == File.id)
        .filter(File.owner_id == user.id)
        .all()
    )

    result = []
    for share, file in rows:
        result.append({
            "share_id":          share.id,
            "file_id":           str(file.id),
            "filename":          file.filename,
            "shared_with_email": share.shared_with_user.email,
            "permission":        share.permission,
            "created_at":        share.shared_at.isoformat(),
        })

    return jsonify({"outgoing": result})


# ── Incoming shares (files shared with me) ───────────────────────────────────

@shares_bp.route("/incoming", methods=["GET"])
@login_required
def shares_incoming():
    user = request.current_user

    rows = (
        db.session.query(FileShare, File)
        .join(File, FileShare.file_id == File.id)
        .filter(FileShare.shared_with_user_id == user.id, File.is_deleted == False)
        .all()
    )

    result = []
    for share, file in rows:
        result.append({
            "share_id":       share.id,
            "file_id":        str(file.id),
            "filename":       file.filename,
            "owner_username": file.owner.email,
            "permission":     share.permission,
            "created_at":     share.shared_at.isoformat(),
        })

    return jsonify({"incoming": result})


# ── Revoke a share — requires: file owner ────────────────────────────────────

@shares_bp.route("/<int:share_id>", methods=["DELETE"])
@login_required
def revoke_share(share_id):
    user  = request.current_user
    share = db.session.get(FileShare, share_id)

    if not share:
        return jsonify({"error": "Share not found"}), 404

    if share.file.owner_id != user.id:
        return jsonify({"error": "Only the file owner can revoke a share"}), 403

    db.session.delete(share)
    db.session.commit()

    logger.info("Share %d revoked by user %d", share_id, user.id)
    return jsonify({"message": "share revoked"})


# ══════════════════════════════════════════════════════════════════════════════
#  FOLDERS BLUEPRINT  (/api/folders)
# ══════════════════════════════════════════════════════════════════════════════

# ── List folders — requires: owner ───────────────────────────────────────────

@folders_bp.route("/", methods=["GET"])
@login_required
def list_folders():
    user    = request.current_user
    folders = Folder.query.filter_by(owner_id=user.id).all()
    return jsonify({"folders": [f.to_dict() for f in folders]})


# ── Create folder — requires: owner ──────────────────────────────────────────

@folders_bp.route("/", methods=["POST"])
@login_required
def create_folder():
    user = request.current_user
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()

    if not name:
        return jsonify({"error": "name is required"}), 400

    parent_id     = None
    parent_id_str = data.get("parent_id")
    if parent_id_str:
        parent_fid = _parse_uuid(parent_id_str)
        if not parent_fid:
            return jsonify({"error": "Invalid parent_id"}), 400
        parent = db.session.get(Folder, parent_fid)
        if not parent or parent.owner_id != user.id:
            return jsonify({"error": "Parent folder not found"}), 404
        parent_id = parent_fid

    folder = Folder(name=name, owner_id=user.id, parent_id=parent_id)
    db.session.add(folder)
    db.session.commit()

    return jsonify({"message": "created", "folder": folder.to_dict()}), 201


# ── Delete empty folder — requires: owner ────────────────────────────────────

@folders_bp.route("/<string:folder_id>", methods=["DELETE"])
@login_required
def delete_folder(folder_id):
    fid = _parse_uuid(folder_id)
    if not fid:
        return jsonify({"error": "Folder not found"}), 404

    user   = request.current_user
    folder = db.session.get(Folder, fid)

    if not folder:
        return jsonify({"error": "Folder not found"}), 404
    if folder.owner_id != user.id:
        return jsonify({"error": "Only the owner can delete this folder"}), 403

    has_files   = File.query.filter_by(folder_id=fid).first() is not None
    has_children = folder.children.first() is not None

    if has_files or has_children:
        return jsonify({"error": "Folder must be empty before deletion"}), 400

    db.session.delete(folder)
    db.session.commit()

    return jsonify({"message": "deleted"})
