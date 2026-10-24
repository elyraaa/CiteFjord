# CiteFjord

CiteFjord is a private desktop application for asking questions about your own PDF, Markdown, text, and code files. It indexes files locally, cites source pages, and uses a locally running Ollama model for answers. There is no web server or shared document library.

## Use the app

1. Install [Ollama](https://ollama.com/download), start it, and download the `qwen2.5-coder:7b` model with `ollama pull qwen2.5-coder:7b`.
2. Open `CiteFjord.exe` in its extracted application folder. Keep the whole folder together.
3. Choose **Add Files** to copy files into your private library. Text files can also be created and edited in the app; PDFs are read only.
4. To remove several copies, select them with Ctrl or Shift and choose **Delete Selected**. **Select All** selects the entire list.
5. Choose **Update Index** after adding, editing, or deleting files. Scanned PDF pages may take longer because they require OCR.
6. Open **Ask questions** to see an answer and its cited sources. When files change, the previous answer is cleared until the index is updated.

Imported files are copies. Editing or deleting a copy in CiteFjord does not change the original file. The application keeps documents and its search index in the operating system's per-user application data area. Existing installations continue using their prior private library. The bundled embedding model lets the Windows build index offline; Ollama must be running to generate answers. Verify important answers against the cited pages, particularly when OCR is used.

## Run from source

Use Python 3.12 with Tk support. Install the dependencies, then run `desktop_app.py`. On Windows:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe desktop_app.py
```

The embedding model downloads on first use when running from source. The Windows release build includes a cached copy. Source installations also need English OCR data in `tessdata` for image-only PDF pages. The native executable is built for Windows x64; macOS and Linux users can run the source with Python, Tk, dependencies, and Ollama, or build their own platform-specific executable.

## Build and deliver the Windows app

Install PyInstaller, prepare English OCR data, and run:

```powershell
& .\.venv\Scripts\python.exe -m pip install pyinstaller
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-windows.ps1
```

The build copies a cached embedding model when `model_cache` is present. Keep the complete `dist\CiteFjord` folder together when distributing it. The text editor supports UTF-8 files up to 5 MB; imported files may be up to 50 MB.

Docker can package the Windows application for delivery. Recipients extract the application and run it on Windows; they do not need Docker. On the sender's computer:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\package-docker.ps1
```

Send the resulting archive with `extract-from-docker.ps1`, then extract it on the recipient's computer:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\extract-from-docker.ps1 -ImageTar .\citefjord-delivery.tar
& .\CiteFjord\CiteFjord.exe
```

Each recipient still needs their own Ollama installation and model. A normal ZIP of the entire release folder is also suitable for delivery.

## Verify

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The `src.cli` commands remain available for maintenance and benchmarking. Use `python -m src.cli --help` for the command list.
