"""Build a stratified, blank-label taxonomy-v2 evaluation fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict, deque
from collections.abc import Iterable, Sequence
from pathlib import Path

import duckdb

from soundcheck.scripts.eval_resolution_v2 import (
    DEFAULT_EVAL_V2_PATH,
    PopularityTier,
    ResolutionV2EvalExample,
    load_examples,
)
from soundcheck.sql.loader import load_sql
from soundcheck.taxonomy import DEFAULT_TAXONOMY_PATH, GenreTaxonomy, load_taxonomy

DEFAULT_DATABASE_PATH = Path("data/soundcheck.duckdb")
DEFAULT_TARGET_COUNT = 480


def _example_id(parts: Iterable[str]) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:20]
    return f"genre-v2-{digest}"


def _integer(value: object) -> int:
    if not isinstance(value, int):
        raise TypeError("listener count must be an integer")
    return value


def _popularity_tiers(
    rows: Sequence[tuple[object, ...]],
) -> dict[str, PopularityTier]:
    values = sorted(
        _integer(row[9])
        for row in rows
        if row[9] is not None
    )
    if not values:
        return {}
    low_cut = values[len(values) // 3]
    high_cut = values[(2 * len(values)) // 3]
    tiers: dict[str, PopularityTier] = {}
    for row in rows:
        artist_key = str(row[0])
        if row[9] is None:
            tiers[artist_key] = "unknown"
        elif _integer(row[9]) <= low_cut:
            tiers[artist_key] = "low"
        elif _integer(row[9]) <= high_cut:
            tiers[artist_key] = "mid"
        else:
            tiers[artist_key] = "high"
    return tiers


def _database_candidates(
    database_path: Path,
    taxonomy: GenreTaxonomy,
) -> tuple[ResolutionV2EvalExample, ...]:
    if not database_path.exists():
        return ()
    try:
        with duckdb.connect(str(database_path), read_only=True) as connection:
            rows = connection.execute(
                load_sql("select_resolution_v2_eval_candidates.sql"),
                [taxonomy.taxonomy_version, taxonomy.taxonomy_version],
            ).fetchall()
    except duckdb.CatalogException:
        return ()
    tiers = _popularity_tiers(rows)
    examples: list[ResolutionV2EvalExample] = []
    for row in rows:
        artist_key = str(row[0])
        source_system = str(row[2])
        source_tag = str(row[3])
        predicted_ids = tuple(str(value) for value in row[4])
        method = str(row[5])
        parts = (
            artist_key,
            source_system,
            source_tag,
            ",".join(predicted_ids),
            taxonomy.taxonomy_version,
        )
        examples.append(
            ResolutionV2EvalExample.model_validate(
                {
                    "example_id": _example_id(parts),
                    "artist_key": artist_key,
                    "artist_name": str(row[1]),
                    "source_system": source_system,
                    "source_tag": source_tag,
                    "predicted_genre_ids": predicted_ids,
                    "predicted_method": method,
                    "macro_family_id": str(row[6]),
                    "language": str(row[7]),
                    "join_key_type": str(row[8]),
                    "popularity_tier": tiers[artist_key],
                }
            )
        )
    return tuple(examples)


def _tag_mapping_candidates(
    database_path: Path,
    taxonomy: GenreTaxonomy,
) -> tuple[ResolutionV2EvalExample, ...]:
    if not database_path.exists():
        return ()
    try:
        with duckdb.connect(str(database_path), read_only=True) as connection:
            rows = connection.execute(
                load_sql("select_resolution_v2_eval_tag_candidates.sql"),
                [taxonomy.taxonomy_version],
            ).fetchall()
    except duckdb.CatalogException:
        return ()
    examples: list[ResolutionV2EvalExample] = []
    for row in rows:
        source_system = str(row[0])
        source_tag = str(row[1])
        normalized_source_tag = str(row[2])
        predicted_ids = tuple(str(value) for value in row[3])
        artist_key = f"source-tag:{source_system}:{normalized_source_tag}"
        examples.append(
            ResolutionV2EvalExample(
                example_id=_example_id(
                    (
                        artist_key,
                        ",".join(predicted_ids),
                        taxonomy.taxonomy_version,
                    )
                ),
                artist_key=artist_key,
                artist_name="[source-tag mapping]",
                source_system=source_system,
                source_tag=source_tag,
                predicted_genre_ids=predicted_ids,
                predicted_method=str(row[4]),
                macro_family_id=str(row[5]),
                language=str(row[6]),
                join_key_type="unknown",
                popularity_tier="unknown",
            )
        )
    return tuple(examples)


def _declared_multilingual_candidates(
    taxonomy: GenreTaxonomy,
) -> tuple[ResolutionV2EvalExample, ...]:
    examples: list[ResolutionV2EvalExample] = []
    for genre in taxonomy.genres:
        if genre.status == "rejected":
            continue
        for language, aliases in genre.multilingual_aliases.items():
            for alias in aliases:
                artist_key = (
                    f"taxonomy-alias:{genre.genre_id}:{language}:"
                    f"{hashlib.sha256(alias.encode()).hexdigest()[:12]}"
                )
                examples.append(
                    ResolutionV2EvalExample(
                        example_id=_example_id(
                            (
                                artist_key,
                                alias,
                                taxonomy.taxonomy_version,
                            )
                        ),
                        artist_key=artist_key,
                        artist_name="[declared multilingual alias]",
                        source_system="taxonomy_declared_alias",
                        source_tag=alias,
                        predicted_genre_ids=(genre.genre_id,),
                        predicted_method="exact_multilingual_alias",
                        macro_family_id=genre.macro_family_id,
                        language=language,
                        join_key_type="unknown",
                        popularity_tier="unknown",
                    )
                )
    return tuple(examples)


def _stratified_sample(
    examples: Sequence[ResolutionV2EvalExample],
    target_count: int,
) -> tuple[ResolutionV2EvalExample, ...]:
    groups: dict[
        tuple[str, str, str, str, str, str],
        deque[ResolutionV2EvalExample],
    ] = defaultdict(deque)
    for example in sorted(examples, key=lambda item: item.example_id):
        stratum_key = (
            example.macro_family_id,
            example.language,
            example.source_system,
            example.predicted_method,
            example.join_key_type,
            example.popularity_tier,
        )
        groups[stratum_key].append(example)
    selected: list[ResolutionV2EvalExample] = []
    group_keys = tuple(sorted(groups))
    while len(selected) < target_count:
        added = False
        for group_key in group_keys:
            if groups[group_key] and len(selected) < target_count:
                selected.append(groups[group_key].popleft())
                added = True
        if not added:
            break
    return tuple(sorted(selected, key=lambda item: item.example_id))


def _preserve_labels(
    examples: Sequence[ResolutionV2EvalExample],
    output_path: Path,
) -> tuple[ResolutionV2EvalExample, ...]:
    if not output_path.exists():
        return tuple(examples)
    existing = {
        example.example_id: example
        for example in load_examples(output_path)
        if example.label_should_resolve is not None
    }
    return tuple(
        example.model_copy(
            update={
                "label_should_resolve": existing[example.example_id].label_should_resolve,
                "label_genre_ids": existing[example.example_id].label_genre_ids,
            }
        )
        if example.example_id in existing
        else example
        for example in examples
    )


def generate_fixture(
    database_path: Path,
    taxonomy: GenreTaxonomy,
    output_path: Path,
    *,
    target_count: int,
) -> tuple[ResolutionV2EvalExample, ...]:
    """Generate predictions while leaving all unavailable labels blank."""
    candidates = (
        *_database_candidates(database_path, taxonomy),
        *_tag_mapping_candidates(database_path, taxonomy),
        *_declared_multilingual_candidates(taxonomy),
    )
    selected = _stratified_sample(candidates, target_count)
    selected = _preserve_labels(selected, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(
            f"{example.model_dump_json()}\n"
            for example in selected
        ),
        encoding="utf-8",
    )
    return selected


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_EVAL_V2_PATH)
    parser.add_argument(
        "--target-count",
        type=int,
        default=DEFAULT_TARGET_COUNT,
    )
    return parser


def main() -> None:
    """CLI entrypoint."""
    args = _build_parser().parse_args()
    if args.target_count < 300:
        raise SystemExit("--target-count must be at least 300")
    taxonomy = load_taxonomy(args.taxonomy)
    examples = generate_fixture(
        args.database,
        taxonomy,
        args.output,
        target_count=args.target_count,
    )
    print(
        json.dumps(
            {
                "event": "resolution_v2_eval_fixture_written",
                "examples": len(examples),
                "human_labels_created": 0,
                "output": str(args.output),
                "taxonomy_version": taxonomy.taxonomy_version,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    if len(examples) < 300:
        raise SystemExit(
            "fewer than 300 candidates; run make resolve-v2 after ingestion"
        )


if __name__ == "__main__":
    main()
