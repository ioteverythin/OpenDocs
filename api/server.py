"""OpenDocs REST API — deployable to Railway, Render, Fly.io, etc.

Endpoints
---------
GET  /                  → Welcome / info
GET  /health            → Health check
GET  /formats           → List available output formats
GET  /themes            → List available themes
POST /generate          → Generate docs from a GitHub URL or raw Markdown
POST /generate/upload   → Generate docs from an uploaded file (.md / .ipynb)
"""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from opendocs import __version__
from opendocs.core.models import OutputFormat
from opendocs.core.template_vars import TemplateVars
from opendocs.generators.themes import list_themes
from opendocs.pipeline import Pipeline

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="OpenDocs API",
    description=(
        "Convert GitHub READMEs, Markdown files, and Jupyter Notebooks "
        "into structured, multi-format documentation — instantly."
    ),
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared pipeline instance
_pipeline = Pipeline()

# Max output dir age (cleaned up after response)
_TEMP_ROOT = Path(tempfile.gettempdir()) / "opendocs-api"
_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    """Request body for the /generate endpoint."""
    source: str = Field(..., description="GitHub URL or raw Markdown content")
    format: str = Field("all", description="Output format: word, pdf, pptx, blog, jira, changelog, latex, onepager, social, faq, architecture, all")
    theme: str = Field("corporate", description="Theme name (e.g. corporate, ocean, aurora)")
    mode: str = Field("basic", description="basic or llm")
    provider: str = Field("openai", description="LLM provider: openai, anthropic, google, ollama, azure")
    model: str = Field("gpt-4o-mini", description="LLM model name")
    api_key: Optional[str] = Field(None, description="LLM API key (required for llm mode)")
    sort_tables: str = Field("smart", description="Table sort strategy")
    # Template vars
    project_name: Optional[str] = None
    author: Optional[str] = None
    version: Optional[str] = None
    organisation: Optional[str] = None
    department: Optional[str] = None
    confidentiality: Optional[str] = None


class GenerateInfo(BaseModel):
    """Metadata returned alongside the ZIP file."""
    job_id: str
    source: str
    format: str
    theme: str
    files_generated: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_formats(fmt_str: str) -> list[OutputFormat]:
    """Turn a format string into a list of OutputFormat enums."""
    fmt_str = fmt_str.lower().strip()
    if fmt_str == "all":
        return [
            OutputFormat.WORD, OutputFormat.PDF, OutputFormat.PPTX,
            OutputFormat.BLOG, OutputFormat.JIRA, OutputFormat.CHANGELOG,
            OutputFormat.LATEX, OutputFormat.ONEPAGER, OutputFormat.SOCIAL,
            OutputFormat.FAQ, OutputFormat.ARCHITECTURE,
        ]
    try:
        return [OutputFormat(fmt_str)]
    except ValueError:
        valid = ", ".join(f.value for f in OutputFormat if f != OutputFormat.ALL)
        raise HTTPException(400, f"Unknown format '{fmt_str}'. Valid: {valid}")


def _build_template_vars(req: GenerateRequest | None = None, **kw) -> TemplateVars | None:
    """Build TemplateVars from request fields."""
    data = {}
    source = {**(req.model_dump() if req else {}), **kw}
    for key in ("project_name", "author", "version", "organisation", "department", "confidentiality"):
        val = source.get(key)
        if val:
            data[key] = val
    if data:
        return TemplateVars(**data)
    return None


