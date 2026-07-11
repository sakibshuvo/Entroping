import json
from pathlib import Path
from typing import Final, NotRequired, TypedDict, cast


class PublicDocRoute(TypedDict):
    label: str
    source: str
    slug: str


class PublicExternalItem(TypedDict):
    label: str
    url: str


class PublicDocGroup(TypedDict):
    label: str
    collapsed: NotRequired[bool]
    items: list[PublicDocRoute]


class PublicDocsManifest(TypedDict):
    groups: list[PublicDocGroup]
    external: list[PublicExternalItem]


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PUBLIC_DOCS_MANIFEST: Final = REPO_ROOT / "site" / "public-docs.json"


def _load_public_docs_manifest() -> PublicDocsManifest:
    return cast(
        PublicDocsManifest,
        json.loads(PUBLIC_DOCS_MANIFEST.read_text(encoding="utf-8")),
    )


def public_doc_sources() -> list[str]:
    return [
        item["source"]
        for group in _load_public_docs_manifest()["groups"]
        for item in group["items"]
    ]


def public_doc_slugs() -> list[str]:
    return [
        item["slug"]
        for group in _load_public_docs_manifest()["groups"]
        for item in group["items"]
    ]


def public_sidebar_labels() -> list[str]:
    return [group["label"] for group in _load_public_docs_manifest()["groups"]]
