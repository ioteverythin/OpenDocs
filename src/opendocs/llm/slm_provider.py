"""Local SLM (Small Language Model) provider using Hugging Face transformers.

Downloads and runs models like Phi-3.5-mini-instruct locally on GPU or CPU.
Supports 4-bit quantization via bitsandbytes for 6-8 GB VRAM GPUs.
Also supports loading fine-tuned LoRA adapters.

Usage::

    from opendocs.llm.slm_provider import SLMProvider

    # Basic — downloads model on first use
    slm = SLMProvider(model="microsoft/Phi-3.5-mini-instruct")
    text = slm.chat("You are a technical writer.", "Describe this architecture.")

    # With a fine-tuned adapter
    slm = SLMProvider(
        model="microsoft/Phi-3.5-mini-instruct",
        adapter_path="./my-finetuned-adapter",
    )

Requires: ``pip install opendocs[slm]``
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .providers import DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE, LLMProvider

logger = logging.getLogger("opendocs.llm.slm_provider")

# Default model — best quality/size for 6-8 GB VRAM
DEFAULT_SLM_MODEL = "microsoft/Phi-3.5-mini-instruct"

# Where to cache downloaded models
_CACHE_DIR = os.environ.get(
    "OPENDOCS_MODEL_CACHE",
    str(Path.home() / ".cache" / "opendocs" / "models"),
)


class SLMProvider(LLMProvider):
    """Local SLM provider using Hugging Face transformers + bitsandbytes.

    Loads the model once and reuses it for all subsequent calls within
    the same process.  Supports:

    - 4-bit quantization (default on CUDA) for low VRAM
    - LoRA adapter loading for fine-tuned models
    - CPU fallback when no GPU is available
    """

    # Class-level cache so we only load the model once
    _loaded_model = None
    _loaded_tokenizer = None
    _loaded_model_name: str | None = None
    _loaded_adapter: str | None = None

    def __init__(
        self,
        *,
        model: str | None = None,
        adapter_path: str | None = None,
        quantize_4bit: bool = True,
        max_new_tokens: int = 2048,
        device_map: str = "auto",
        cache_dir: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            model=model or DEFAULT_SLM_MODEL,
            api_key="local",  # not needed but parent expects it
            **kwargs,
        )
        self.adapter_path = adapter_path
        self.quantize_4bit = quantize_4bit
        self.max_new_tokens = max_new_tokens
        self.device_map = device_map
        self.cache_dir = cache_dir or _CACHE_DIR

    def _ensure_loaded(self):
        """Load model + tokenizer if not already cached."""
        # Skip if same model already loaded
        if (
            SLMProvider._loaded_model is not None
            and SLMProvider._loaded_model_name == self.model
            and SLMProvider._loaded_adapter == self.adapter_path
        ):
            return

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        logger.info("Loading SLM model: %s (this may take a minute on first run)...", self.model)

        tokenizer = AutoTokenizer.from_pretrained(
            self.model,
            cache_dir=self.cache_dir,
            trust_remote_code=True,
        )

        # Build quantization config for 4-bit if GPU available with enough VRAM
        model_kwargs: dict[str, Any] = {
            "cache_dir": self.cache_dir,
            "trust_remote_code": True,
            "device_map": self.device_map,
            "torch_dtype": torch.float16,
        }

        use_gpu = torch.cuda.is_available()
        min_vram_mb = 3500  # Need ~3.5 GB free for quantized Phi-3.5

        if use_gpu:
            try:
                free_vram = torch.cuda.mem_get_info()[0] / (1024 ** 2)
                total_vram = torch.cuda.mem_get_info()[1] / (1024 ** 2)
                logger.info(
                    "GPU VRAM: %.0f MB free / %.0f MB total", free_vram, total_vram,
                )
                if free_vram < min_vram_mb:
                    logger.warning(
                        "Insufficient free VRAM (%.0f MB < %d MB) — falling back to CPU",
                        free_vram, min_vram_mb,
                    )
                    use_gpu = False
            except Exception:
                pass  # If we can't check, try GPU anyway

        if use_gpu and self.quantize_4bit:
            try:
                from transformers import BitsAndBytesConfig

                model_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",
                )
                logger.info("Using 4-bit quantization (bitsandbytes NF4)")
            except ImportError:
                logger.warning("bitsandbytes not available — loading in float16")
        elif not use_gpu:
            logger.info("Loading on CPU in float16 to save memory (~7.5 GB RAM for Phi-3.5)")
            model_kwargs["device_map"] = "cpu"
            model_kwargs["torch_dtype"] = torch.float16

        model = AutoModelForCausalLM.from_pretrained(self.model, **model_kwargs)

        # Load LoRA adapter if specified
        if self.adapter_path and Path(self.adapter_path).exists():
            from peft import PeftModel

            logger.info("Loading LoRA adapter from: %s", self.adapter_path)
            model = PeftModel.from_pretrained(model, self.adapter_path)
            logger.info("LoRA adapter loaded successfully")

        # Cache at class level
        SLMProvider._loaded_model = model
        SLMProvider._loaded_tokenizer = tokenizer
        SLMProvider._loaded_model_name = self.model
        SLMProvider._loaded_adapter = self.adapter_path

        logger.info("SLM model loaded: %s", self.model)

    def _call(self, system: str, user: str) -> str:
        """Run inference on the local model."""
        self._ensure_loaded()

        import torch

        model = SLMProvider._loaded_model
        tokenizer = SLMProvider._loaded_tokenizer

        # Build chat messages in the format the model expects
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        # Use the tokenizer's chat template if available
        if hasattr(tokenizer, "apply_chat_template"):
            input_text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            # Fallback for models without chat template
            input_text = f"System: {system}\n\nUser: {user}\n\nAssistant:"

        inputs = tokenizer(input_text, return_tensors="pt")

        # Move to same device as model
        device = next(model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                temperature=max(self.temperature, 0.01),  # avoid 0.0
                do_sample=self.temperature > 0.01,
                top_p=0.9,
                repetition_penalty=1.1,
                pad_token_id=tokenizer.eos_token_id,
            )

        # Decode only the generated tokens (strip the prompt)
        input_len = inputs["input_ids"].shape[1]
        generated = outputs[0][input_len:]
        result = tokenizer.decode(generated, skip_special_tokens=True).strip()

        return result

    def _call_json(self, system: str, user: str) -> str:
        """Call with JSON hint — small models need extra guidance."""
        json_hint = (
            "\n\nIMPORTANT: You MUST respond with valid JSON only. "
            "No markdown fences, no commentary, no explanation — "
            "just a single JSON object. Start your response with {"
        )
        return self._call(system + json_hint, user)

    @property
    def provider_name(self) -> str:
        return "slm"

    @classmethod
    def unload(cls):
        """Free GPU memory by unloading the cached model."""
        if cls._loaded_model is not None:
            del cls._loaded_model
            del cls._loaded_tokenizer
            cls._loaded_model = None
            cls._loaded_tokenizer = None
            cls._loaded_model_name = None
            cls._loaded_adapter = None

            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("SLM model unloaded")

    @staticmethod
    def download_model(
        model_name: str = DEFAULT_SLM_MODEL,
        cache_dir: str | None = None,
    ) -> Path:
        """Pre-download a model so first inference is fast.

        Returns the path to the cached model directory.
        """
        from huggingface_hub import snapshot_download

        dest = cache_dir or _CACHE_DIR
        logger.info("Downloading model %s to %s ...", model_name, dest)
        path = snapshot_download(
            model_name,
            cache_dir=dest,
        )
        logger.info("Model downloaded: %s", path)
        return Path(path)
