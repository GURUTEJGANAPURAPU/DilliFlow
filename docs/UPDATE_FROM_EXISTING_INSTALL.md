# Updating an existing DilliFlow installation

This enhanced source bundle intentionally does **not** include a processed SQLite database or a local `.env` secret file.

If the earlier DilliFlow setup already completed successfully on your Windows machine:

1. Keep the existing `backend/data/processed/dilliflow.sqlite` file.
2. Keep the existing `backend/.env` file and its locally configured Transport Stack key.
3. Extract the new ZIP contents over the existing `D:\DilliFlow` project folder and allow source files to be overwritten.
4. Do not delete the existing `.venv`, `frontend/node_modules`, SQLite database or `.env` file.
5. Start both services from `D:\DilliFlow` using `\.\run_dilliflow.ps1`.

The enhanced package does not change the SQLite table schema, so a completed database ingestion does not need to be repeated. The package includes the original raw source archives for a fresh installation.

If you are already in `D:\DilliFlow\backend`, run the wrapper `\.\run_dilliflow.ps1` from that directory. It forwards to the project-root launcher.

To verify the backend separately, open a third PowerShell window:

```powershell
cd D:\DilliFlow\backend
..\.venv\Scripts\python.exe scripts\smoke_test.py
```

