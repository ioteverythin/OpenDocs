"""Codebase analyzer — walk a source tree and build a structured understanding.

Scans Python, JavaScript, TypeScript, Go, Rust, Java, and other source
files.  Extracts:

- File / module inventory with line counts
- Classes, functions, their docstrings
- Import / dependency graph
- Technology & framework detection
- Architecture patterns (layers, services, etc.)
- Entry points and configuration files

The output is a ``CodebaseModel`` that can be converted to Markdown or
fed directly into the existing ``DocumentModel`` pipeline.
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_IGNORE_DIRS: set[str] = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".tox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "site-packages",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".next",
    ".nuxt",
    "target",
    "out",
    ".idea",
    ".vscode",
    ".eggs",
    "egg-info",
    "htmlcov",
    "coverage",
    ".cargo",
}

_SOURCE_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".scala": "scala",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "c++",
    ".h": "c",
    ".hpp": "c++",
    ".cs": "c#",
    ".swift": "swift",
    ".dart": "dart",
    ".lua": "lua",
    ".r": "r",
    ".R": "r",
    ".ex": "elixir",
    ".exs": "elixir",
    ".sh": "shell",
    ".bash": "shell",
}

_CONFIG_FILES: set[str] = {
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "Pipfile",
    "poetry.lock",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "tsconfig.json",
    "webpack.config.js",
    "vite.config.ts",
    "vite.config.js",
    "Cargo.toml",
    "go.mod",
    "Gemfile",
    "composer.json",
    "build.gradle",
    "pom.xml",
    "Makefile",
    "CMakeLists.txt",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".env.example",
    ".env.sample",
    "Procfile",
    "railway.toml",
    "vercel.json",
    "netlify.toml",
    "fly.toml",
    "render.yaml",
}

_TEST_PATTERNS = re.compile(r"(^test_|_test\.py$|\.test\.|\.spec\.|__tests__)", re.IGNORECASE)

# Tech detection patterns in import statements / content
_TECH_PATTERNS: dict[str, dict] = {
    # Python frameworks
    "fastapi": {"name": "FastAPI", "category": "Web Framework", "lang": "python"},
    "flask": {"name": "Flask", "category": "Web Framework", "lang": "python"},
    "django": {"name": "Django", "category": "Web Framework", "lang": "python"},
    "starlette": {"name": "Starlette", "category": "Web Framework", "lang": "python"},
    "celery": {"name": "Celery", "category": "Task Queue", "lang": "python"},
    "sqlalchemy": {"name": "SQLAlchemy", "category": "ORM", "lang": "python"},
    "pydantic": {"name": "Pydantic", "category": "Data Validation", "lang": "python"},
    "pytest": {"name": "Pytest", "category": "Testing", "lang": "python"},
    "click": {"name": "Click", "category": "CLI Framework", "lang": "python"},
    "typer": {"name": "Typer", "category": "CLI Framework", "lang": "python"},
    "rich": {"name": "Rich", "category": "Terminal UI", "lang": "python"},
    "httpx": {"name": "HTTPX", "category": "HTTP Client", "lang": "python"},
    "requests": {"name": "Requests", "category": "HTTP Client", "lang": "python"},
    "aiohttp": {"name": "aiohttp", "category": "Async HTTP", "lang": "python"},
    "openai": {"name": "OpenAI SDK", "category": "AI/LLM", "lang": "python"},
    "anthropic": {"name": "Anthropic SDK", "category": "AI/LLM", "lang": "python"},
    "langchain": {"name": "LangChain", "category": "AI/LLM Framework", "lang": "python"},
    "langgraph": {"name": "LangGraph", "category": "AI/LLM Framework", "lang": "python"},
    "transformers": {"name": "Hugging Face Transformers", "category": "AI/ML", "lang": "python"},
    "torch": {"name": "PyTorch", "category": "AI/ML", "lang": "python"},
    "tensorflow": {"name": "TensorFlow", "category": "AI/ML", "lang": "python"},
    "numpy": {"name": "NumPy", "category": "Scientific Computing", "lang": "python"},
    "pandas": {"name": "Pandas", "category": "Data Analysis", "lang": "python"},
    "scikit-learn": {"name": "scikit-learn", "category": "Machine Learning", "lang": "python"},
    "sklearn": {"name": "scikit-learn", "category": "Machine Learning", "lang": "python"},
    "uvicorn": {"name": "Uvicorn", "category": "ASGI Server", "lang": "python"},
    "gunicorn": {"name": "Gunicorn", "category": "WSGI Server", "lang": "python"},
    "alembic": {"name": "Alembic", "category": "Database Migrations", "lang": "python"},
    "redis": {"name": "Redis", "category": "Cache/Message Broker", "lang": "python"},
    "boto3": {"name": "AWS SDK (boto3)", "category": "Cloud SDK", "lang": "python"},
    "google.cloud": {"name": "Google Cloud SDK", "category": "Cloud SDK", "lang": "python"},
    "azure": {"name": "Azure SDK", "category": "Cloud SDK", "lang": "python"},
    "reportlab": {"name": "ReportLab", "category": "PDF Generation", "lang": "python"},
    "python-docx": {"name": "python-docx", "category": "Word Generation", "lang": "python"},
    "docx": {"name": "python-docx", "category": "Word Generation", "lang": "python"},
    "python-pptx": {"name": "python-pptx", "category": "PowerPoint Generation", "lang": "python"},
    "pptx": {"name": "python-pptx", "category": "PowerPoint Generation", "lang": "python"},
    "mistune": {"name": "Mistune", "category": "Markdown Parser", "lang": "python"},
    "matplotlib": {"name": "Matplotlib", "category": "Visualization", "lang": "python"},
    "websocket": {"name": "WebSocket", "category": "Real-time Communication", "lang": "python"},
    "websockets": {"name": "WebSockets", "category": "Real-time Communication", "lang": "python"},
    "socketio": {"name": "Socket.IO", "category": "Real-time Communication", "lang": "python"},
    # JS/TS frameworks
    "react": {"name": "React", "category": "Frontend Framework", "lang": "javascript"},
    "vue": {"name": "Vue.js", "category": "Frontend Framework", "lang": "javascript"},
    "angular": {"name": "Angular", "category": "Frontend Framework", "lang": "javascript"},
    "express": {"name": "Express.js", "category": "Web Framework", "lang": "javascript"},
    "next": {"name": "Next.js", "category": "Fullstack Framework", "lang": "javascript"},
    "nestjs": {"name": "NestJS", "category": "Backend Framework", "lang": "typescript"},
    "prisma": {"name": "Prisma", "category": "ORM", "lang": "typescript"},
    "mongoose": {"name": "Mongoose", "category": "ODM", "lang": "javascript"},
    "jest": {"name": "Jest", "category": "Testing", "lang": "javascript"},
    "vitest": {"name": "Vitest", "category": "Testing", "lang": "javascript"},
    "tailwindcss": {"name": "Tailwind CSS", "category": "CSS Framework", "lang": "javascript"},
}

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class FunctionInfo:
    """Extracted function/method metadata."""

    name: str
    docstring: str = ""
    args: list[str] = field(default_factory=list)
    return_type: str = ""
    is_async: bool = False
    decorators: list[str] = field(default_factory=list)
    line_number: int = 0
    line_count: int = 0


@dataclass
class ClassInfo:
    """Extracted class metadata."""

    name: str
    docstring: str = ""
    bases: list[str] = field(default_factory=list)
    methods: list[FunctionInfo] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    line_number: int = 0
    line_count: int = 0


@dataclass
class FileAnalysis:
    """Analysis of a single source file."""

    path: str  # relative to project root
    language: str
    line_count: int = 0
    blank_lines: int = 0
    comment_lines: int = 0
    code_lines: int = 0
    module_docstring: str = ""
    imports: list[str] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    is_test: bool = False
    is_config: bool = False
    is_entry_point: bool = False
    summary: str = ""  # one-line description


@dataclass
class TechStackItem:
    """A detected technology / library."""

    name: str
    category: str
    language: str = ""
    confidence: float = 1.0
    source_files: list[str] = field(default_factory=list)


@dataclass
class ArchitectureLayer:
    """A logical architecture layer with its components."""

    name: str
    description: str
    modules: list[str] = field(default_factory=list)


@dataclass
class CodebaseModel:
    """Complete structured analysis of a codebase."""

    project_name: str
    root_path: str
    total_files: int = 0
    total_lines: int = 0
    total_code_lines: int = 0
    languages: dict[str, int] = field(default_factory=dict)  # lang → file count
    files: list[FileAnalysis] = field(default_factory=list)
    tech_stack: list[TechStackItem] = field(default_factory=list)
    architecture_layers: list[ArchitectureLayer] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    description: str = ""  # from README first line, pyproject, package.json etc.
    version: str = ""
    license: str = ""
    dependencies: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def _iter_source_files(root: Path) -> Iterator[Path]:
    """Yield source files from *root*, skipping ignored directories."""
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories in-place
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS and not d.endswith(".egg-info")]
        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() in _SOURCE_EXTENSIONS or fname in _CONFIG_FILES:
                yield fpath


# ---------------------------------------------------------------------------
# Python AST analysis
# ---------------------------------------------------------------------------


def _analyze_python(source: str, rel_path: str) -> FileAnalysis:
    """Deep analysis of a Python file using AST."""
    lines = source.splitlines()
    total = len(lines)
    blank = sum(1 for ln in lines if not ln.strip())
    comment = sum(1 for ln in lines if ln.strip().startswith("#"))

    fa = FileAnalysis(
        path=rel_path,
        language="python",
        line_count=total,
        blank_lines=blank,
        comment_lines=comment,
        code_lines=max(0, total - blank - comment),
    )

    # Detect test file
    fa.is_test = bool(_TEST_PATTERNS.search(rel_path))

    # Detect entry point
    if "__main__" in rel_path or "cli.py" in rel_path or "main.py" in rel_path:
        fa.is_entry_point = True

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return fa

    # Module docstring
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant):
        ds = getattr(tree.body[0].value, "value", None)
        if isinstance(ds, str):
            fa.module_docstring = ds.strip()
            # Use first line as summary
            fa.summary = ds.strip().split("\n")[0].rstrip(".")

    # Imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                fa.imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                fa.imports.append(node.module)

    # Top-level classes
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            ci = ClassInfo(
                name=node.name,
                line_number=node.lineno,
                line_count=node.end_lineno - node.lineno + 1 if node.end_lineno else 0,
                bases=[_ast_name(b) for b in node.bases],
                decorators=[_ast_name(d) for d in node.decorator_list],
            )
            # Class docstring
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                ds = getattr(node.body[0].value, "value", None)
                if isinstance(ds, str):
                    ci.docstring = ds.strip()

            # Methods
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fi = _extract_func(item)
                    ci.methods.append(fi)

            fa.classes.append(ci)

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fi = _extract_func(node)
            fa.functions.append(fi)

            # Detect entry-point patterns
            if node.name == "main":
                fa.is_entry_point = True

    return fa


def _extract_func(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
    """Extract metadata from a function/method AST node."""
    fi = FunctionInfo(
        name=node.name,
        is_async=isinstance(node, ast.AsyncFunctionDef),
        line_number=node.lineno,
        line_count=node.end_lineno - node.lineno + 1 if node.end_lineno else 0,
        decorators=[_ast_name(d) for d in node.decorator_list],
    )

    # Docstring
    if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
        ds = getattr(node.body[0].value, "value", None)
        if isinstance(ds, str):
            fi.docstring = ds.strip()

    # Args
    for arg in node.args.args:
        fi.args.append(arg.arg)

    # Return annotation
    if node.returns:
        fi.return_type = _ast_name(node.returns)

    return fi


def _ast_name(node) -> str:
    """Get a printable name from an AST node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_ast_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Subscript):
        return f"{_ast_name(node.value)}[{_ast_name(node.slice)}]"
    if isinstance(node, ast.Call):
        return _ast_name(node.func)
    if isinstance(node, ast.Tuple):
        return ", ".join(_ast_name(e) for e in node.elts)
    return ast.dump(node) if hasattr(ast, "dump") else str(node)


