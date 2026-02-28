"""Orchestration pipeline — ties fetcher, parser, and generators together."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from .core.fetcher import ReadmeFetcher, is_github_url
from .core.models import DocumentModel, GenerationResult, OutputFormat, PipelineResult
from .core.notebook_parser import NotebookParser, is_notebook
from .core.parser import ReadmeParser
from .core.semantic_extractor import SemanticExtractor
from .core.template_vars import EMPTY_VARS, TemplateVars, load_template_vars
from .generators.diagram_extractor import DiagramExtractor, ImageCache
from .generators.mermaid_renderer import MermaidRenderer
from .generators.blog_generator import BlogGenerator
from .generators.changelog_generator import ChangelogGenerator
from .generators.faq_generator import FaqGenerator
from .generators.jira_generator import JiraGenerator
from .generators.latex_generator import LatexGenerator
from .generators.onepager_generator import OnePagerGenerator
from .generators.pdf_generator import PdfGenerator
from .generators.pptx_generator import PptxGenerator
from .generators.social_generator import SocialGenerator
from .generators.styles import apply_theme, reset_theme
from .generators.table_sorter import TableSorter
from .generators.themes import get_theme, DEFAULT_THEME
from .generators.word_generator import WordGenerator
from .generators.architecture_generator import ArchitectureGenerator

console = Console()

# Map format enum → generator class
_GENERATORS = {
    OutputFormat.WORD: WordGenerator,
    OutputFormat.PDF: PdfGenerator,
    OutputFormat.PPTX: PptxGenerator,
    OutputFormat.BLOG: BlogGenerator,
    OutputFormat.JIRA: JiraGenerator,
    OutputFormat.CHANGELOG: ChangelogGenerator,
    OutputFormat.LATEX: LatexGenerator,
    OutputFormat.ONEPAGER: OnePagerGenerator,
    OutputFormat.SOCIAL: SocialGenerator,
    OutputFormat.FAQ: FaqGenerator,
    OutputFormat.ARCHITECTURE: ArchitectureGenerator,
}


class Pipeline:
    """End-to-end README → multi-format documentation pipeline.

    Usage::

        pipeline = Pipeline()
        result = pipeline.run("https://github.com/owner/repo")
        print(result.word_path)
    """

    def __init__(
        self,
        github_token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.fetcher = ReadmeFetcher(timeout=timeout, github_token=github_token)
        self.parser = ReadmeParser()
        self.notebook_parser = NotebookParser()
        self.semantic_extractor = SemanticExtractor()

    def run(
        self,
        source: str,
        *,
        output_dir: str | Path = "./output",
        formats: list[OutputFormat] | None = None,
        local: bool = False,
        theme_name: str = "corporate",
        mode: str = "basic",
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        sort_tables: str = "smart",
        provider: str = "openai",
        template_vars: TemplateVars | None = None,
        config_path: str | None = None,
    ) -> PipelineResult:
        """Run the full pipeline.

        Parameters
        ----------
        source
            GitHub URL or local file path.
        output_dir
            Directory where generated files will be written.
        formats
            Which formats to generate. Defaults to all.
        local
            If *True*, treat *source* as a local file path even if it
            looks like a URL.
        theme_name
            Name of the color theme to use (e.g. ``corporate``, ``ocean``).
        mode
            Extraction mode: ``basic`` (deterministic) or ``llm``
            (uses LLM for semantic enrichment).
        api_key
            LLM API key — required when *mode* is ``llm``.
        model
            LLM model name (default ``gpt-4o-mini``).
        base_url
            Custom API base URL (e.g. local Ollama, Azure endpoint).
        sort_tables
            Table sorting strategy: ``smart`` (auto-detect), ``alpha``,
            ``numeric``, ``column:N``, ``column:N:desc``, or ``none``.
        provider
            LLM provider: ``openai``, ``anthropic``, ``google``,
            ``ollama``, ``azure``.
        template_vars
            Pre-built ``TemplateVars`` instance with report variables.
        config_path
            Path to a YAML/JSON config file with template variables.
        """
        output_path = Path(output_dir).resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        if formats is None:
            formats = [
                OutputFormat.WORD, OutputFormat.PDF, OutputFormat.PPTX,
                OutputFormat.BLOG, OutputFormat.JIRA, OutputFormat.CHANGELOG,
                OutputFormat.LATEX, OutputFormat.ONEPAGER, OutputFormat.SOCIAL,
                OutputFormat.FAQ, OutputFormat.ARCHITECTURE,
            ]

        result = PipelineResult(source=source)

        # -- Resolve theme ------------------------------------------------
        theme = get_theme(theme_name)
        apply_theme(theme)
        console.print(f"[dim]Theme:[/] [bold]{theme_name}[/bold]")

        # -- Resolve template variables -----------------------------------
        tvars = template_vars or EMPTY_VARS
        if config_path and not template_vars:
            tvars = load_template_vars(config_path)
        if tvars.has_values:
            console.print(f"[dim]Template vars:[/] [bold]{tvars.project_name or '(unnamed)'}[/bold]")

        # -- Check if source is a Jupyter Notebook ------------------------
        is_nb = (local or not is_github_url(source)) and is_notebook(source)

        # -- Step 1: Fetch README -----------------------------------------
        console.print(f"\n[bold blue]{'Loading notebook' if is_nb else 'Fetching README'} from:[/] {source}")
        try:
            if local:
                content, name = self.fetcher._fetch_local(source)
                repo_url = ""
            else:
                content, name = self.fetcher.fetch(source)
                repo_url = source if is_github_url(source) else ""
        except Exception as exc:
            console.print(f"[bold red]Fetch failed:[/] {exc}")
            reset_theme()
            return result

        console.print(f"[green][OK][/] Fetched {'notebook' if is_nb else 'README'} ({len(content):,} chars)")

        # -- Step 2: Parse ------------------------------------------------
        if is_nb:
            console.print("[bold blue]Parsing Jupyter Notebook...[/]")
            doc: DocumentModel = self.notebook_parser.parse_content(
                content,
                repo_name=name,
                repo_url=repo_url,
                source_path=source,
            )
        else:
            console.print("[bold blue]Parsing Markdown...[/]")
            doc: DocumentModel = self.parser.parse(
                content,
                repo_name=name,
                repo_url=repo_url,
                source_path=source,
            )
        console.print(
            f"[green][OK][/] Parsed: {len(doc.sections)} sections, "
            f"{len(doc.all_blocks)} blocks, "
            f"{len(doc.mermaid_diagrams)} diagrams"
        )

        # -- Step 2b: Sort tables ----------------------------------------
        if sort_tables != "none":
            console.print(f"[bold blue]Sorting tables...[/] [dim](strategy={sort_tables})[/]")
            sorter = TableSorter(strategy=sort_tables)
            doc = sorter.process(doc)
            from .core.models import TableBlock as _TB
            n_tables = sum(
                1 for b in doc.all_blocks if isinstance(b, _TB)
            )
            console.print(f"[green][OK][/] {n_tables} table(s) sorted")

        # -- Step 3: Semantic extraction ----------------------------------
        console.print("[bold blue]Extracting knowledge graph...[/]")
        kg = self.semantic_extractor.extract(doc)

        # Optional LLM enrichment
        if mode == "llm":
            if not api_key:
                console.print("[yellow]WARNING: LLM mode requires --api-key; falling back to basic[/]")
            else:
                try:
                    from .llm.llm_extractor import LLMExtractor, LLMSummarizer

                    # -- Entity extraction via LLM --
                    console.print(f"[bold blue]Running LLM extraction...[/] [dim](provider={provider}, model={model})[/]")
                    llm_extractor = LLMExtractor(
                        api_key=api_key, model=model, base_url=base_url,
                        provider=provider,
                    )
                    llm_kg = llm_extractor.extract(doc)
                    kg.merge(llm_kg)
                    console.print(f"[green][OK][/] LLM enriched graph (+{len(llm_kg.entities)} entities)")

                    # -- Executive & stakeholder summaries --
                    console.print("[bold blue]Generating LLM summaries...[/]")
                    summarizer = LLMSummarizer(
                        api_key=api_key, model=model, base_url=base_url,
                        provider=provider,
                    )
                    summarizer.enrich(doc, kg)
                    console.print("[green][OK][/] Executive summary + 3 stakeholder views generated")

                    # -- LLM content enhancement (blog, FAQ, section rewrites) --
                    from .llm.llm_extractor import LLMContentEnhancer

                    console.print("[bold blue]Running LLM content enhancement...[/]")
                    enhancer = LLMContentEnhancer(
                        api_key=api_key, model=model, base_url=base_url,
                        provider=provider,
                    )
                    enhancer.enrich(doc, kg)
                    parts = []
                    if kg.llm_blog:
                        parts.append("blog")
                    if kg.llm_faq:
                        parts.append(f"{len(kg.llm_faq)} FAQ items")
                    if kg.llm_sections:
                        parts.append(f"{len(kg.llm_sections)} section rewrites")
                    console.print(f"[green][OK][/] LLM content: {', '.join(parts) if parts else 'none'}")

                except ImportError:
                    console.print("[yellow]WARNING: openai package not installed; skipping LLM mode[/]")
                    console.print("[dim]   Install with: pip install opendocs\\[llm\\][/]")
                except Exception as exc:
                    console.print(f"[yellow]WARNING: LLM extraction failed: {exc}[/]")

        stats = kg.compute_stats()
        console.print(
            f"[green][OK][/] KG: {stats['total_entities']} entities, "
            f"{stats['total_relations']} relations"
        )

        # -- Step 4: Render diagrams & download images --------------------
        console.print("[bold blue]Rendering diagrams & downloading images...[/]")
        renderer = MermaidRenderer(cache_dir=output_path / "diagrams")
        diagram_extractor = DiagramExtractor(renderer=renderer)

        # Build KG mermaid code for rendering (capped to avoid oversized URLs)
        kg_mermaid = kg.to_mermaid(max_entities=30) if kg.entities else None

        diagram_paths, image_cache = diagram_extractor.extract(
            doc, output_path, kg_mermaid=kg_mermaid,
        )

        n_rendered = len(image_cache.mermaid_images)
        n_external = len(image_cache.external_images)
        kg_rendered = "yes" if image_cache.kg_diagram else "no"
        console.print(
            f"[green][OK][/] {len(diagram_paths)} .mmd file(s), "
            f"{n_rendered} diagram(s) rendered, "
            f"{n_external} image(s) downloaded, "
            f"KG diagram: {kg_rendered}"
        )

        # -- Step 5: Generate documents -----------------------------------
        for fmt in formats:
            generator_cls = _GENERATORS.get(fmt)
            if generator_cls is None:
                continue

            gen = generator_cls(
                theme=theme,
                knowledge_graph=kg,
                image_cache=image_cache,
                template_vars=tvars,
            )
            console.print(f"[bold blue]Generating {fmt.value.upper()}...[/]")

            gen_result: GenerationResult = gen.generate(doc, output_path)
            result.results.append(gen_result)

            if gen_result.success:
                console.print(f"[green][OK][/] {gen_result.output_path}")
            else:
                console.print(f"[red][FAIL][/] {fmt.value}: {gen_result.error}")

        # -- Step 5b: Smart analysis report (always when KG is populated) --
        if kg.entities:
            from .generators.smart_report import generate_smart_report

            console.print("[bold blue]Generating Analysis Report (Markdown)...[/]")
            report_result = generate_smart_report(doc, kg, output_path)
            result.results.append(report_result)
            if report_result.success:
                console.print(f"[green][OK][/] {report_result.output_path}")
            else:
                console.print(f"[red][FAIL][/] Analysis report: {report_result.error}")

        # -- Summary ------------------------------------------------------
        success = sum(1 for r in result.results if r.success)
        total = len(result.results)
        console.print(
            f"\n[bold green]Done![/] {success}/{total} formats generated "
            f"-> [link=file://{output_path}]{output_path}[/link]\n"
        )

        reset_theme()
        return result
