from __future__ import annotations

from pydantic import BaseModel, Field

from src.schemas import UserInput


class BenchmarkCase(BaseModel):
    case_key: str
    category: str
    category_type: str = ""
    primary_keyword: str
    secondary_keywords: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    search_intent: list[str] = Field(default_factory=lambda: ["Commercial", "Informational"])
    product_features: list[str] = Field(default_factory=list)
    existing_content: str = ""
    target_word_min: int = 700
    target_word_max: int = 1500
    box_style: str = "full"
    website_name: str = ""
    website_description: str = ""
    notes: str = ""
    source: str = "gold_set"

    def to_user_input(self) -> UserInput:
        target = (self.target_word_min + self.target_word_max) // 2
        description = self.website_description.strip() or f"وب‌سایتی که درباره {self.category} مطلب منتشر می‌کند."
        return UserInput(
            website_name=self.website_name,
            website_description=description,
            category_name=self.category,
            primary_keyword=self.primary_keyword,
            secondary_keywords=self.secondary_keywords,
            industries_professions=self.industries,
            search_intents=self.search_intent,
            existing_content=self.existing_content,
            desired_word_count=target,
            category_type=self.category_type,
            box_style=self.box_style,  # type: ignore[arg-type]
        )