# ---------------------------------------------------------------------------
# Generic (non-Python) analysis
# ---------------------------------------------------------------------------


def _analyze_generic(source: str, rel_path: str, language: str) -> FileAnalysis:
    """Basic analysis for non-Python source files."""
    lines = source.splitlines()
    total = len(lines)
    blank = sum(1 for ln in lines if not ln.strip())

    # Rough comment detection
    comment = 0
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("//") or stripped.startswith("#") or stripped.startswith("*"):
            comment += 1

    fa = FileAnalysis(
        path=rel_path,
        language=language,
        line_count=total,
        blank_lines=blank,
        comment_lines=comment,
        code_lines=max(0, total - blank - comment),
        is_test=bool(_TEST_PATTERNS.search(rel_path)),
    )

    # Extract imports (simple patterns)
    import_patterns = [
        re.compile(r"^import\s+(.+)", re.MULTILINE),
        re.compile(r"^from\s+(\S+)\s+import", re.MULTILINE),
        re.compile(r"require\(['\"]([^'\"]+)['\"]\)", re.MULTILINE),
        re.compile(r"import\s+.*\s+from\s+['\"]([^'\"]+)['\"]", re.MULTILINE),
        re.compile(r"^use\s+(\S+)", re.MULTILINE),  # Rust
        re.compile(r'^\s*#include\s*[<"]([^>"]+)[>"]', re.MULTILINE),  # C/C++
    ]
    for pat in import_patterns:
        for m in pat.finditer(source):
            fa.imports.append(m.group(1).strip().rstrip(";"))

    # First comment block as summary
    for ln in lines[:20]:
        stripped = ln.strip()
        if stripped.startswith("//") or stripped.startswith("#"):
            text = stripped.lstrip("/#").strip()
            if text and len(text) > 10:
                fa.summary = text
                break
        elif stripped.startswith("/*") or stripped.startswith('"""'):
            text = stripped.strip("/*").strip('"""').strip()
            if text and len(text) > 10:
                fa.summary = text
                break

    # ------------------------------------------------------------------
    # Regex-based class & function extraction for common languages
    # ------------------------------------------------------------------
    _extract_classes_funcs_generic(source, language, fa)

    return fa


