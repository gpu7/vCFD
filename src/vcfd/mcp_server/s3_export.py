"""Upload ParaView packages to S3 and mint short-lived download URLs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def upload_paraview_zip(
    zip_path: Path,
    *,
    bucket: str,
    prefix: str = "paraview",
    region: str | None = None,
    case_name: str | None = None,
    presign_expiry_sec: int = 86400,
) -> dict[str, Any]:
    """Upload zip to s3://bucket/prefix/case/timestamp_name.zip and return keys/URLs.

    Uses default boto3 credential chain (instance role on EC2, env/profile on Mac).
    """
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    if not zip_path.is_file():
        raise FileNotFoundError(f"Zip not found: {zip_path}")

    bucket = bucket.strip()
    if not bucket:
        raise ValueError("S3 bucket name is empty")

    prefix = prefix.strip().strip("/")
    case = case_name or zip_path.stem.replace("_paraview", "")
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    key = f"{prefix}/{case}/{ts}_{zip_path.name}" if prefix else f"{case}/{ts}_{zip_path.name}"

    session_kwargs: dict[str, Any] = {}
    if region:
        session_kwargs["region_name"] = region
    session = boto3.session.Session(**session_kwargs)
    s3 = session.client("s3")

    extra = {
        "ContentType": "application/zip",
        "Metadata": {
            "vcfd-case": case,
            "vcfd-export": "paraview",
        },
    }
    try:
        s3.upload_file(
            str(zip_path),
            bucket,
            key,
            ExtraArgs=extra,
        )
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"S3 upload failed: {exc}") from exc

    s3_uri = f"s3://{bucket}/{key}"
    reg = session.region_name or region or "us-east-1"
    # Virtual-hosted URL (not directly downloadable if private)
    https_path = f"https://{bucket}.s3.{reg}.amazonaws.com/{key}"

    presigned: str | None = None
    try:
        presigned = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=max(60, int(presign_expiry_sec)),
        )
    except (BotoCoreError, ClientError):
        presigned = None

    return {
        "bucket": bucket,
        "key": key,
        "s3_uri": s3_uri,
        "region": session.region_name or region,
        "https_console_hint": https_path,
        "presigned_url": presigned,
        "presign_expiry_sec": presign_expiry_sec if presigned else None,
        "case_name": case,
        "size_bytes": zip_path.stat().st_size,
    }