def _zip_output_dir(output_dir: Path) -> io.BytesIO:
    """Zip all generated files into an in-memory buffer."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fpath in sorted(output_dir.rglob("*")):
            if fpath.is_file():
                arcname = fpath.relative_to(output_dir)
                zf.write(fpath, arcname)
    buf.seek(0)
    return buf


def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _run_pipeline(
    source: str,
    output_dir: Path,
    *,
    local: bool = False,
    fmt_str: str = "all",
    theme: str = "corporate",
    mode: str = "basic",
    api_key: str | None = None,
    model: str = "gpt-4o-mini",
    provider: str = "openai",
    sort_tables: str = "smart",
    template_vars: TemplateVars | None = None,
) -> int:
    """Run the pipeline and return the number of files generated."""
    formats = _resolve_formats(fmt_str)
    result = _pipeline.run(
        source,
        output_dir=output_dir,
        formats=formats,
        local=local,
        theme_name=theme,
        mode=mode,
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        model=model,
        provider=provider,
        sort_tables=sort_tables,
        template_vars=template_vars,
    )
    return sum(1 for r in result.results if r.success)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", tags=["Info"])
def root():
    """Welcome endpoint with API info."""
    return {
        "service": "OpenDocs API",
        "version": __version__,
        "docs": "/docs",
        "endpoints": {
            "GET /health": "Health check",
            "GET /formats": "List output formats",
            "GET /themes": "List available themes",
            "POST /generate": "Generate docs from URL or Markdown",
            "POST /generate/upload": "Generate docs from uploaded file",
        },
    }


@app.get("/health", tags=["Info"])
def health():
    """Health check for Railway / load balancers."""
    return {"status": "ok", "version": __version__}


@app.get("/formats", tags=["Info"])
def formats():
    """List all available output formats."""
    return {
        "formats": [
            {"name": f.value, "description": f.value.upper()}
            for f in OutputFormat
            if f != OutputFormat.ALL
        ]
    }


@app.get("/themes", tags=["Info"])
def themes():
    """List all available themes."""
    return {
        "themes": [
            {"name": t.name, "description": t.description}
            for t in list_themes()
        ]
    }


@app.post("/generate", tags=["Generate"])
def generate(req: GenerateRequest):
    """Generate documentation from a GitHub URL or raw Markdown.

    Returns a ZIP file containing all generated documents.
    """
    job_id = uuid.uuid4().hex[:12]
    output_dir = _TEMP_ROOT / job_id

    try:
        is_url = _is_url(req.source)
        tvars = _build_template_vars(req)

        if is_url:
            # GitHub URL
            n_files = _run_pipeline(
                req.source, output_dir,
                fmt_str=req.format, theme=req.theme,
                mode=req.mode, api_key=req.api_key,
                model=req.model, provider=req.provider,
                sort_tables=req.sort_tables, template_vars=tvars,
            )
        else:
            # Raw Markdown content — write to temp file
            md_path = output_dir / "_input.md"
            output_dir.mkdir(parents=True, exist_ok=True)
            md_path.write_text(req.source, encoding="utf-8")
            n_files = _run_pipeline(
                str(md_path), output_dir, local=True,
                fmt_str=req.format, theme=req.theme,
                mode=req.mode, api_key=req.api_key,
                model=req.model, provider=req.provider,
                sort_tables=req.sort_tables, template_vars=tvars,
            )

        if n_files == 0:
            raise HTTPException(500, "Pipeline produced no output files.")

        zip_buf = _zip_output_dir(output_dir)

        return StreamingResponse(
            zip_buf,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="opendocs-{job_id}.zip"',
                "X-OpenDocs-Job": job_id,
                "X-OpenDocs-Files": str(n_files),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Generation failed: {exc}")
    finally:
        # Clean up temp files
        if output_dir.exists():
            shutil.rmtree(output_dir, ignore_errors=True)


@app.post("/generate/upload", tags=["Generate"])
async def generate_upload(
    file: UploadFile = File(..., description="Markdown (.md) or Jupyter Notebook (.ipynb) file"),
    format: str = Form("all"),
    theme: str = Form("corporate"),
    mode: str = Form("basic"),
    provider: str = Form("openai"),
    model: str = Form("gpt-4o-mini"),
    api_key: Optional[str] = Form(None),
    sort_tables: str = Form("smart"),
    project_name: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    version: Optional[str] = Form(None),
    organisation: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    confidentiality: Optional[str] = Form(None),
):
    """Generate documentation from an uploaded .md or .ipynb file.

    Returns a ZIP file containing all generated documents.
    """
    if not file.filename:
        raise HTTPException(400, "No file uploaded.")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".md", ".markdown", ".ipynb"):
        raise HTTPException(400, f"Unsupported file type '{ext}'. Upload .md or .ipynb files.")

    job_id = uuid.uuid4().hex[:12]
    output_dir = _TEMP_ROOT / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Save uploaded file
        upload_path = output_dir / file.filename
        content = await file.read()
        upload_path.write_bytes(content)

        tvars = _build_template_vars(
            project_name=project_name, author=author, version=version,
            organisation=organisation, department=department,
            confidentiality=confidentiality,
        )

        n_files = _run_pipeline(
            str(upload_path), output_dir, local=True,
            fmt_str=format, theme=theme,
            mode=mode, api_key=api_key,
            model=model, provider=provider,
            sort_tables=sort_tables, template_vars=tvars,
        )

        if n_files == 0:
            raise HTTPException(500, "Pipeline produced no output files.")

        zip_buf = _zip_output_dir(output_dir)

        return StreamingResponse(
            zip_buf,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="opendocs-{job_id}.zip"',
                "X-OpenDocs-Job": job_id,
                "X-OpenDocs-Files": str(n_files),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Generation failed: {exc}")
    finally:
        if output_dir.exists():
            shutil.rmtree(output_dir, ignore_errors=True)
