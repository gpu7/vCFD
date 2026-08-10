# ParaView workflow

## Automatic (S3 → Mac)

When the MCP server has `VCFD_S3_BUCKET` set (EC2 instance role can write):

1. Voice or MCP: `export_for_paraview` — uploads zip to S3 and returns a **presigned URL**.
2. On the Mac (AWS CLI credentials with `s3:GetObject` on the bucket):

```bash
./scripts/fetch_paraview_from_s3.sh --case voice_pipe
# or: ./scripts/fetch_paraview_from_s3.sh --latest
```

3. Open the unpacked folder under `results/` in ParaView.

Bucket default: `vcfd-results-<aws-account-id>`, prefix `paraview/`, private + AES256, 30-day expiry on `paraview/`.

## Manual

1. Run `export_for_paraview` on a solved case.
2. Copy the reported zip or `VTK/` folder to your Mac (scp, or S3 as above).
3. Open in ParaView:
   - Prefer the OpenFOAM case directory (`.foam` empty file trick or OpenFOAM reader), or
   - Open VTK files from the export.
4. Useful filters for the **axisymmetric circular pipe** (wedge):
   - **Slice** or view the wedge sector
   - **Plot Over Line** from axis (r=0) to wall (r=R) for Ux(r)
   - **Glyph** for velocity vectors
5. Analytical Hagen–Poiseuille: Ux(r) = 2 U_bulk (1 − (r/R)²); compare with `compare_to_analytical`.
