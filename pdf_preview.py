from __future__ import annotations

import os
import threading
from pathlib import Path

# Optional dependency: PyMuPDF (pymupdf)
try:
    import fitz

    HAS_FITZ = True
except Exception:  # pragma: no cover - environment dependent
    fitz = None
    HAS_FITZ = False


def _is_container_env() -> bool:
    """Heuristic: run only in container (Railway) where /data mount exists."""
    try:
        return Path("/app").exists() and Path("/data").exists()
    except Exception:
        return False


def preview_png_path_for_pdf(pdf_path: Path) -> Path:
    """Return the target PNG preview path for a given PDF path.

    We place the PNG next to the PDF under the same directory, with suffix .render.png
    Example: /data/.../latex/foo.pdf -> /data/.../latex/foo.render.png
    """
    pdf_path = Path(pdf_path)
    return pdf_path.parent / f"{pdf_path.stem}.render.png"


def render_pdf_first_page_to_png(
    pdf_path: Path, out_png: Path | None = None, scale: float = 2.0
) -> Path:
    """Render the first page of a PDF to a PNG file using PyMuPDF.

    - scale: 2.0 gives a 144 DPI-like raster, good balance of quality/size
    """
    if not HAS_FITZ:
        raise RuntimeError("PyMuPDF (pymupdf) is not available to render PDFs")

    pdf_path = Path(pdf_path)
    if out_png is None:
        out_png = preview_png_path_for_pdf(pdf_path)

    out_png.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(0)
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat)
        pix.save(str(out_png))
    finally:
        doc.close()

    return out_png


def ensure_png_up_to_date(pdf_path: Path) -> Path:
    """Ensure a PNG preview exists and is newer than the PDF. Re-render if not.

    Returns the PNG path regardless of whether re-rendering happened.
    """
    pdf_path = Path(pdf_path)
    png_path = preview_png_path_for_pdf(pdf_path)

    try:
        if (not png_path.exists()) or (png_path.stat().st_mtime < pdf_path.stat().st_mtime):
            if HAS_FITZ:
                try:
                    render_pdf_first_page_to_png(pdf_path, png_path)
                except Exception as e:
                    print(f"[PDF PREVIEW] Render failed for {pdf_path}: {e}")
            else:
                # No renderer available; leave it and let UI fallback handle it
                pass
    except Exception as e:
        print(f"[PDF PREVIEW] Failed to check timestamps for {pdf_path}: {e}")

    return png_path


def start_pdf_preview_watcher(
    base_dir: Path | None = None, debounce_seconds: float = 1.0, enabled: bool | None = None
) -> None:
    """Start a lightweight watchdog observer to render PNG previews on PDF changes.

    Behavior:
    - Only runs in container (/data present) unless explicitly enabled.
    - Watches recursively under base_dir for *.pdf within any .../csv/latex directory.
    - Debounces bursts of events and processes changed files once per burst.
    - Stores PNGs next to the PDFs as <stem>.render.png (on the /data mount).
    """
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except Exception as e:  # pragma: no cover - depends on environment
        print(f"[PDF PREVIEW] Watcher unavailable (watchdog not importable): {e}")
        return

    if enabled is None:
        enabled = _is_container_env() and os.getenv("DISABLE_PDF_PREVIEW_WATCHER", "0") != "1"

    if not enabled:
        print("[PDF PREVIEW] Watcher disabled (not container or disabled via env)")
        return

    if base_dir is None:
        try:
            from config import get_data_dir

            base_dir = get_data_dir()
        except Exception:
            base_dir = Path("/data")

    if not base_dir.exists():
        print(f"[PDF PREVIEW] Data dir not found, watcher not started: {base_dir}")
        return

    class _Handler(FileSystemEventHandler):
        def __init__(self):
            self._lock = threading.Lock()
            self._changed: set[Path] = set()
            self._timer: threading.Timer | None = None

        def _schedule(self):
            if self._timer is not None:
                try:
                    self._timer.cancel()
                except Exception:
                    pass
            self._timer = threading.Timer(debounce_seconds, self._process)
            self._timer.daemon = True
            self._timer.start()

        def on_created(self, event):
            self._on_event(event)

        def on_modified(self, event):
            self._on_event(event)

        def _on_event(self, event):
            try:
                if getattr(event, "is_directory", False):
                    return
                p = Path(getattr(event, "src_path", ""))
                if p.suffix.lower() == ".pdf" and "csv" in p.parts and "latex" in p.parts:
                    with self._lock:
                        self._changed.add(p)
                    self._schedule()
            except Exception as e:
                print(f"[PDF PREVIEW] Event handling error: {e}")

        def _process(self):
            try:
                with self._lock:
                    items = list(self._changed)
                    self._changed.clear()
                if not items:
                    return
                print(f"[PDF PREVIEW] Processing {len(items)} changed PDF(s)")
                for pdf in items:
                    try:
                        ensure_png_up_to_date(pdf)
                    except Exception as e:
                        print(f"[PDF PREVIEW] Failed to update preview for {pdf}: {e}")
            except Exception as e:
                print(f"[PDF PREVIEW] Processing loop error: {e}")

    observer = Observer()
    handler = _Handler()
    observer.schedule(handler, str(base_dir), recursive=True)
    observer.daemon = True
    observer.start()
    print(f"[PDF PREVIEW] Watcher started on {base_dir}")
