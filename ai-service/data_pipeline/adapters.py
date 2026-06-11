import csv
import gzip
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable, Iterator

from .schema import (
    Interaction,
    ProductRecord,
    normalize_action,
    normalize_timestamp,
)


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def _json_lines(path: Path) -> Iterator[dict]:
    with _open_text(path) as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


class DatasetAdapter(ABC):
    source: str
    domain: str
    license_name: str
    citation_url: str

    def __init__(self, interactions_path: str, metadata_path: str | None = None):
        self.interactions_path = Path(interactions_path)
        self.metadata_path = Path(metadata_path) if metadata_path else None

    @abstractmethod
    def interactions(self) -> Iterable[Interaction]:
        raise NotImplementedError

    @abstractmethod
    def products(self) -> Iterable[ProductRecord]:
        raise NotImplementedError


class GoodreadsAdapter(DatasetAdapter):
    source = "goodreads"
    domain = "book"
    license_name = "Academic use only"
    citation_url = "https://mcauleylab.ucsd.edu/public_datasets/gdrive/goodreads/UCSD%20Book%20Graph.html"

    def interactions(self):
        path = self.interactions_path
        if path.suffix == ".csv":
            with _open_text(path) as handle:
                for row in csv.DictReader(handle):
                    rating = float(row["rating"]) if row.get("rating") else None
                    action = "READ" if str(row.get("is_read", "")).lower() in {"1", "true"} else "RATE"
                    yield Interaction(
                        self.source,
                        self.domain,
                        str(row.get("user_id", "")),
                        str(row.get("book_id", row.get("item_id", ""))),
                        normalize_action(action, rating=rating),
                        normalize_timestamp(row.get("date_updated") or row.get("timestamp")),
                        rating,
                    )
            return
        for row in _json_lines(path):
            rating = float(row["rating"]) if row.get("rating") not in (None, "") else None
            action = "READ" if row.get("is_read", True) else "RATE"
            yield Interaction(
                self.source,
                self.domain,
                str(row.get("user_id", "")),
                str(row.get("book_id", "")),
                normalize_action(action, rating=rating),
                normalize_timestamp(
                    row.get("date_updated")
                    or row.get("read_at")
                    or row.get("date_added")
                    or row.get("timestamp")
                ),
                rating,
            )

    def products(self):
        if not self.metadata_path:
            return
        for row in _json_lines(self.metadata_path):
            authors = row.get("authors") or []
            creator = ", ".join(
                str(author.get("name", author)) if isinstance(author, dict) else str(author)
                for author in authors[:3]
            )
            yield ProductRecord(
                source=self.source,
                domain=self.domain,
                external_id=str(row.get("book_id", "")),
                title=str(row.get("title_without_series") or row.get("title") or ""),
                creator_or_brand=creator,
                description=str(row.get("description") or ""),
                category="Books",
                image_url=str(row.get("image_url") or ""),
                metadata={
                    "isbn": row.get("isbn"),
                    "isbn13": row.get("isbn13"),
                    "publisher": row.get("publisher"),
                    "publication_year": row.get("publication_year"),
                },
            )


class AmazonElectronicsAdapter(DatasetAdapter):
    source = "amazon_electronics"
    domain = "electronics"
    license_name = "Amazon Reviews dataset terms"
    citation_url = "https://amazon-reviews-2023.github.io/"

    def interactions(self):
        for row in _json_lines(self.interactions_path):
            rating = float(row.get("rating", row.get("overall", 0)) or 0)
            yield Interaction(
                self.source,
                self.domain,
                str(row.get("user_id") or row.get("reviewerID") or ""),
                str(row.get("parent_asin") or row.get("asin") or ""),
                normalize_action("RATE", rating=rating),
                normalize_timestamp(
                    row.get("timestamp")
                    or row.get("sort_timestamp")
                    or row.get("unixReviewTime")
                ),
                rating,
            )

    def products(self):
        if not self.metadata_path:
            return
        for row in _json_lines(self.metadata_path):
            categories = row.get("categories") or row.get("category") or []
            if isinstance(categories, list):
                category = " > ".join(map(str, categories[-3:]))
            else:
                category = str(categories)
            images = row.get("images") or []
            image_url = ""
            if images:
                first = images[0]
                image_url = (
                    first.get("large")
                    or first.get("large_image_url")
                    or first.get("hi_res")
                    or ""
                    if isinstance(first, dict)
                    else str(first)
                )
            description = row.get("description") or row.get("features") or ""
            if isinstance(description, list):
                description = " ".join(map(str, description))
            yield ProductRecord(
                source=self.source,
                domain=self.domain,
                external_id=str(row.get("parent_asin") or row.get("asin") or ""),
                title=str(row.get("title") or ""),
                creator_or_brand=str(row.get("store") or row.get("brand") or ""),
                description=str(description),
                category=category or "Electronics",
                price=float(row.get("price") or 0),
                image_url=image_url,
                metadata={"average_rating": row.get("average_rating")},
            )


class HMFashionAdapter(DatasetAdapter):
    source = "hm"
    domain = "fashion"
    license_name = "Non-commercial and academic research"
    citation_url = "https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations"

    def interactions(self):
        with _open_text(self.interactions_path) as handle:
            for row in csv.DictReader(handle):
                yield Interaction(
                    self.source,
                    self.domain,
                    str(row.get("customer_id", "")),
                    str(row.get("article_id", "")),
                    "PURCHASE",
                    normalize_timestamp(row.get("t_dat") or row.get("timestamp")),
                    None,
                )

    def products(self):
        if not self.metadata_path:
            return
        with _open_text(self.metadata_path) as handle:
            for row in csv.DictReader(handle):
                detail = row.get("detail_desc") or ""
                yield ProductRecord(
                    source=self.source,
                    domain=self.domain,
                    external_id=str(row.get("article_id", "")),
                    title=str(row.get("prod_name") or row.get("product_type_name") or ""),
                    creator_or_brand="H&M",
                    description=detail,
                    category=str(
                        row.get("section_name")
                        or row.get("garment_group_name")
                        or "Fashion"
                    ),
                    metadata={
                        "colour_group": row.get("colour_group_name"),
                        "department": row.get("department_name"),
                        "index_group": row.get("index_group_name"),
                    },
                )


ADAPTERS = {
    "goodreads": GoodreadsAdapter,
    "amazon_electronics": AmazonElectronicsAdapter,
    "hm": HMFashionAdapter,
}
