from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from google.genai.types import GenerateContentConfig, Modality
from PIL import Image

from src.domain.errors import redact
from src.llm import create_genai_client

load_dotenv()


PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "global")

IMAGE_MODEL = os.getenv(
    "GEMINI_IMAGE_MODEL",
    "gemini-2.5-flash-image",
)

OUTPUT_DIR = Path(
    os.getenv("FEATURE_IMAGE_OUTPUT_DIR", "generated_images")
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


FEATURE_IMAGE_PROMPT_VERSION = "FEATURE_IMAGE_V1"


def site_context_block(website_name: str = "", website_description: str = "") -> str:
    website = website_name.strip() or "the website"
    description = website_description.strip() or "No website description was provided. Do not assume an industry."
    return """
Website name: """ + website + """
Website description: """ + description + """

The generated image is a featured image for a Persian SEO article.

Important:

- Represent the ARTICLE TOPIC, not an advertisement for the website.
- Use the website description only to understand the subject and audience.
- Do not place a logo.
- Do not invent product UI or screenshots.
- Do not use random text.
- Prefer no text unless text is genuinely useful.
- Avoid watermarks.
- Avoid generic stock-photo appearance.
- Do not assume a specific industry beyond the website description.
"""


@dataclass
class FeatureImageResult:
    success: bool
    output_path: str | None
    model: str
    prompt_version: str
    latency_ms: int
    width: int | None = None
    height: int | None = None
    input_hash: str | None = None
    error: str | None = None


def slugify(text: str) -> str:
    """
    Convert category/title to a safe filename.
    Works reasonably with Persian text.
    """

    text = text.strip()

    text = re.sub(
        r"[^\w\s-]",
        "",
        text,
        flags=re.UNICODE,
    )

    text = re.sub(
        r"[-\s]+",
        "-",
        text,
    )

    text = text.strip("-")

    return text[:80] or "feature-image"


def hash_text(text: str) -> str:
    """
    Stable hash of article content.
    Useful for observability without storing full article text.
    """

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def build_feature_image_prompt(
    article: str,
    category: str | None = None,
    website_name: str = "",
    website_description: str = "",
) -> str:

    category_context = ""

    if category:
        category_context = f"""
CATEGORY:
{category}
"""

    return f"""
You are a senior editorial art director creating ONE
featured image for a professional Persian website.

{site_context_block(website_name, website_description)}

{category_context}

Analyze the article before generating the image.

ARTICLE:
----------------
{article}
----------------

Your task:

1. Identify the central topic.
2. Identify the main search intent.
3. Identify the strongest visual concept.
4. Generate ONE professional editorial hero image.

Requirements:

- 16:9 landscape composition.
- Suitable for a website/blog featured image.
- Strong visual focal point.
- Clean professional composition.
- Modern visual storytelling.
- Understandable without reading the article.
- Appropriate for Persian business audiences.
- Represent the actual article topic.
- Avoid generic stock-photo aesthetics.
- Avoid clichés where possible.
- Avoid unnecessary objects.
- Avoid visual clutter.
- Leave reasonable negative space for cropping.
- No logos.
- No watermark.
- No fake UI.
- No meaningless Persian or English text.
- Prefer NO TEXT unless text is essential to understanding the concept.
- Do not turn the image into an advertisement.

The final image should look like a professionally
art-directed editorial hero image.

Generate exactly ONE image.
"""


class FeatureImageService:
    """
    Reusable application service for Gemini feature-image generation.

    The Streamlit UI and CLI should both call this service.
    """

    def __init__(
        self,
        project_id: str = PROJECT_ID,
        location: str = LOCATION,
        model: str = IMAGE_MODEL,
        output_dir: Path = OUTPUT_DIR,
    ):

        self.project_id = project_id
        self.location = location
        self.model = model
        self.output_dir = output_dir

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.client, _provider, _message = create_genai_client()

    def generate(
        self,
        article: str,
        category: str | None = None,
        output_filename: str | None = None,
        website_name: str = "",
        website_description: str = "",
    ) -> FeatureImageResult:

        if not article or not article.strip():
            return FeatureImageResult(
                success=False,
                output_path=None,
                model=self.model,
                prompt_version=FEATURE_IMAGE_PROMPT_VERSION,
                latency_ms=0,
                error="Article content cannot be empty.",
            )

        started = time.perf_counter()

        input_hash = hash_text(article)

        prompt = build_feature_image_prompt(
            article=article,
            category=category,
            website_name=website_name,
            website_description=website_description,
        )

        if output_filename:
            filename = slugify(output_filename)

            if not filename.lower().endswith(
                (".png", ".jpg", ".jpeg")
            ):
                filename += ".png"

        else:

            category_name = slugify(
                category or "feature-image"
            )

            filename = (
                f"{category_name}-"
                f"{input_hash[:10]}.png"
            )

        output_path = (
            self.output_dir / filename
        )

        try:

            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=GenerateContentConfig(
                    response_modalities=[
                        Modality.TEXT,
                        Modality.IMAGE,
                    ],
                    candidate_count=1,
                ),
            )

            if not response.candidates:
                raise RuntimeError(
                    "Gemini returned no candidates."
                )

            for part in (
                response.candidates[0]
                .content
                .parts
            ):

                if not part.inline_data:
                    continue

                image = Image.open(
                    BytesIO(
                        part.inline_data.data
                    )
                )

                image.save(
                    output_path
                )

                latency_ms = int(
                    (time.perf_counter() - started)
                    * 1000
                )

                return FeatureImageResult(
                    success=True,
                    output_path=str(
                        output_path
                    ),
                    model=self.model,
                    prompt_version=(
                        FEATURE_IMAGE_PROMPT_VERSION
                    ),
                    latency_ms=latency_ms,
                    width=image.width,
                    height=image.height,
                    input_hash=input_hash,
                )

            raise RuntimeError(
                "Gemini response did not contain an image."
            )

        except Exception as exc:

            latency_ms = int(
                (time.perf_counter() - started)
                * 1000
            )

            return FeatureImageResult(
                success=False,
                output_path=None,
                model=self.model,
                prompt_version=(
                    FEATURE_IMAGE_PROMPT_VERSION
                ),
                latency_ms=latency_ms,
                input_hash=input_hash,
                error=redact(str(exc))[:500],
            )