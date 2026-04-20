import logging
import uuid

import boto3
from botocore.exceptions import ClientError
from flask import Blueprint, request, jsonify, current_app

from . import db
from .auth import login_required
from .models import File, FileShare, User

import time
from .logging_utils import log_event

files_bp = Blueprint("files", __name__, url_prefix="/api/files")
logger   = logging.getLogger(__name__)


# ── S3 client ──────────────────────────────────────────────────────────────────

def _s3_client():
    # VULN: boto3 is initialised with explicit credentials sourced from env vars
    # (.env file) rather than the instance metadata service (IAM role).
    # If the .env file is accessible via a path-traversal or SSRF vulnerability,
    # the long-lived AWS key pair is fully exposed.
    cfg = current_app.config
    return boto3.client(
        "s3",
        region_name          = cfg["AWS_REGION"],
        aws_access_key_id    = cfg["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key= cfg["AWS_SECRET_ACCESS_KEY"],
    )


# ── Upload ─────────────────────────────────────────────────────────────────────

@files_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    start = time.time()

    if "file" not in request.files:
        log_event(
            "file_upload_failure",
            level="warning",
            endpoint=request.path,
            http_status=400,
            ip=request.remote_addr,
            user_id=getattr(request.current_user, "id", None),
            error="No file part in request"
        )
        return jsonify({"error": "No file part in request"}), 400

    f = request.files["file"]
    if not f.filename:
        log_event(
            "file_upload_failure",
            level="warning",
            endpoint=request.path,
            http_status=400,
            ip=request.remote_addr,
            user_id=getattr(request.current_user, "id", None),
            error="Empty filename"
        )
        return jsonify({"error": "Empty filename"}), 400

    user = request.current_user
    s3_key = f"uploads/{user.id}/{uuid.uuid4().hex}_{f.filename}"
    bucket = current_app.config["S3_BUCKET_NAME"]
    file_size = getattr(f, "content_length", None) or request.content_length or 0
    content_type = f.content_type or "application/octet-stream"

    try:
        s3 = _s3_client()
        s3.upload_fileobj(
            f,
            bucket,
            s3_key,
            ExtraArgs={"ContentType": content_type},
        )
    except ClientError as e:
        logger.error("S3 upload failed: %s", e)

        log_event(
            "file_upload_failure",
            level="error",
            endpoint=request.path,
            http_status=500,
            ip=request.remote_addr,
            user_id=user.id,
            file_name=f.filename,
            file_size=file_size,
            content_type=content_type,
            s3_bucket=bucket,
            s3_key=s3_key,
            error=str(e)
        )

        return jsonify({"error": "Upload to S3 failed"}), 500

    file_record = File(
        owner_id=user.id,
        filename=f.filename,
        s3_key=s3_key,
        size_bytes=file_size,
        content_type=content_type,
    )
    db.session.add(file_record)
    db.session.commit()

    logger.info("File uploaded by user %d: %s (file_id=%d)", user.id, f.filename, file_record.id)

    log_event(
        "file_upload_success",
        endpoint=request.path,
        http_status=201,
        ip=request.remote_addr,
        user_id=user.id,
        file_id=file_record.id,
        file_name=f.filename,
        file_size=file_size,
        content_type=content_type,
        s3_bucket=bucket,
        s3_key=s3_key,
        latency_ms=int((time.time() - start) * 1000)
    )

    return jsonify({"message": "uploaded", "file": file_record.to_dict()}), 201

# ── List files ─────────────────────────────────────────────────────────────────

@files_bp.route("/", methods=["GET"])
@login_required
def list_files():
    user = request.current_user

    owned = File.query.filter_by(owner_id=user.id).all()

    shared_file_ids = db.session.query(FileShare.file_id).filter_by(
        shared_with_user_id=user.id
    ).subquery()
    shared = File.query.filter(File.id.in_(shared_file_ids)).all()

    owned_list = []
    for f in owned:
        d = f.to_dict()
        d["is_shared"] = f.shares.count() > 0
        owned_list.append(d)

    result = {
        "owned":  owned_list,
        "shared": [f.to_dict() for f in shared],
    }
    return jsonify(result)


# ── Download (presigned URL) ───────────────────────────────────────────────────

@files_bp.route("/<int:file_id>/download", methods=["GET"])
@login_required
def download(file_id):
    start = time.time()
    user = request.current_user

    # VULN: file_id is a sequential integer — see models.py for IDOR details.
    file_record = db.session.get(File, file_id)
    if not file_record:
        log_event(
            "file_download_failure",
            level="warning",
            endpoint=request.path,
            http_status=404,
            ip=request.remote_addr,
            user_id=user.id,
            file_id=file_id,
            error="File not found"
        )
        return jsonify({"error": "File not found"}), 404

    # Access control: owner or any user the file was shared with
    is_owner = file_record.owner_id == user.id
    is_shared = FileShare.query.filter_by(
        file_id=file_id, shared_with_user_id=user.id
    ).first() is not None

    if not is_owner and not is_shared:
        log_event(
            "file_download_failure",
            level="warning",
            endpoint=request.path,
            http_status=403,
            ip=request.remote_addr,
            user_id=user.id,
            file_id=file_id,
            owner_id=file_record.owner_id,
            error="Access denied"
        )
        return jsonify({"error": "Access denied"}), 403

    try:
        s3 = _s3_client()
        url = s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": current_app.config["S3_BUCKET_NAME"],
                "Key": file_record.s3_key
            },
            ExpiresIn=current_app.config["S3_PRESIGNED_EXPIRY"],
        )
    except ClientError as e:
        logger.error("Presigned URL generation failed: %s", e)

        log_event(
            "presigned_url_failed",
            level="error",
            endpoint=request.path,
            http_status=500,
            ip=request.remote_addr,
            user_id=user.id,
            file_id=file_id,
            owner_id=file_record.owner_id,
            s3_key=file_record.s3_key,
            error=str(e)
        )

        return jsonify({"error": "Could not generate download link"}), 500

    log_event(
        "file_download_success",
        endpoint=request.path,
        http_status=200,
        ip=request.remote_addr,
        user_id=user.id,
        file_id=file_id,
        owner_id=file_record.owner_id,
        s3_key=file_record.s3_key,
        latency_ms=int((time.time() - start) * 1000)
    )

    return jsonify({"download_url": url})


