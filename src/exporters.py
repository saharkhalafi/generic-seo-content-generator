from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone

from src.persian import strip_html
from src.schemas import FinalSEOBox
from src.security import sanitize_html, sanitize_markdown


def seo_box_to_json(box: FinalSEOBox) -> str:
    return json.dumps(box.export_payload(), ensure_ascii=False, indent=2)


def seo_box_to_markdown(box: FinalSEOBox) -> str:
    faqs = "\n\n".join(f"**{item.question}**\n\n{item.answer}" for item in box.faq)
    faq_section = f"\n## سوالات متداول\n\n{faqs}\n" if box.faq else ""
    links = "\n".join(
        f"- [{item.anchor}]({item.suggested_url}) — {item.reason}"
        for item in box.internal_links
    )
    body = sanitize_markdown((box.content_markdown or "").strip() or html_to_markdown(box.content))
    return f"""---
title: {box.meta_title}
description: {box.meta_description}
slug: {box.slug}
h1: {box.h1}
word_count: {box.word_count}
seo_score: {box.seo_score}
status: {box.status}
revision_count: {box.revision_count}
---

{body}

## فراخوان اقدام

{box.cta}

## پیشنهاد لینک داخلی

{links or "-"}

## متادیتا

- عنوان سئو: {box.meta_title}
- توضیحات متا: {box.meta_description}
- اسلاگ: {box.slug}
{faq_section}"""


def seo_box_to_html_document(box: FinalSEOBox) -> str:
    title = html.escape(box.meta_title)
    description = html.escape(box.meta_description)
    canonical = box.slug if box.slug.startswith("http") else f"/{box.slug.strip('/')}/" if box.slug.strip() else ""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    site_label = box.website_name.strip() or "SEO Content"
    canonical_tag = f'\n  <link rel="canonical" href="{html.escape(canonical)}">' if canonical else ""
    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <meta name="description" content="{description}">{canonical_tag}
  <style>
    body {{ font-family: Tahoma, Vazirmatn, sans-serif; line-height: 1.9; max-width: 860px; margin: 2rem auto; padding: 0 1rem; color: #1f2937; }}
    h1, h2, h3 {{ line-height: 1.5; }}
    .meta {{ background: #f8fafc; border: 1px solid #e2e8f0; padding: 1rem; border-radius: 12px; margin-bottom: 1.5rem; }}
  </style>
</head>
<body>
  <header class="meta">
    <div>{html.escape(site_label)} — SEO Box — {generated}</div>
    <div>اسلاگ: {html.escape(box.slug)}</div>
  </header>
  {sanitize_html(box.content)}
</body>
</html>
"""


def normalize_slug(slug: str, existing_url: str, site_domain: str = "") -> str:
    if existing_url.strip():
        return existing_url.strip()
    value = (slug or "").strip().strip("/")
    if value.startswith("http"):
        return value
    domain = (site_domain or "").strip().rstrip("/")
    if domain:
        return f"{domain}/{value}/" if value else f"{domain}/"
    return f"/{value}/" if value else "/"


def html_to_markdown(raw_html: str) -> str:
    text = raw_html or ""
    text = re.sub(r"<h1[^>]*>(.*?)</h1>", r"# \1", text, flags=re.I | re.S)
    text = re.sub(r"<h2[^>]*>(.*?)</h2>", r"## \1", text, flags=re.I | re.S)
    text = re.sub(r"<h3[^>]*>(.*?)</h3>", r"### \1", text, flags=re.I | re.S)
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1", text, flags=re.I | re.S)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = strip_html(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
