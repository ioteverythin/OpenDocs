"""Analysis tools — tech-stack detection, command extraction, file summarisation."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .repo_tools import RepoTools

logger = logging.getLogger("docagent.tools.analysis")

# ---------------------------------------------------------------------------
# Well-known config → tech mapping
# ---------------------------------------------------------------------------
_TECH_SIGNALS: dict[str, list[str]] = {
    "package.json": ["Node.js"],
    "tsconfig.json": ["TypeScript"],
    "requirements.txt": ["Python"],
    "pyproject.toml": ["Python"],
    "setup.py": ["Python"],
    "Pipfile": ["Python", "Pipenv"],
    "Cargo.toml": ["Rust"],
    "go.mod": ["Go"],
    "pom.xml": ["Java", "Maven"],
    "build.gradle": ["Java", "Gradle"],
    "Gemfile": ["Ruby"],
    "Dockerfile": ["Docker"],
    "docker-compose.yml": ["Docker", "Docker Compose"],
    "docker-compose.yaml": ["Docker", "Docker Compose"],
    ".github/workflows": ["GitHub Actions"],
    "Makefile": ["Make"],
    "next.config.js": ["Next.js"],
    "next.config.mjs": ["Next.js"],
    "vite.config.ts": ["Vite"],
    "vite.config.js": ["Vite"],
    "angular.json": ["Angular"],
    "vue.config.js": ["Vue.js"],
    "tailwind.config.js": ["Tailwind CSS"],
    "prisma/schema.prisma": ["Prisma"],
    "terraform": ["Terraform"],
    "serverless.yml": ["Serverless Framework"],
    "k8s": ["Kubernetes"],
    "kubernetes": ["Kubernetes"],
    "helm": ["Helm"],
}

_FRAMEWORK_PATTERNS: dict[str, str] = {
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "express": "Express.js",
    "nestjs": "NestJS",
    "spring": "Spring",
    "react": "React",
    "svelte": "Svelte",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "transformers": "Hugging Face Transformers",
    "langchain": "LangChain",
    "openai": "OpenAI SDK",
    "streamlit": "Streamlit",
    "gradio": "Gradio",
}


class AnalysisTools:
    """Higher-level repository analysis built on RepoTools."""

    def __init__(self, repo_tools: RepoTools) -> None:
        self._repo = repo_tools

    # ------------------------------------------------------------------
    # repo.detect_stack
    # ------------------------------------------------------------------
    def detect_stack(self) -> list[str]:
        """Detect the technology stack from the repository contents."""
        files = self._repo.list_files()
        stack: set[str] = set()

        # 1. Check for well-known config files
        file_set = {f.replace("\\", "/") for f in files}
        for signal, techs in _TECH_SIGNALS.items():
            for f in file_set:
                if f == signal or f.endswith("/" + signal) or f.startswith(signal):
                    stack.update(techs)

        # 2. Parse dependency files for framework detection
        stack.update(self._detect_python_deps(file_set))
        stack.update(self._detect_node_deps(file_set))

        # 3. Detect by file extensions
        ext_map = {".py": "Python", ".ts": "TypeScript", ".js": "JavaScript",
                   ".go": "Go", ".rs": "Rust", ".java": "Java", ".rb": "Ruby",
                   ".cs": "C#", ".cpp": "C++", ".c": "C", ".swift": "Swift",
                   ".kt": "Kotlin", ".scala": "Scala", ".r": "R"}
        for f in files:
            ext = Path(f).suffix.lower()
            if ext in ext_map:
                stack.add(ext_map[ext])

        logger.info("Detected stack: %s", stack)
        return sorted(stack)

    def _detect_python_deps(self, file_set: set[str]) -> set[str]:
        """Scan Python dependency files for frameworks."""
        found: set[str] = set()
        dep_files = [f for f in file_set
                     if f.endswith("requirements.txt") or f == "pyproject.toml"
                     or f == "setup.py" or f == "Pipfile"]
        for df in dep_files:
            try:
                content = self._repo.read_file(df).lower()
            except Exception:
                continue
            for pattern, name in _FRAMEWORK_PATTERNS.items():
                if pattern in content:
                    found.add(name)
        return found

    def _detect_node_deps(self, file_set: set[str]) -> set[str]:
        """Scan package.json for frameworks."""
        found: set[str] = set()
        for f in file_set:
            if not f.endswith("package.json"):
                continue
            try:
                content = self._repo.read_file(f)
                data = json.loads(content)
            except Exception:
                continue
            all_deps = list((data.get("dependencies") or {}).keys())
            all_deps += list((data.get("devDependencies") or {}).keys())
            dep_str = " ".join(all_deps).lower()
            for pattern, name in _FRAMEWORK_PATTERNS.items():
                if pattern in dep_str:
                    found.add(name)
        return found

    # ------------------------------------------------------------------
    # repo.extract_commands
    # ------------------------------------------------------------------
    def extract_commands(self) -> dict[str, list[str]]:
        """Extract install/run commands from README and config files.

        Returns ``{"install": [...], "run": [...], "test": [...], "build": [...]}``.
        """
        commands: dict[str, list[str]] = {
            "install": [], "run": [], "test": [], "build": [],
        }

        # --- README ---
        try:
            readme = self._find_readme()
            if readme:
                self._extract_commands_from_md(readme, commands)
        except Exception:
            pass

        # --- package.json scripts ---
        try:
            pkg = self._repo.read_file("package.json")
            data = json.loads(pkg)
            scripts = data.get("scripts", {})
            for key, val in scripts.items():
                if "install" in key:
                    commands["install"].append(f"npm run {key}")
                elif "start" in key or "dev" in key or "serve" in key:
                    commands["run"].append(f"npm run {key}")
                elif "test" in key:
                    commands["test"].append(f"npm run {key}")
                elif "build" in key:
                    commands["build"].append(f"npm run {key}")
        except Exception:
            pass

        # --- Makefile targets ---
        try:
            mk = self._repo.read_file("Makefile")
            for m in re.finditer(r"^(\w[\w-]*):", mk, re.MULTILINE):
                target = m.group(1)
                if target in ("install", "setup"):
                    commands["install"].append(f"make {target}")
                elif target in ("run", "start", "serve", "dev"):
                    commands["run"].append(f"make {target}")
                elif target in ("test", "check"):
                    commands["test"].append(f"make {target}")
                elif target in ("build", "compile", "dist"):
                    commands["build"].append(f"make {target}")
        except Exception:
            pass

        return commands

    def _find_readme(self) -> str:
        """Find and read the README."""
        for name in ("README.md", "readme.md", "Readme.md", "README.rst", "README"):
            try:
                return self._repo.read_file(name)
            except FileNotFoundError:
                continue
        return ""

    def _extract_commands_from_md(self, md: str, commands: dict) -> None:
        """Extract shell commands from fenced code blocks in Markdown."""
        in_block = False
        lang = ""
        block_lines: list[str] = []
        for line in md.splitlines():
            if line.strip().startswith("```"):
                if in_block:
                    # End of block
                    if lang in ("bash", "sh", "shell", "console", ""):
                        cmd_text = "\n".join(block_lines).strip()
                        if cmd_text:
                            self._classify_command(cmd_text, commands)
                    in_block = False
                    block_lines = []
                else:
                    lang = line.strip().lstrip("`").strip().lower()
                    in_block = True
            elif in_block:
                block_lines.append(line)

    @staticmethod
    def _classify_command(cmd: str, commands: dict) -> None:
        """Classify a command string into install/run/test/build."""
        lower = cmd.lower()
        if any(kw in lower for kw in ("pip install", "npm install", "yarn add",
                                       "cargo install", "go install", "apt-get")):
            commands["install"].append(cmd)
        elif any(kw in lower for kw in ("pytest", "npm test", "cargo test",
                                         "go test", "unittest")):
            commands["test"].append(cmd)
        elif any(kw in lower for kw in ("npm run build", "cargo build",
                                         "go build", "make build", "docker build")):
            commands["build"].append(cmd)
        elif any(kw in lower for kw in ("python", "npm start", "npm run",
                                         "node", "cargo run", "go run",
                                         "uvicorn", "gunicorn", "flask run")):
            commands["run"].append(cmd)

    # ------------------------------------------------------------------
    # repo.summarize_file
    # ------------------------------------------------------------------
    def summarize_file(self, path: str, max_lines: int = 50) -> str:
        """Produce a deterministic summary of a source file.

        Returns the first *max_lines* lines plus structural info
        (classes, functions, imports).
        """
        content = self._repo.read_file(path)
        lines = content.splitlines()
        head = "\n".join(lines[:max_lines])

        ext = Path(path).suffix.lower()
        structures: list[str] = []

        if ext == ".py":
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("class ") or stripped.startswith("def "):
                    structures.append(stripped.split("(")[0].split(":")[0])
                elif stripped.startswith(("import ", "from ")):
                    structures.append(stripped)
        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            for line in lines:
                stripped = line.strip()
                if stripped.startswith(("export ", "function ", "class ", "const ", "import ")):
                    structures.append(stripped[:120])

        summary_parts = [f"=== {path} ({len(lines)} lines) ==="]
        if structures:
            summary_parts.append("Structures: " + " | ".join(structures[:30]))
        summary_parts.append(head)
        return "\n".join(summary_parts)
