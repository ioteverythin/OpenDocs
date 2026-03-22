"""Fine-tune a base SLM on codebase-to-documentation examples.

Uses QLoRA (4-bit quantized LoRA) to fine-tune Phi-3.5-mini-instruct
(or any Hugging Face causal LM) on examples of:

    code analysis context → professional technical documentation

The fine-tuned adapter is small (~50 MB) and can be loaded on top of
the base model at inference time.

Usage::

    from opendocs.llm.slm_finetune import SLMFineTuner

    tuner = SLMFineTuner(
        base_model="microsoft/Phi-3.5-mini-instruct",
        output_dir="./my-adapter",
    )

    # Add training examples (code context → desired documentation)
    tuner.add_example(
        code_context="...(module summary, imports, classes)...",
        documentation="...(professional narrative doc)...",
    )

    # Fine-tune (takes ~15-30 min on a single GPU)
    tuner.train(epochs=3, batch_size=1)

    # The adapter is saved to output_dir and can be loaded with:
    # SLMProvider(adapter_path="./my-adapter")

Requires: ``pip install opendocs[slm]``
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("opendocs.llm.slm_finetune")

# Prompt template for training data
_SYSTEM_PROMPT = """\
You are an expert technical documentation writer. Given a structured \
analysis of a software codebase (modules, classes, functions, imports, \
architecture layers, and technology stack), you produce a comprehensive, \
professional-quality technical document.

Your output should include:
- An Executive Summary with specific project details
- System Architecture description with component relationships
- Detailed module-by-module documentation with purpose and status
- Technology Stack analysis
- Implementation recommendations
- Priority matrix for pending work

Write in clear, professional prose. Reference specific module names, \
class names, function names, and technology names. Include concrete \
details — never write generic filler text."""

_USER_TEMPLATE = """\
Analyze the following codebase and write a comprehensive technical document.

PROJECT: {project_name}

CODEBASE ANALYSIS:
{code_context}

