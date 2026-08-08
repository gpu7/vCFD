# ParaView workflow

1. Run `export_for_paraview` on a solved case.
2. Copy the reported zip or `VTK/` folder to your Mac (scp, S3, shared disk).
3. Open in ParaView:
   - Prefer the OpenFOAM case directory (`.foam` empty file trick or OpenFOAM reader), or
   - Open VTK files from the export.
4. Useful filters for the pipe/channel case:
   - **Slice** along the center plane
   - **Plot Over Line** from wall to centerline for velocity profile
   - **Glyph** for velocity vectors
5. Compare centerline / radial profile to the analytical numbers spoken by `compare_to_analytical`.