# Pre-compiled patterns for generic class/function extraction
_CPP_CLASS_RE = re.compile(
    r"^\s*(?:class|struct)\s+(\w+)\s*(?::\s*((?:public|protected|private)\s+\w+(?:\s*,\s*(?:public|protected|private)\s+\w+)*))?",
    re.MULTILINE,
)
_CPP_METHOD_RE = re.compile(
    r"^\s*(?:virtual\s+|static\s+|inline\s+|explicit\s+|constexpr\s+)*"
    r"(?:[\w:*&<>\s]+?)\s+(\w+)\s*\([^)]*\)",
    re.MULTILINE,
)
_CPP_FUNC_RE = re.compile(
    r"^(?:[\w:*&<>\s]+?)\s+(\w+)\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)
_JS_CLASS_RE = re.compile(
    r"^\s*(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?",
    re.MULTILINE,
)
_JS_FUNC_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(",
    re.MULTILINE,
)
_JS_ARROW_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(",
    re.MULTILINE,
)
_JAVA_CLASS_RE = re.compile(
    r"^\s*(?:public\s+|private\s+|protected\s+)?(?:abstract\s+)?(?:class|interface|enum)\s+(\w+)(?:\s+extends\s+(\w+))?",
    re.MULTILINE,
)

# C/C++ keywords and types to ignore as false-positive function names
_CPP_KEYWORDS = frozenset(
    {
        "if",
        "else",
        "for",
        "while",
        "do",
        "switch",
        "case",
        "return",
        "break",
        "continue",
        "goto",
        "try",
        "catch",
        "throw",
        "new",
        "delete",
        "sizeof",
        "typedef",
        "using",
        "namespace",
        "class",
        "struct",
        "enum",
        "union",
        "public",
        "private",
        "protected",
        "virtual",
        "override",
        "final",
        "const",
        "static",
        "extern",
        "inline",
        "volatile",
        "register",
        "template",
        "typename",
        "define",
        "include",
        "ifdef",
        "ifndef",
        "endif",
        "elif",
        "pragma",
        "PROGMEM",
        "IRAM_ATTR",
    }
)


def _extract_classes_funcs_generic(source: str, language: str, fa: "FileAnalysis") -> None:
    """Extract classes and functions for non-Python languages using regex."""
    lang_lower = language.lower()

    if lang_lower in ("c", "c++"):
        _extract_cpp(source, fa)
    elif lang_lower in ("javascript", "typescript"):
        _extract_js_ts(source, fa)
    elif lang_lower == "java":
        _extract_java(source, fa)


def _extract_cpp(source: str, fa: "FileAnalysis") -> None:
    """Extract C/C++ classes/structs and top-level functions."""
    # Classes & structs
    for m in _CPP_CLASS_RE.finditer(source):
        name = m.group(1)
        bases: list[str] = []
        if m.group(2):
            for b in m.group(2).split(","):
                b = b.strip()
                # Remove access specifier (public/protected/private)
                parts = b.split()
                bases.append(parts[-1] if parts else b)

        ci = ClassInfo(name=name, bases=bases, line_number=source[: m.start()].count("\n") + 1)

        # Scan the block after the class/struct for methods
        # Find the opening brace
        brace_start = source.find("{", m.end())
        if brace_start >= 0:
            depth = 1
            pos = brace_start + 1
            block_end = len(source)
            while pos < len(source) and depth > 0:
                if source[pos] == "{":
                    depth += 1
                elif source[pos] == "}":
                    depth -= 1
                pos += 1
            block_end = pos
            class_body = source[brace_start:block_end]

            for fm in _CPP_METHOD_RE.finditer(class_body):
                fname = fm.group(1)
                if fname not in _CPP_KEYWORDS and not fname.startswith("_"):
                    ci.methods.append(FunctionInfo(name=fname))

        fa.classes.append(ci)

    # Top-level functions (outside classes) — simpler pattern
    for m in _CPP_FUNC_RE.finditer(source):
        fname = m.group(1)
        if fname not in _CPP_KEYWORDS and fname not in {c.name for c in fa.classes}:
            fa.functions.append(
                FunctionInfo(
                    name=fname,
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )


def _extract_js_ts(source: str, fa: "FileAnalysis") -> None:
    """Extract JavaScript/TypeScript classes and functions."""
    for m in _JS_CLASS_RE.finditer(source):
        ci = ClassInfo(
            name=m.group(1),
            bases=[m.group(2)] if m.group(2) else [],
            line_number=source[: m.start()].count("\n") + 1,
        )
        fa.classes.append(ci)

    seen_funcs: set[str] = set()
    for pattern in (_JS_FUNC_RE, _JS_ARROW_RE):
        for m in pattern.finditer(source):
            fname = m.group(1)
            if fname not in seen_funcs:
                seen_funcs.add(fname)
                fa.functions.append(
                    FunctionInfo(
                        name=fname,
                        is_async="async" in source[max(0, m.start() - 20) : m.start()],
                        line_number=source[: m.start()].count("\n") + 1,
                    )
                )


def _extract_java(source: str, fa: "FileAnalysis") -> None:
    """Extract Java classes/interfaces."""
    for m in _JAVA_CLASS_RE.finditer(source):
        ci = ClassInfo(
            name=m.group(1),
            bases=[m.group(2)] if m.group(2) else [],
            line_number=source[: m.start()].count("\n") + 1,
        )
        fa.classes.append(ci)


# ---------------------------------------------------------------------------
# Config file analysis
# ---------------------------------------------------------------------------


def _analyze_config(root: Path, rel_path: str, content: str) -> dict:
    """Extract metadata from config files (pyproject.toml, package.json, etc.)."""
    info: dict = {}
    fname = Path(rel_path).name

    if fname == "pyproject.toml":
        # Simple regex extraction (avoid toml dependency)
        m = re.search(r'^description\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if m:
            info["description"] = m.group(1)
        m = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if m:
            info["version"] = m.group(1)
        m = re.search(r'^name\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if m:
            info["name"] = m.group(1)
        m = re.search(r'license\s*=\s*\{text\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if m:
            info["license"] = m.group(1)
        # Dependencies
        deps = re.findall(r'^\s+"([a-zA-Z0-9_-]+)', content, re.MULTILINE)
        if deps:
            info["dependencies"] = list(set(deps))

    elif fname == "package.json":
        m = re.search(r'"description"\s*:\s*"([^"]+)"', content)
        if m:
            info["description"] = m.group(1)
        m = re.search(r'"version"\s*:\s*"([^"]+)"', content)
        if m:
            info["version"] = m.group(1)
        m = re.search(r'"name"\s*:\s*"([^"]+)"', content)
        if m:
            info["name"] = m.group(1)
        m = re.search(r'"license"\s*:\s*"([^"]+)"', content)
        if m:
            info["license"] = m.group(1)

    elif fname == "Cargo.toml":
        m = re.search(r'^description\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if m:
            info["description"] = m.group(1)
        m = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if m:
            info["version"] = m.group(1)

    elif fname == "requirements.txt":
        deps = []
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                pkg = re.split(r"[>=<!\[]", line)[0].strip()
                if pkg:
                    deps.append(pkg)
        info["dependencies"] = deps

    return info


# ---------------------------------------------------------------------------
# Tech stack detection
# ---------------------------------------------------------------------------


def _detect_tech_stack(files: list[FileAnalysis]) -> list[TechStackItem]:
    """Detect technologies from imports and file patterns."""
    tech_hits: dict[str, TechStackItem] = {}

    all_imports: set[str] = set()
    for fa in files:
        for imp in fa.imports:
            # Normalize: take the root package
            root_pkg = imp.split(".")[0].lower().replace("-", "").replace("_", "")
            all_imports.add(root_pkg)
            all_imports.add(imp.lower())

    for key, info in _TECH_PATTERNS.items():
        normalized = key.lower().replace("-", "").replace("_", "")
        if normalized in all_imports or key in all_imports:
            if info["name"] not in tech_hits:
                tech_hits[info["name"]] = TechStackItem(
                    name=info["name"],
                    category=info["category"],
                    language=info.get("lang", ""),
                )
            # Track which files use it
            for fa in files:
                for imp in fa.imports:
                    if key in imp.lower():
                        if fa.path not in tech_hits[info["name"]].source_files:
                            tech_hits[info["name"]].source_files.append(fa.path)

    return sorted(tech_hits.values(), key=lambda t: t.category)


# ---------------------------------------------------------------------------
# Architecture inference
# ---------------------------------------------------------------------------


def _infer_architecture(files: list[FileAnalysis], root: Path) -> list[ArchitectureLayer]:
    """Infer architecture layers from directory structure and file purposes."""
    layers: dict[str, ArchitectureLayer] = {}

    # Group by top-level directory
    dir_files: dict[str, list[FileAnalysis]] = {}
    for fa in files:
        parts = Path(fa.path).parts
        top_dir = parts[0] if len(parts) > 1 else "(root)"
        dir_files.setdefault(top_dir, []).append(fa)

    # Categorize directories into layers
    layer_mapping = {
        "api": ("API Layer", "HTTP endpoints, request handlers, and route definitions"),
        "routes": ("API Layer", "HTTP endpoints, request handlers, and route definitions"),
        "endpoints": ("API Layer", "HTTP endpoints, request handlers, and route definitions"),
        "views": ("API Layer", "View handlers and request processing"),
        "core": ("Core / Business Logic", "Domain models, business rules, and core algorithms"),
        "domain": ("Core / Business Logic", "Domain models, business rules, and core algorithms"),
        "models": ("Data Models", "Data structures, schemas, and type definitions"),
        "schemas": ("Data Models", "Data structures, schemas, and type definitions"),
        "services": ("Service Layer", "Business logic orchestration and service implementations"),
        "generators": ("Output / Generation Layer", "Document generation and output formatting"),
        "templates": ("Presentation Layer", "Templates, views, and UI components"),
        "components": ("Presentation Layer", "UI components and widgets"),
        "static": ("Static Assets", "CSS, JavaScript, images, and other static files"),
        "db": ("Data Access Layer", "Database connections, queries, and migrations"),
        "database": ("Data Access Layer", "Database connections, queries, and migrations"),
        "migrations": ("Data Access Layer", "Database schema migrations"),
        "utils": ("Utilities", "Helper functions, shared utilities, and common tools"),
        "helpers": ("Utilities", "Helper functions, shared utilities, and common tools"),
        "lib": ("Utilities", "Shared library code and utilities"),
        "common": ("Utilities", "Shared library code and utilities"),
        "config": ("Configuration", "Application configuration and settings"),
        "settings": ("Configuration", "Application configuration and settings"),
        "tests": ("Testing", "Unit tests, integration tests, and test fixtures"),
        "test": ("Testing", "Unit tests, integration tests, and test fixtures"),
        "docs": ("Documentation", "Project documentation and guides"),
        "scripts": ("Scripts / Tooling", "Build scripts, deployment scripts, and dev tools"),
        "tools": ("Scripts / Tooling", "Build scripts, deployment scripts, and dev tools"),
        "plugins": ("Plugins / Extensions", "Plugin system and extension modules"),
        "extensions": ("Plugins / Extensions", "Plugin system and extension modules"),
        "skills": ("Plugins / Extensions", "Skill modules and extension points"),
        "middleware": ("Middleware", "Request/response processing pipeline"),
        "auth": ("Authentication & Security", "Authentication, authorization, and security"),
        "security": ("Authentication & Security", "Authentication, authorization, and security"),
        "agents": ("AI / Agent Layer", "AI agents, LLM orchestration, and autonomous workflows"),
        "llm": ("AI / LLM Integration", "LLM provider clients and AI-powered features"),
        "publishers": ("Publishing / Integration", "External service publishing and integrations"),
        "cli": ("CLI Interface", "Command-line interface and argument parsing"),
    }

    for dir_name, dir_file_list in dir_files.items():
        dir_lower = dir_name.lower()
        if dir_lower in layer_mapping:
            layer_name, layer_desc = layer_mapping[dir_lower]
        else:
            # Guess from file content
            layer_name = dir_name.replace("_", " ").replace("-", " ").title()
            layer_desc = f"Modules in the {dir_name}/ directory"

        if layer_name not in layers:
            layers[layer_name] = ArchitectureLayer(
                name=layer_name,
                description=layer_desc,
            )

        for fa in dir_file_list:
            layers[layer_name].modules.append(fa.path)

    return sorted(layers.values(), key=lambda layer: layer.name)


# ---------------------------------------------------------------------------
# Main analyzer
# ---------------------------------------------------------------------------


class CodebaseAnalyzer:
    """Analyze a codebase directory and produce a structured ``CodebaseModel``."""

    def __init__(self, max_file_size: int = 500_000) -> None:
        self.max_file_size = max_file_size

    def analyze(self, root: str | Path) -> CodebaseModel:
        """Walk *root* and return a ``CodebaseModel``."""
        root = Path(root).resolve()
        project_name = root.name

        model = CodebaseModel(
            project_name=project_name,
            root_path=str(root),
        )

        config_meta: dict = {}

        for fpath in _iter_source_files(root):
            rel = str(fpath.relative_to(root)).replace("\\", "/")

            # Read file
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except (OSError, PermissionError):
                continue

            if len(content) > self.max_file_size:
                continue  # skip enormous generated files

            fname = fpath.name

            # Config files
            if fname in _CONFIG_FILES:
                model.config_files.append(rel)
                meta = _analyze_config(root, rel, content)
                if meta:
                    config_meta.update(meta)
                continue

            ext = fpath.suffix.lower()
            lang = _SOURCE_EXTENSIONS.get(ext, "")
            if not lang:
                continue

            # Analyze source file
            if lang == "python":
                fa = _analyze_python(content, rel)
            else:
                fa = _analyze_generic(content, rel, lang)

            model.files.append(fa)
            model.total_files += 1
            model.total_lines += fa.line_count
            model.total_code_lines += fa.code_lines
            model.languages[lang] = model.languages.get(lang, 0) + 1

            if fa.is_test:
                model.test_files.append(rel)
            if fa.is_entry_point:
                model.entry_points.append(rel)

        # Apply config metadata
        model.description = config_meta.get("description", "")
        model.version = config_meta.get("version", "")
        model.license = config_meta.get("license", "")
        if config_meta.get("name"):
            model.project_name = config_meta["name"]
        if config_meta.get("dependencies"):
            model.dependencies = config_meta["dependencies"]

        # Detect tech stack
        model.tech_stack = _detect_tech_stack(model.files)

        # Infer architecture
        model.architecture_layers = _infer_architecture(model.files, root)

        return model


# ---------------------------------------------------------------------------
# Markdown report generation
# ---------------------------------------------------------------------------


def generate_codebase_markdown(model: CodebaseModel) -> str:
    """Convert a ``CodebaseModel`` into a comprehensive Markdown document.

    The output follows a professional technical report structure similar
    to the Dubai AI Voice Agent document style:
    - Title / metadata
    - Executive Summary
    - System Architecture (with Mermaid diagram)
    - Codebase Status (module table)
    - Technology Stack (table)
    - Module Documentation
    - Architecture Diagrams (Mermaid)
    """
    lines: list[str] = []

    # ── Title ──────────────────────────────────────────────────────────
    title = model.project_name or "Project"
    lines.append(f"# {title}")
    lines.append("")
    if model.description:
        lines.append(f"> {model.description}")
        lines.append("")
    if model.version:
        lines.append(f"**Version:** {model.version}")
    if model.license:
        lines.append(f"**License:** {model.license}")
    lines.append(f"**Generated from:** codebase analysis of `{model.root_path}`")
    lines.append("")

    # ── Executive Summary ──────────────────────────────────────────────
    lines.append("## Executive Summary")
    lines.append("")

    lang_summary = ", ".join(
        f"{count} {lang.title()} file{'s' if count > 1 else ''}"
        for lang, count in sorted(model.languages.items(), key=lambda x: -x[1])
    )
    tech_names = [t.name for t in model.tech_stack[:8]]
    tech_summary = ", ".join(tech_names) if tech_names else "standard library"

    lines.append(
        f"The **{title}** codebase consists of **{model.total_files:,} source files** "
        f"comprising **{model.total_code_lines:,} lines of code** "
        f"({lang_summary}). "
        f"The project leverages {tech_summary} as its core technology stack."
    )
    lines.append("")

    src_files = [f for f in model.files if not f.is_test]
    test_count = len(model.test_files)
    lines.append(
        f"The codebase contains **{len(src_files)} source modules** and "
        f"**{test_count} test file{'s' if test_count != 1 else ''}**, "
        f"with **{len(model.config_files)} configuration file{'s' if len(model.config_files) != 1 else ''}** "
        f"and **{len(model.entry_points)} identified entry point{'s' if len(model.entry_points) != 1 else ''}**."
    )
    lines.append("")

    # Top-level module summaries
    top_modules = [f for f in model.files if not f.is_test and f.summary][:6]
    if top_modules:
        lines.append("Key modules include:")
        lines.append("")
        for fa in top_modules:
            lines.append(f"- **{fa.path}** — {fa.summary}")
        lines.append("")

    # ── System Architecture Diagram ────────────────────────────────────
    lines.append("## System Architecture")
    lines.append("")
    lines.append(
        "The architecture spans multiple layers, from entry points and CLI interfaces "
        "through core business logic to output generation and external integrations."
    )
    lines.append("")

    # Generate a Mermaid C4-style architecture diagram
    lines.append("```mermaid")
    lines.append("graph TB")

    # Group layers
    layer_ids: dict[str, str] = {}
    for i, layer in enumerate(model.architecture_layers):
        lid = f"L{i}"
        layer_ids[layer.name] = lid
        safe_name = layer.name.replace('"', "'")
        n_mods = len(layer.modules)
        lines.append(f'    {lid}["{safe_name}<br/><i>{n_mods} module(s)</i>"]')

    # Connect layers (simple top-down flow)
    if len(model.architecture_layers) > 1:
        layer_keys = list(layer_ids.keys())
        for i in range(len(layer_keys) - 1):
            a = layer_ids[layer_keys[i]]
            b = layer_ids[layer_keys[i + 1]]
            lines.append(f"    {a} --> {b}")

    lines.append("```")
    lines.append("")

    # ── Codebase Status ────────────────────────────────────────────────
    lines.append("## Codebase Status")
    lines.append("")
    lines.append("A thorough audit of the codebase reveals the following modules, their purpose, and key metrics.")
    lines.append("")

    # Module table
    lines.append("| Module | Purpose | Lines | Classes | Functions |")
    lines.append("|--------|---------|------:|--------:|----------:|")

    for fa in sorted(model.files, key=lambda f: f.path):
        if fa.is_test:
            continue
        purpose = fa.summary or fa.module_docstring.split("\n")[0][:60] if fa.module_docstring else ""
        if not purpose:
            purpose = f"{fa.language.title()} module"
        n_classes = len(fa.classes)
        n_funcs = len(fa.functions) + sum(len(c.methods) for c in fa.classes)
        lines.append(f"| `{fa.path}` | {purpose} | {fa.line_count} | {n_classes} | {n_funcs} |")

    lines.append("")

    # ── Technology Stack ───────────────────────────────────────────────
    if model.tech_stack:
        lines.append("## Technology Stack")
        lines.append("")
        lines.append("| Technology | Category | Used In |")
        lines.append("|-----------|----------|---------|")

        for tech in model.tech_stack:
            used_in = ", ".join(f"`{f}`" for f in tech.source_files[:3])
            if len(tech.source_files) > 3:
                used_in += f" +{len(tech.source_files) - 3} more"
            lines.append(f"| {tech.name} | {tech.category} | {used_in} |")

        lines.append("")

    # ── Language Breakdown ─────────────────────────────────────────────
    if len(model.languages) > 1:
        lines.append("## Language Breakdown")
        lines.append("")
        lines.append("| Language | Files | Percentage |")
        lines.append("|----------|------:|-----------:|")

        for lang, count in sorted(model.languages.items(), key=lambda x: -x[1]):
            pct = count / model.total_files * 100 if model.total_files else 0
            lines.append(f"| {lang.title()} | {count} | {pct:.1f}% |")

        lines.append("")

    # ── Entry Points ───────────────────────────────────────────────────
    if model.entry_points:
        lines.append("## Entry Points")
        lines.append("")
        for ep in model.entry_points:
            lines.append(f"- `{ep}`")
        lines.append("")

    # ── Architecture Layers ────────────────────────────────────────────
    lines.append("## Architecture Layers")
    lines.append("")

    for layer in model.architecture_layers:
        lines.append(f"### {layer.name}")
        lines.append("")
        lines.append(layer.description)
        lines.append("")

        layer_files = [f for f in model.files if f.path in layer.modules]
        for fa in layer_files:
            class_names = [c.name for c in fa.classes]
            func_names = [f.name for f in fa.functions if not f.name.startswith("_")]
            parts = []
            if class_names:
                parts.append(f"Classes: {', '.join(class_names)}")
            if func_names:
                parts.append(f"Functions: {', '.join(func_names[:5])}")
                if len(func_names) > 5:
                    parts[-1] += f" +{len(func_names) - 5} more"
            detail = " — " + "; ".join(parts) if parts else ""
            lines.append(f"- **`{fa.path}`**{detail}")

        lines.append("")

    # ── Module Documentation ───────────────────────────────────────────
    lines.append("## Module Documentation")
    lines.append("")

    documented_files = [f for f in model.files if not f.is_test and (f.classes or f.functions or f.module_docstring)]

    for fa in documented_files[:30]:  # Cap to avoid enormous docs
        lines.append(f"### `{fa.path}`")
        lines.append("")

        if fa.module_docstring:
            # Truncate very long docstrings
            ds = fa.module_docstring
            if len(ds) > 500:
                ds = ds[:500] + "..."
            lines.append(f"{ds}")
            lines.append("")

        if fa.classes:
            for ci in fa.classes:
                bases = f" ({', '.join(ci.bases)})" if ci.bases else ""
                lines.append(f"**class `{ci.name}`**{bases}")
                if ci.docstring:
                    short_doc = ci.docstring.split("\n")[0]
                    lines.append(f": {short_doc}")
                lines.append("")

                if ci.methods:
                    public_methods = [m for m in ci.methods if not m.name.startswith("_") or m.name == "__init__"]
                    if public_methods:
                        lines.append("| Method | Async | Args | Description |")
                        lines.append("|--------|-------|------|-------------|")
                        for m in public_methods[:10]:
                            is_async = "Yes" if m.is_async else "No"
                            args_str = ", ".join(a for a in m.args if a != "self")[:40]
                            desc = m.docstring.split("\n")[0][:60] if m.docstring else ""
                            lines.append(f"| `{m.name}` | {is_async} | {args_str} | {desc} |")
                        lines.append("")

        if fa.functions:
            public_funcs = [f for f in fa.functions if not f.name.startswith("_")]
            if public_funcs:
                lines.append("| Function | Async | Args | Description |")
                lines.append("|----------|-------|------|-------------|")
                for func in public_funcs[:10]:
                    is_async = "Yes" if func.is_async else "No"
                    args_str = ", ".join(func.args)[:40]
                    desc = func.docstring.split("\n")[0][:60] if func.docstring else ""
                    lines.append(f"| `{func.name}` | {is_async} | {args_str} | {desc} |")
                lines.append("")

    # ── Dependency Graph (Mermaid) ─────────────────────────────────────
    lines.append("## Dependency Graph")
    lines.append("")
    lines.append("Internal module dependency graph based on import analysis:")
    lines.append("")
    lines.append("```mermaid")
    lines.append("graph LR")

    # Build internal dependency edges
    {fa.path for fa in model.files}
    edges: set[tuple[str, str]] = set()
    edge_count = 0
    max_edges = 40

    for fa in model.files:
        if fa.is_test:
            continue
        src_id = _mermaid_id(fa.path)
        for imp in fa.imports:
            # Convert import to potential file path
            imp.replace(".", "/")
            for target in model.files:
                if target.is_test:
                    continue
                target_stem = target.path.replace("/", ".").replace("\\", ".").removesuffix(".py")
                if imp in target_stem or target_stem.endswith(imp):
                    edge = (src_id, _mermaid_id(target.path))
                    if edge not in edges and edge[0] != edge[1]:
                        edges.add(edge)
                        edge_count += 1
                        if edge_count >= max_edges:
                            break
            if edge_count >= max_edges:
                break
        if edge_count >= max_edges:
            break

    node_ids = set()
    for a, b in edges:
        node_ids.add(a)
        node_ids.add(b)

    # Declare nodes with short labels
    for fa in model.files:
        nid = _mermaid_id(fa.path)
        if nid in node_ids:
            label = Path(fa.path).stem
            lines.append(f'    {nid}["{label}"]')

    for a, b in sorted(edges):
        lines.append(f"    {a} --> {b}")

    if not edges:
        lines.append('    root["(no internal cross-imports detected)"]')

    lines.append("```")
    lines.append("")

    # ── Test Coverage Overview ─────────────────────────────────────────
    if model.test_files:
        lines.append("## Test Files")
        lines.append("")
        lines.append("| Test File | Lines |")
        lines.append("|-----------|------:|")
        for fa in model.files:
            if fa.is_test:
                lines.append(f"| `{fa.path}` | {fa.line_count} |")
        lines.append("")

    # ── Configuration Files ────────────────────────────────────────────
    if model.config_files:
        lines.append("## Configuration Files")
        lines.append("")
        for cf in sorted(model.config_files):
            lines.append(f"- `{cf}`")
        lines.append("")

    return "\n".join(lines)


def _mermaid_id(path: str) -> str:
    """Make a path safe for Mermaid node IDs."""
    return path.replace("/", "_").replace("\\", "_").replace(".", "_").replace("-", "_").replace(" ", "_")
