"""Image generation tool — image.generate.

Uses AI image generation (DALL-E, Stable Diffusion, etc.) to create
icons, illustrations, and decorative images for documentation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ImageGenerateTool:
    """Generate icons/illustrations via AI image generation APIs.

    Supports DALL-E (OpenAI) by default, with hooks for other providers.
    """

    def __init__(
        self,
        api_key: str = "",
        output_dir: Path | str = ".",
        provider: str = "openai",
    ) -> None:
        self.api_key = api_key
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.provider = provider

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        prompt: str = params["prompt"]
        style: str = params.get("style", "flat-icon")
        size: str = params.get("size", "512x512")

        # Prepend style guidance to the prompt
        styled_prompt = f"{style} style: {prompt}"

        if self.provider == "openai":
            return await self._generate_openai(styled_prompt, size)
        # TODO: add support for Stable Diffusion, Midjourney, etc.
        return {"error": f"Unsupported provider: {self.provider}"}

    async def _generate_openai(
        self, prompt: str, size: str
    ) -> dict[str, Any]:
        """Generate image via OpenAI DALL-E API."""
        # TODO: import openai
        # TODO: client = openai.AsyncOpenAI(api_key=self.api_key)
        # TODO: response = await client.images.generate(
        #     model="dall-e-3",
        #     prompt=prompt,
        #     size=size,
        #     n=1,
        # )
        # TODO: download image from response.data[0].url
        # TODO: save to output_dir / f"img_{uuid}.png"
        return {
            "prompt": prompt,
            "size": size,
            "image_url": "",            # TODO: from API response
            "local_path": "",           # TODO: saved file path
        }
