"""S3 export unit tests (mocked boto3)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from vcfd.mcp_server.s3_export import upload_paraview_zip


def test_upload_paraview_zip(tmp_path: Path):
    z = tmp_path / "demo_paraview.zip"
    z.write_bytes(b"PK\x03\x04fake")

    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = "https://example.com/presigned"
    mock_session = MagicMock()
    mock_session.client.return_value = mock_client
    mock_session.region_name = "us-east-1"

    with patch("boto3.session.Session", return_value=mock_session):
        info = upload_paraview_zip(
            z,
            bucket="vcfd-results-test",
            prefix="paraview",
            region="us-east-1",
            case_name="demo",
            presign_expiry_sec=3600,
        )

    assert info["bucket"] == "vcfd-results-test"
    assert info["key"].startswith("paraview/demo/")
    assert info["key"].endswith("demo_paraview.zip")
    assert info["s3_uri"].startswith("s3://vcfd-results-test/")
    assert info["presigned_url"] == "https://example.com/presigned"
    mock_client.upload_file.assert_called_once()