Write a professional technical document covering:
1. Executive Summary (what this project does, key stats)
2. System Architecture (how components connect)
3. Current Codebase Status (module-by-module assessment)
4. Technology Stack (what's used and why)
5. Implementation Plan / Recommendations
6. Priority Matrix (what to do first)"""


@dataclass
class TrainingExample:
    """A single code-context → documentation training pair."""
    code_context: str
    documentation: str
    project_name: str = "Project"


@dataclass
class SLMFineTuner:
    """QLoRA fine-tuner for codebase documentation generation.

    Fine-tunes a base model using 4-bit quantization + LoRA adapters,
    making it possible to train on a 6-8 GB VRAM GPU.

    Parameters
    ----------
    base_model
        Hugging Face model ID (default: Phi-3.5-mini-instruct).
    output_dir
        Where to save the trained LoRA adapter.
    cache_dir
        Where to cache the downloaded base model.
    lora_r
        LoRA rank (higher = more capacity, more VRAM). 16 is good default.
    lora_alpha
        LoRA alpha scaling factor. Usually 2x rank.
    lora_dropout
        Dropout in LoRA layers.
    learning_rate
        Training learning rate.
    """
    base_model: str = "microsoft/Phi-3.5-mini-instruct"
    output_dir: str = "./opendocs-adapter"
    cache_dir: str = ""
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    learning_rate: float = 2e-4
    examples: list[TrainingExample] = field(default_factory=list)

    def __post_init__(self):
        if not self.cache_dir:
            self.cache_dir = os.environ.get(
                "OPENDOCS_MODEL_CACHE",
                str(Path.home() / ".cache" / "opendocs" / "models"),
            )

    def add_example(
        self,
        code_context: str,
        documentation: str,
        project_name: str = "Project",
    ) -> None:
        """Add a training example (code analysis → desired output)."""
        self.examples.append(TrainingExample(
            code_context=code_context,
            documentation=documentation,
            project_name=project_name,
        ))

    def add_examples_from_file(self, path: str | Path) -> int:
        """Load training examples from a JSONL file.

        Each line should be a JSON object with keys:
        ``code_context``, ``documentation``, and optionally ``project_name``.

        Returns the number of examples loaded.
        """
        count = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                self.add_example(
                    code_context=data["code_context"],
                    documentation=data["documentation"],
                    project_name=data.get("project_name", "Project"),
                )
                count += 1
        logger.info("Loaded %d training examples from %s", count, path)
        return count

    def save_examples(self, path: str | Path) -> None:
        """Save current training examples to a JSONL file."""
        with open(path, "w", encoding="utf-8") as f:
            for ex in self.examples:
                json.dump({
                    "project_name": ex.project_name,
                    "code_context": ex.code_context,
                    "documentation": ex.documentation,
                }, f, ensure_ascii=False)
                f.write("\n")
        logger.info("Saved %d examples to %s", len(self.examples), path)

    def _build_dataset(self, tokenizer):
        """Convert examples into a tokenized HF Dataset."""
        from datasets import Dataset

        records = []
        for ex in self.examples:
            user_msg = _USER_TEMPLATE.format(
                project_name=ex.project_name,
                code_context=ex.code_context,
            )

            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": ex.documentation},
            ]

            if hasattr(tokenizer, "apply_chat_template"):
                text = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=False,
                )
            else:
                text = (
                    f"System: {_SYSTEM_PROMPT}\n\n"
                    f"User: {user_msg}\n\n"
                    f"Assistant: {ex.documentation}"
                )

            records.append({"text": text})

        return Dataset.from_list(records)

    def train(
        self,
        epochs: int = 3,
        batch_size: int = 1,
        gradient_accumulation_steps: int = 8,
        max_seq_length: int = 4096,
        warmup_steps: int = 10,
        logging_steps: int = 5,
        save_steps: int = 50,
    ) -> Path:
        """Run QLoRA fine-tuning and save the adapter.

        Parameters
        ----------
        epochs
            Number of training epochs.
        batch_size
            Per-device batch size (keep at 1 for 6-8 GB VRAM).
        gradient_accumulation_steps
            Effective batch = batch_size * gradient_accumulation_steps.
        max_seq_length
            Maximum sequence length for training.
        warmup_steps
            Learning rate warmup steps.

        Returns
        -------
        Path
            Path to the saved adapter directory.
        """
        if not self.examples:
            raise ValueError(
                "No training examples. Add examples with add_example() "
                "or add_examples_from_file() before training."
            )

        import torch
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            TrainingArguments,
            Trainer,
            DataCollatorForLanguageModeling,
        )

        output_path = Path(self.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        logger.info("Step 1/4: Loading tokenizer for %s", self.base_model)
        tokenizer = AutoTokenizer.from_pretrained(
            self.base_model,
            cache_dir=self.cache_dir,
            trust_remote_code=True,
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        logger.info("Step 2/4: Loading base model with 4-bit quantization")
        quant_config = None
        model_kwargs: dict[str, Any] = {
            "cache_dir": self.cache_dir,
            "trust_remote_code": True,
            "torch_dtype": torch.float16,
        }

        if torch.cuda.is_available():
            quant_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
            model_kwargs["quantization_config"] = quant_config
            model_kwargs["device_map"] = "auto"
        else:
            logger.warning("No CUDA GPU — training on CPU will be very slow")
            model_kwargs["device_map"] = "cpu"
            model_kwargs["torch_dtype"] = torch.float32

        model = AutoModelForCausalLM.from_pretrained(self.base_model, **model_kwargs)

        if quant_config is not None:
            model = prepare_model_for_kbit_training(model)

        logger.info("Step 3/4: Applying LoRA (r=%d, alpha=%d)", self.lora_r, self.lora_alpha)

        # Find target modules (works for most transformer architectures)
        target_modules = _find_target_modules(model)
        logger.info("LoRA target modules: %s", target_modules)

        lora_config = LoraConfig(
            r=self.lora_r,
            lora_alpha=self.lora_alpha,
            lora_dropout=self.lora_dropout,
            target_modules=target_modules,
            bias="none",
            task_type="CAUSAL_LM",
        )
        model = get_peft_model(model, lora_config)

        trainable, total = model.get_nb_trainable_parameters()
        logger.info(
            "Trainable parameters: %s / %s (%.2f%%)",
            f"{trainable:,}", f"{total:,}", trainable / total * 100,
        )

        # Build dataset
        logger.info("Preparing %d training examples", len(self.examples))
        dataset = self._build_dataset(tokenizer)

        def tokenize_fn(examples):
            return tokenizer(
                examples["text"],
                truncation=True,
                max_length=max_seq_length,
                padding="max_length",
            )

        tokenized = dataset.map(tokenize_fn, batched=True, remove_columns=["text"])

        data_collator = DataCollatorForLanguageModeling(
            tokenizer=tokenizer,
            mlm=False,
        )

        # Training arguments
        training_args = TrainingArguments(
            output_dir=str(output_path / "checkpoints"),
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=gradient_accumulation_steps,
            learning_rate=self.learning_rate,
            warmup_steps=warmup_steps,
            logging_steps=logging_steps,
            save_steps=save_steps,
            save_total_limit=2,
            fp16=torch.cuda.is_available(),
            optim="paged_adamw_8bit" if torch.cuda.is_available() else "adamw_torch",
            report_to="none",
            remove_unused_columns=False,
        )

        logger.info("Step 4/4: Training for %d epochs...", epochs)
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=tokenized,
            data_collator=data_collator,
        )

        trainer.train()

        # Save adapter only (not the full base model)
        adapter_dir = output_path / "adapter"
        model.save_pretrained(str(adapter_dir))
        tokenizer.save_pretrained(str(adapter_dir))

        logger.info("Adapter saved to: %s", adapter_dir)
        logger.info(
            "To use: SLMProvider(model='%s', adapter_path='%s')",
            self.base_model, adapter_dir,
        )

        return adapter_dir


def _find_target_modules(model) -> list[str]:
    """Auto-detect linear layer names for LoRA targeting.

    Works across different model architectures (Phi, LLaMA, Mistral, etc.)
    by looking for common attention/MLP projection names.
    """
    import re

    linear_names = set()
    for name, module in model.named_modules():
        if module.__class__.__name__ in ("Linear", "Linear4bit"):
            # Extract the last component of the module name
            parts = name.split(".")
            layer_name = parts[-1]
            # Skip output/embedding layers
            if layer_name not in ("lm_head", "embed_tokens", "wte", "wpe"):
                linear_names.add(layer_name)

    # If we found common names, prefer the standard attention + MLP set
    common_targets = {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}
    overlap = linear_names & common_targets
    if len(overlap) >= 4:
        return sorted(overlap)

    # Fallback: use all linear layers found
    if linear_names:
        return sorted(linear_names)

    # Last resort
    return ["q_proj", "v_proj"]


def generate_training_data_from_codebase(
    codebase_dir: str | Path,
    reference_doc: str | Path | None = None,
) -> TrainingExample:
    """Create a training example from a codebase directory.

    Analyzes the codebase using ``CodebaseAnalyzer`` and (optionally)
    pairs it with a reference document as the target output.

    Parameters
    ----------
    codebase_dir
        Path to the codebase to analyze.
    reference_doc
        Path to a reference .md or .docx file to use as the target
        documentation output.  If None, creates the example with
        only the code_context filled in.

    Returns
    -------
    TrainingExample
        A training pair ready for fine-tuning.
    """
    from ..core.code_analyzer import CodebaseAnalyzer, generate_codebase_markdown

    analyzer = CodebaseAnalyzer()
    model = analyzer.analyze(codebase_dir)

    # Build a concise code context (not the full markdown, just the structured data)
    context_parts = []
    context_parts.append(f"Project: {model.project_name}")
    context_parts.append(f"Description: {model.description}")
    context_parts.append(f"Files: {model.total_files}, Code Lines: {model.total_code_lines}")
    context_parts.append(f"Languages: {', '.join(f'{l} ({c})' for l, c in model.languages.items())}")

    if model.tech_stack:
        context_parts.append("\nTechnology Stack:")
        for tech in model.tech_stack:
            context_parts.append(f"  - {tech.name} ({tech.category})")

    if model.architecture_layers:
        context_parts.append("\nArchitecture Layers:")
        for layer in model.architecture_layers:
            context_parts.append(f"  {layer.name}: {layer.description}")
            for mod in layer.modules[:5]:
                context_parts.append(f"    - {mod}")
            if len(layer.modules) > 5:
                context_parts.append(f"    ... +{len(layer.modules) - 5} more")

    context_parts.append("\nModule Details:")
    for fa in model.files[:30]:
        parts = [f"  {fa.path} ({fa.line_count} lines)"]
        if fa.summary:
            parts.append(f"    Purpose: {fa.summary}")
        if fa.classes:
            parts.append(f"    Classes: {', '.join(c.name for c in fa.classes)}")
        if fa.functions:
            pub_funcs = [f.name for f in fa.functions if not f.name.startswith("_")]
            if pub_funcs:
                parts.append(f"    Functions: {', '.join(pub_funcs[:8])}")
        context_parts.append("\n".join(parts))

    code_context = "\n".join(context_parts)

    # Load reference doc if provided
    doc_text = ""
    if reference_doc:
        ref_path = Path(reference_doc)
        if ref_path.suffix == ".md":
            doc_text = ref_path.read_text(encoding="utf-8")
        elif ref_path.suffix == ".docx":
            from docx import Document as DocxDocument
            doc = DocxDocument(str(ref_path))
            paragraphs = []
            for p in doc.paragraphs:
                if p.text.strip():
                    paragraphs.append(p.text)
            doc_text = "\n\n".join(paragraphs)
        elif ref_path.suffix == ".txt":
            doc_text = ref_path.read_text(encoding="utf-8")

    return TrainingExample(
        code_context=code_context,
        documentation=doc_text,
        project_name=model.project_name,
    )