# ── Delete ─────────────────────────────────────────────────────────────────────

@files_bp.route("/<int:file_id>", methods=["DELETE"])
@login_required
def delete_file(file_id):
    user        = request.current_user
    file_record = db.session.get(File, file_id)

    if not file_record:
        return jsonify({"error": "File not found"}), 404

    if file_record.owner_id != user.id:
        return jsonify({"error": "Only the owner can delete this file"}), 403

    try:
        s3 = _s3_client()
        s3.delete_object(
            Bucket=current_app.config["S3_BUCKET_NAME"],
            Key=file_record.s3_key,
        )
    except ClientError as e:
        logger.error("S3 delete failed: %s", e)

    db.session.delete(file_record)
    db.session.commit()
    logger.info("File deleted by user %d: file_id=%d", user.id, file_id)
    return jsonify({"message": "deleted"})


# ── Share ──────────────────────────────────────────────────────────────────────

@files_bp.route("/<int:file_id>/share", methods=["POST"])
@login_required
def share_file(file_id):
    user        = request.current_user
    file_record = db.session.get(File, file_id)

    if not file_record:
        return jsonify({"error": "File not found"}), 404

    if file_record.owner_id != user.id:
        return jsonify({"error": "Only the owner can share this file"}), 403

    data       = request.get_json(silent=True) or {}
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
        file_id=file_id, shared_with_user_id=target_user.id
    ).first()

    if existing:
        existing.permission = permission
        db.session.commit()
        return jsonify({"message": "permission updated", "share": existing.to_dict()})

    share = FileShare(
        file_id             = file_id,
        shared_with_user_id = target_user.id,
        permission          = permission,
    )
    db.session.add(share)
    db.session.commit()

    logger.info(
        "File %d shared by user %d with user %d (permission=%s)",
        file_id, user.id, target_user.id, permission,
    )
    return jsonify({"message": "shared", "share": share.to_dict()}), 201


# ── List shares for a file ────────────────────────────────────────────────────

@files_bp.route("/<int:file_id>/shares", methods=["GET"])
@login_required
def list_shares(file_id):
    user        = request.current_user
    file_record = db.session.get(File, file_id)

    if not file_record:
        return jsonify({"error": "File not found"}), 404

    if file_record.owner_id != user.id:
        return jsonify({"error": "Only the owner can view shares"}), 403

    shares = FileShare.query.filter_by(file_id=file_id).all()
    result = []
    for s in shares:
        entry = s.to_dict()
        entry["shared_with_email"] = s.shared_with_user.email
        result.append(entry)

    return jsonify({"shares": result})
