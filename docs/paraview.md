# ParaView workflow

1. Run `export_for_paraview` on a solved case.
2. Copy the reported zip or `VTK/` folder to your Mac (scp, S3, shared disk).
3. Open in ParaView:
   - Prefer the OpenFOAM case directory (`.foam` empty file trick or OpenFOAM reader), or
   - Open VTK files from the export.
4. Useful filters for the **axisymmetric circular pipe** (wedge):
   - **Slice** or view the wedge sector
   - **Plot Over Line** from axis (r=0) to wall (r=R) for Ux(r)
   - **Glyph** for velocity vectors
5. Analytical Hagen–Poiseuille: Ux(r) = 2 U_bulk (1 − (r/R)²); compare with `compare_to_analytical`.
