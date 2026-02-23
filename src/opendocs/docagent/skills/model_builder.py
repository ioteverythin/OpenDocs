"""repo.model_builder — build the RepoKnowledgeModel from indexed data."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .base import BaseSkill
from ..models.repo_model import RepoKnowledgeModel, APIEndpoint


class ModelBuilderSkill(BaseSkill):
    """Construct a RepoKnowledgeModel from indexed repository data."""

    name = "repo.model_builder"

    def run(
        self,
        *,
        url: str,
        files: list[str],
        readme: str,
        key_files: dict[str, str],
        tech_stack: list[str],
        commands: dict[str, list[str]],
        index_dir: Path,
        use_llm: bool = False,
        llm_config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> RepoKnowledgeModel:
        """Build and persist the repository knowledge model."""
        self.logger.info("Building repo knowledge model for %s", url)

        # ── LLM-enhanced path ────────────────────────────────────────
        if use_llm:
            try:
                model = self._build_model_llm(
                    url=url, files=files, readme=readme,
                    key_files=key_files, tech_stack=tech_stack,
                    commands=commands, llm_config=llm_config or {},
                )
                out_path = index_dir / "repo_model.json"
                out_path.write_text(model.model_dump_json(indent=2), encoding="utf-8")
                self.logger.info("Saved LLM-enhanced repo model → %s", out_path)
                return model
            except Exception as exc:
                self.logger.warning("LLM model building failed, falling back: %s", exc)

        # --- Basic info ---
        project_name = url.rstrip("/").split("/")[-1]
        description = self._extract_description(readme)
        problem_statement = self._extract_problem(readme)
        features = self._extract_features(readme)
        target_users = self._infer_users(readme, tech_stack)

        # --- Architecture ---
        architecture = self._extract_architecture(files, key_files)
        data_flow = self._extract_data_flow(readme, key_files)

        # --- Setup ---
        setup = commands.get("install", [])
        if not setup:
            setup = self._extract_setup_from_readme(readme)

        # --- API endpoints ---
        endpoints = self._detect_api_endpoints(key_files)

        # --- Dependencies ---
        deps = self._extract_dependencies(key_files)

        # --- CI/CD ---
        ci_cd = self._detect_ci_cd(files, key_files)

        # --- Deployment ---
        deployment = self._detect_deployment(files, key_files, readme)

        # --- Build model ---
        model = RepoKnowledgeModel(
            project_name=project_name,
            description=description,
            problem_statement=problem_statement,
            features=features,
            target_users=target_users,
            tech_stack=tech_stack,
            architecture_components=architecture,
            data_flow=data_flow,
            setup_instructions=setup,
            api_endpoints=endpoints,
            dependencies=deps,
            deployment_info=deployment,
            ci_cd=ci_cd,
            risks=self._identify_risks(key_files, tech_stack),
            assumptions=self._make_assumptions(readme, tech_stack),
            roadmap=self._extract_roadmap(readme),
            repo_url=url,
            file_tree=files[:200],
            readme_content=readme[:10_000],
            key_files={k: v[:500] for k, v in list(key_files.items())[:30]},
        )

        # Persist
        out_path = index_dir / "repo_model.json"
        out_path.write_text(model.model_dump_json(indent=2), encoding="utf-8")
        self.logger.info("Saved repo model → %s", out_path)

        return model

    # ------------------------------------------------------------------
    # LLM-enhanced model building
    # ------------------------------------------------------------------

    def _build_model_llm(
        self,
        *,
        url: str,
        files: list[str],
        readme: str,
        key_files: dict[str, str],
        tech_stack: list[str],
        commands: dict[str, list[str]],
        llm_config: dict[str, Any],
    ) -> RepoKnowledgeModel:
        """Use LLM to build a richer RepoKnowledgeModel."""
        from ..llm_client import chat_json

        project_name = url.rstrip("/").split("/")[-1]

        # Build context for the LLM
        file_summary = "\n".join(files[:100])
        key_file_summary = ""
        for path, content in list(key_files.items())[:15]:
            key_file_summary += f"\n--- {path} ---\n{content[:1500]}\n"

        system = (
            "You are an expert software architect. Analyse the given GitHub repository "
            "and produce a structured JSON knowledge model.\n\n"
            "Return a JSON object with EXACTLY these fields:\n"
            "- description (string): concise project description\n"
            "- problem_statement (string): what problem this solves\n"
            "- features (array of strings): key features\n"
            "- target_users (array of strings): who uses this\n"
            "- architecture_components (array of strings): main components\n"
            "- data_flow (array of strings): how data moves through the system\n"
            "- risks (array of strings): technical risks\n"
            "- assumptions (array of strings): key assumptions\n"
            "- roadmap (array of strings): suggested improvements\n"
            "- deployment_info (array of strings): deployment methods\n"
            "\nBe specific, technical, and insightful. No generic filler."
        )

        user = (
            f"Repository: {url}\n"
            f"Project: {project_name}\n"
            f"Detected tech stack: {', '.join(tech_stack)}\n"
            f"File count: {len(files)}\n\n"
            f"=== FILE TREE (first 100) ===\n{file_summary}\n\n"
            f"=== KEY FILES ===\n{key_file_summary}\n\n"
            f"=== README (first 5000 chars) ===\n{readme[:5000]}\n\n"
            "Analyse this repository and produce the JSON knowledge model."
        )

        data = chat_json(system, user, **llm_config)

        # Merge LLM insights with deterministic extraction
        model = RepoKnowledgeModel(
            project_name=project_name,
            description=data.get("description", self._extract_description(readme)),
            problem_statement=data.get("problem_statement", ""),
            features=data.get("features", self._extract_features(readme)),
            target_users=data.get("target_users", self._infer_users(readme, tech_stack)),
            tech_stack=tech_stack,
            architecture_components=data.get("architecture_components",
                                             self._extract_architecture(files, key_files)),
            data_flow=data.get("data_flow", []),
            setup_instructions=commands.get("install", []) or self._extract_setup_from_readme(readme),
            api_endpoints=self._detect_api_endpoints(key_files),
            dependencies=self._extract_dependencies(key_files),
            deployment_info=data.get("deployment_info", []),
            ci_cd=self._detect_ci_cd(files, key_files),
            risks=data.get("risks", []),
            assumptions=data.get("assumptions", []),
            roadmap=data.get("roadmap", []),
            repo_url=url,
            file_tree=files[:200],
            readme_content=readme[:10_000],
            key_files={k: v[:500] for k, v in list(key_files.items())[:30]},
        )

        self.logger.info("LLM-enhanced model: %d features, %d risks",
                         len(model.features), len(model.risks))
        return model

    # ------------------------------------------------------------------
    # Extraction helpers (deterministic)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_description(readme: str) -> str:
        """Extract the first meaningful paragraph as description."""
        lines = readme.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip headings, badges, blank lines
            if (not stripped or stripped.startswith("#")
                    or stripped.startswith("[!") or stripped.startswith("![")
                    or stripped.startswith("<")):
                continue
            # Found a text paragraph
            desc_lines = [stripped]
            for j in range(i + 1, min(i + 5, len(lines))):
                nl = lines[j].strip()
                if not nl or nl.startswith("#"):
                    break
                desc_lines.append(nl)
            return " ".join(desc_lines)[:500]
        return "No description available."

    @staticmethod
    def _extract_problem(readme: str) -> str:
        """Try to find a problem statement section."""
        patterns = [
            r"(?:##?\s*(?:Problem|Motivation|Why|Background))\s*\n([\s\S]*?)(?=\n##|\Z)",
        ]
        for pat in patterns:
            m = re.search(pat, readme, re.IGNORECASE)
            if m:
                return m.group(1).strip()[:500]
        return "Inferred from repository structure."

    @staticmethod
    def _extract_features(readme: str) -> list[str]:
        """Extract features from README bullet lists under feature-like headings."""
        features: list[str] = []
        in_section = False
        for line in readme.splitlines():
            stripped = line.strip()
            if re.match(r"^##?\s*(Features|Key Features|Highlights|What)", stripped, re.I):
                in_section = True
                continue
            if in_section:
                if stripped.startswith("#"):
                    break
                if stripped.startswith(("- ", "* ", "• ")):
                    feat = stripped.lstrip("-*• ").strip()
                    if feat:
                        features.append(feat[:200])
        return features[:30]

    @staticmethod
    def _infer_users(readme: str, tech_stack: list[str]) -> list[str]:
        """Infer target users from readme and tech stack."""
        users: list[str] = []
        if any(t in tech_stack for t in ("React", "Vue.js", "Angular", "Next.js")):
            users.append("Frontend developers")
        if any(t in tech_stack for t in ("FastAPI", "Flask", "Django", "Express.js", "NestJS")):
            users.append("Backend developers")
        if any(t in tech_stack for t in ("PyTorch", "TensorFlow", "Hugging Face Transformers")):
            users.append("ML/AI engineers")
        if any(t in tech_stack for t in ("Docker", "Kubernetes", "Terraform")):
            users.append("DevOps engineers")
        if not users:
            users.append("Software developers")
        return users

    @staticmethod
    def _extract_architecture(files: list[str], key_files: dict[str, str]) -> list[str]:
        """Identify architectural components from file structure."""
        components: list[str] = []
        dirs = {f.split("/")[0] for f in files if "/" in f}
        arch_dirs = {"src", "lib", "app", "api", "core", "services", "models",
                     "controllers", "routes", "middleware", "utils", "config",
                     "db", "database", "tests", "docs", "scripts", "deploy"}
        for d in sorted(dirs):
            if d.lower() in arch_dirs or d.lower() in ("frontend", "backend", "server", "client"):
                components.append(f"{d}/ — {d.capitalize()} layer")
        return components[:20]

    @staticmethod
    def _extract_data_flow(readme: str, key_files: dict[str, str]) -> list[str]:
        """Extract data flow descriptions."""
        flows: list[str] = []
        # Look for architecture/flow sections
        m = re.search(
            r"(?:##?\s*(?:Architecture|Data Flow|How it works|System Design))\s*\n([\s\S]*?)(?=\n##|\Z)",
            readme, re.IGNORECASE,
        )
        if m:
            for line in m.group(1).splitlines():
                stripped = line.strip()
                if stripped.startswith(("- ", "* ", "1.", "2.", "3.")):
                    flows.append(stripped.lstrip("-*0123456789. ").strip())
        return flows[:15]

    @staticmethod
    def _extract_setup_from_readme(readme: str) -> list[str]:
        """Extract setup instructions from README."""
        instructions: list[str] = []
        in_section = False
        in_code = False
        for line in readme.splitlines():
            stripped = line.strip()
            if re.match(r"^##?\s*(Install|Setup|Getting Started|Quick Start)", stripped, re.I):
                in_section = True
                continue
            if in_section:
                if stripped.startswith("#") and not stripped.startswith("###"):
                    break
                if stripped.startswith("```"):
                    in_code = not in_code
                    continue
                if in_code and stripped:
                    instructions.append(stripped)
        return instructions[:20]

    @staticmethod
    def _detect_api_endpoints(key_files: dict[str, str]) -> list[APIEndpoint]:
        """Detect API endpoints from source code."""
        endpoints: list[APIEndpoint] = []
        patterns = [
            # FastAPI / Flask decorators
            r'@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)',
            # Express.js
            r'(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)',
        ]
        for path, content in key_files.items():
            for pat in patterns:
                for m in re.finditer(pat, content, re.IGNORECASE):
                    method = m.group(1).upper()
                    route = m.group(2)
                    endpoints.append(APIEndpoint(
                        method=method, path=route,
                        description=f"Found in {path}",
                    ))
        return endpoints[:50]

    @staticmethod
    def _extract_dependencies(key_files: dict[str, str]) -> dict[str, str]:
        """Extract dependency versions from config files."""
        deps: dict[str, str] = {}

        # Python requirements.txt
        for name in ("requirements.txt", "requirements/base.txt"):
            if name in key_files:
                for line in key_files[name].splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = re.split(r"[>=<~!]", line, 1)
                        pkg = parts[0].strip()
                        ver = parts[1].strip() if len(parts) > 1 else "*"
                        if pkg:
                            deps[pkg] = ver

        # package.json
        if "package.json" in key_files:
            try:
                data = json.loads(key_files["package.json"])
                for section in ("dependencies", "devDependencies"):
                    for k, v in (data.get(section) or {}).items():
                        deps[k] = v
            except Exception:
                pass

        return dict(list(deps.items())[:50])

    @staticmethod
    def _detect_ci_cd(files: list[str], key_files: dict[str, str]) -> list[str]:
        """Detect CI/CD configuration."""
        ci: list[str] = []
        if any(f.startswith(".github/workflows") for f in files):
            ci.append("GitHub Actions")
        if any(f in files for f in (".travis.yml", ".circleci/config.yml")):
            ci.append("Travis CI" if ".travis.yml" in files else "CircleCI")
        if "Jenkinsfile" in files:
            ci.append("Jenkins")
        if ".gitlab-ci.yml" in files:
            ci.append("GitLab CI")
        return ci

    @staticmethod
    def _detect_deployment(files: list[str], key_files: dict[str, str], readme: str) -> list[str]:
        """Detect deployment methods."""
        deploy: list[str] = []
        if any("Dockerfile" in f for f in files):
            deploy.append("Docker containerisation")
        if any("docker-compose" in f for f in files):
            deploy.append("Docker Compose orchestration")
        if any("k8s" in f or "kubernetes" in f for f in files):
            deploy.append("Kubernetes deployment")
        if any("terraform" in f.lower() for f in files):
            deploy.append("Terraform infrastructure")
        if any("vercel" in readme.lower() for _ in [1]):
            deploy.append("Vercel deployment")
        if any("heroku" in readme.lower() for _ in [1]):
            deploy.append("Heroku deployment")
        return deploy

    @staticmethod
    def _identify_risks(key_files: dict[str, str], tech_stack: list[str]) -> list[str]:
        """Identify potential risks from the codebase."""
        risks: list[str] = []
        all_content = " ".join(key_files.values()).lower()
        if "todo" in all_content or "fixme" in all_content:
            risks.append("Codebase contains TODO/FIXME markers indicating incomplete work")
        if "deprecated" in all_content:
            risks.append("Some dependencies or APIs may be deprecated")
        if not any(f.startswith("test") or "/test" in f for f in key_files):
            risks.append("Limited test coverage detected")
        return risks

    @staticmethod
    def _make_assumptions(readme: str, tech_stack: list[str]) -> list[str]:
        """Generate reasonable assumptions."""
        assumptions = ["Repository is in active development"]
        if "Python" in tech_stack:
            assumptions.append("Python 3.10+ is required")
        if "Node.js" in tech_stack:
            assumptions.append("Node.js 18+ is required")
        if "Docker" in tech_stack:
            assumptions.append("Docker runtime is available for deployment")
        return assumptions

    @staticmethod
    def _extract_roadmap(readme: str) -> list[str]:
        """Extract roadmap items from README."""
        roadmap: list[str] = []
        in_section = False
        for line in readme.splitlines():
            stripped = line.strip()
            if re.match(r"^##?\s*(Roadmap|Future|Planned|Coming Soon|TODO)", stripped, re.I):
                in_section = True
                continue
            if in_section:
                if stripped.startswith("#"):
                    break
                if stripped.startswith(("- ", "* ", "• ")):
                    item = stripped.lstrip("-*• ").strip()
                    if item:
                        roadmap.append(item[:200])
        return roadmap[:20]
