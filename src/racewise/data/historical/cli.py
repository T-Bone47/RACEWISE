"""Historical data CLI: command-line interface for historical data ingestion."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from racewise.data.historical.f1db_ingest import F1DBIngester, get_f1db_ingester
from racewise.data.historical.jolpica_ingest import JolpicaIngester, get_jolpica_ingester
from racewise.data.historical.fastf1_historical_ingest import FastF1HistoricalIngester, get_fastf1_historical_ingester
from racewise.data.historical.catalog import HistoricalCatalogManager, get_catalog_manager
from racewise.data.historical.availability import AvailabilityIndex, get_availability_index

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def cmd_f1db(args: argparse.Namespace) -> int:
    """Ingest F1DB release into the canonical store."""
    try:
        ingester = get_f1db_ingester()
        if args.rebuild:
            ingester.rebuild()
        stats = ingester.ingest_release(force=args.force)
        print(f"F1DB canonicalization complete: {stats['canonical_counts']}")
        print(f"Runtime: {stats['runtime_seconds']}s ({stats['session_rows_per_second']} rows/s)")
        return 0
    except Exception as e:
        logger.error(f"F1DB ingestion failed: {e}")
        return 1


def cmd_coverage(args: argparse.Namespace) -> int:
    """Print the historical session coverage matrix from canonical data."""
    from racewise.data.historical.canonical_queries import get_canonical_queries

    q = get_canonical_queries()
    db_path = q.db_path
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if args.season:
            rows = conn.execute(
                """
                SELECT season, session_type,
                       COUNT(*) AS sessions,
                       SUM(CASE WHEN results_count > 0 THEN 1 ELSE 0 END) AS with_results,
                       SUM(CASE WHEN qualifying_count > 0 THEN 1 ELSE 0 END) AS with_qualifying,
                       SUM(CASE WHEN pit_stops_count > 0 THEN 1 ELSE 0 END) AS with_pit_stops,
                       SUM(CASE WHEN laps_count > 0 THEN 1 ELSE 0 END) AS with_laps,
                       SUM(CASE WHEN stints_count > 0 THEN 1 ELSE 0 END) AS with_stints,
                       SUM(CASE WHEN weather_count > 0 THEN 1 ELSE 0 END) AS with_weather,
                       SUM(CASE WHEN race_control_count > 0 THEN 1 ELSE 0 END) AS with_race_control
                FROM canonical_session_catalog
                WHERE season = ?
                GROUP BY season, session_type ORDER BY session_type
                """,
                (args.season,),
            ).fetchall()
            for row in rows:
                print(dict(row))
        else:
            eras = [
                ("1950-1959", 1950, 1959), ("1960-1969", 1960, 1969),
                ("1970-1979", 1970, 1979), ("1980-1989", 1980, 1989),
                ("1990-1999", 1990, 1999), ("2000-2009", 2000, 2009),
                ("2010-2019", 2010, 2019), ("2020-2026", 2020, 2026),
            ]
            print(f"{'era':<12}{'sessions':>9}{'results':>9}{'qualifying':>12}{'pit_stops':>11}{'laps':>7}{'stints':>8}{'weather':>9}{'race_ctl':>10}")
            for label, lo, hi in eras:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS sessions,
                           SUM(CASE WHEN results_count > 0 THEN 1 ELSE 0 END) AS wr,
                           SUM(CASE WHEN qualifying_count > 0 THEN 1 ELSE 0 END) AS wq,
                           SUM(CASE WHEN pit_stops_count > 0 THEN 1 ELSE 0 END) AS wp,
                           SUM(CASE WHEN laps_count > 0 THEN 1 ELSE 0 END) AS wl,
                           SUM(CASE WHEN stints_count > 0 THEN 1 ELSE 0 END) AS ws,
                           SUM(CASE WHEN weather_count > 0 THEN 1 ELSE 0 END) AS ww,
                           SUM(CASE WHEN race_control_count > 0 THEN 1 ELSE 0 END) AS wrc
                    FROM canonical_session_catalog WHERE season BETWEEN ? AND ?
                    """,
                    (lo, hi),
                ).fetchone()
                print(f"{label:<12}{row['sessions']:>9}{row['wr']:>9}{row['wq']:>12}{row['wp']:>11}{row['wl']:>7}{row['ws']:>8}{row['ww']:>9}{row['wrc']:>10}")
    finally:
        conn.close()
    return 0


def cmd_jolpica(args: argparse.Namespace) -> int:
    """Ingest Jolpica F1 data for a season range."""
    try:
        ingester = get_jolpica_ingester()
        health = ingester.health_check()
        print(f"Jolpica health: {health}")

        if health["status"] != "connected":
            print("Jolpica API not available")
            return 1

        start_year = args.start_year
        end_year = args.end_year

        for year in range(start_year, end_year + 1):
            print(f"\n=== Ingesting {year} ===")
            try:
                races = ingester.get_races(year)
                print(f"Found {len(races)} races")

                for race in races:
                    round_num = race.get("round")
                    if args.round and round_num not in args.round:
                        continue

                    # Ingest race results
                    results = ingester.get_race_results(year, round_num)
                    print(f"  Race {round_num}: {len(results)} results")

                    # Ingest qualifying
                    quali = ingester.get_qualifying_results(year, round_num)
                    print(f"  Qualifying: {len(quali)} entries")

                    # Pit stops: query the API and report what it actually returns;
                    # availability is data-derived, not assumed from the year.
                    pits = ingester.get_pit_stops(year, round_num)
                    print(f"  Pit stops: {len(pits)} entries")

                    # Lap data (limited)
                    laps = ingester.get_lap_data(year, round_num)
                    print(f"  Laps: {len(laps)} entries")

            except Exception as e:
                logger.error(f"Failed to ingest {year} round {round_num}: {e}")

        return 0
    except Exception as e:
        logger.error(f"Jolpica ingestion failed: {e}")
        return 1


def cmd_fastf1(args: argparse.Namespace) -> int:
    """Ingest historical FastF1 data."""
    try:
        ingester = get_fastf1_historical_ingester()

        if args.season:
            result = ingester.ingest_season(args.season, resume=args.resume, force=args.force)
            print(f"Season {args.season}: {result}")
        elif args.start_year and args.end_year:
            result = ingester.ingest_range(args.start_year, args.end_year, resume=args.resume)
            print(f"Range {args.start_year}-{args.end_year}: {result}")
        else:
            print("Must specify --season or --start-year/--end-year")
            return 1

        return 0
    except Exception as e:
        logger.error(f"FastF1 ingestion failed: {e}")
        return 1


def cmd_fastf1_canonical(args: argparse.Namespace) -> int:
    """Ingest FastF1 modern engineering data into the canonical store.

    Loads representative sessions (or a specific season/round), then maps
    stints, weather and race control into canonical tables. Idempotent:
    re-running produces identical counts. Skips sessions F1DB does not
    represent (no invented sessions).
    """
    import pathlib
    import time

    from racewise.data.fastf1_adapter import FastF1Adapter
    from racewise.data.historical.fastf1_canonical import FastF1Canonicalizer
    from racewise.data.historical.f1db_canonical import CanonicalStore

    default_targets = [(2023, 1, "R"), (2023, 1, "Q"), (2023, 2, "R"), (2023, 3, "R")]
    if args.round:
        targets = [(args.season, r, code) for r in args.round for code in (args.sessions or ["R"])]
    else:
        targets = default_targets

    cache_dir = args.cache_dir or str(pathlib.Path.cwd() / ".fastf1-cache")
    adapter = FastF1Adapter(cache_dir=cache_dir)
    store = CanonicalStore()
    canon = FastF1Canonicalizer(store)

    totals = {"stints": 0, "weather": 0, "race_control": 0, "lap_rows": 0, "sessions": 0, "skipped": 0}
    t_start = time.perf_counter()
    load_seconds = 0.0
    for year, round_num, code in targets:
        t0 = time.perf_counter()
        try:
            session = adapter.load_session(year, round_num, code)
        except Exception as e:
            print(f"{year} R{round_num} {code}: LOAD FAILED ({type(e).__name__}: {e}) - DATA_UNAVAILABLE")
            totals["skipped"] += 1
            continue
        load_seconds += time.perf_counter() - t0
        res = canon.ingest_session(year, round_num, code, session)
        if not res.get("attached"):
            totals["skipped"] += 1
            print(f"{year} R{round_num} {code}: no canonical session (F1DB does not represent it); skipped")
            continue
        totals["sessions"] += 1
        totals["stints"] += res["stints"]
        totals["weather"] += res["weather"]
        totals["race_control"] += res["race_control"]
        totals["lap_rows"] += res["lap_rows"]
        print(
            f"{year} R{round_num} {code}: stints={res['stints']} weather={res['weather']} "
            f"race_control={res['race_control']} fastf1_lap_rows={res['lap_rows']} ({res['seconds']}s)"
        )

    # Availability catalog must reflect the new provider data.
    f1db = canon._f1db
    catalog_rows = f1db.rebuild_catalog()
    elapsed = time.perf_counter() - t_start
    print(f"\nCatalog rebuilt: {catalog_rows} sessions")
    print(
        f"Totals: {totals} | load time {load_seconds:.1f}s | total {elapsed:.1f}s "
        f"| db size {store.db_path.stat().st_size / 1e6:.1f} MB"
    )
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    """Manage historical catalog."""
    catalog = get_catalog_manager()
    catalog.load()

    if args.report:
        print(catalog.generate_report())
    elif args.list_providers:
        for p in catalog.catalog.providers:
            print(f"{p.provider} v{p.provider_version}: {p.source_url}")
    elif args.list_entities:
        for etype, inv in catalog.catalog.entities.items():
            print(f"{etype}: {inv.total_records} records, {inv.earliest_season}-{inv.latest_season}")

    return 0


def cmd_availability(args: argparse.Namespace) -> int:
    """Check data availability."""
    index = get_availability_index()

    if args.matrix:
        matrix = index.get_coverage_matrix()
        print(json.dumps(matrix, indent=2))
    elif args.season:
        coverage = index.get_coverage_matrix()
        if args.season in coverage:
            print(json.dumps(coverage[args.season], indent=2))
        else:
            print(f"Season {args.season} not in index")

    return 0


def cmd_manifest(args: argparse.Namespace) -> int:
    """Generate dataset manifest."""
    catalog = get_catalog_manager()
    catalog.load()

    if args.generate:
        # Generate manifest from current state
        manifest = {
            "generated_at": datetime.utcnow().isoformat(),
            "catalog": catalog.catalog.to_dict() if catalog.catalog else {},
        }
        output = args.output or "data/manifests/dataset_manifest.json"
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"Manifest written to {output}")
    elif args.verify:
        # Verify manifest against actual files
        print("Verification not yet implemented")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="RACEWISE Historical Data Ingestion CLI")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # F1DB
    f1db_parser = subparsers.add_parser("f1db", help="Ingest F1DB release")
    f1db_parser.add_argument("--force", action="store_true", help="Force re-download")
    f1db_parser.add_argument("--rebuild", action="store_true", help="Rebuild canonical DB from scratch")

    # Coverage
    cov_parser = subparsers.add_parser("coverage", help="Historical coverage matrix (data-derived)")
    cov_parser.add_argument("--season", type=int)

    # Jolpica
    jolpica_parser = subparsers.add_parser("jolpica", help="Ingest Jolpica F1 data")
    jolpica_parser.add_argument("--start-year", type=int, default=1950)
    jolpica_parser.add_argument("--end-year", type=int, default=2026)
    jolpica_parser.add_argument("--round", type=int, action="append")

    # FastF1
    ff1_parser = subparsers.add_parser("fastf1", help="Ingest FastF1 historical data")
    ff1_group = ff1_parser.add_mutually_exclusive_group(required=True)
    ff1_group.add_argument("--season", type=int)
    ff1_group.add_argument("--start-year", type=int)
    ff1_parser.add_argument("--end-year", type=int)
    ff1_parser.add_argument("--resume", action="store_true", default=True)
    ff1_parser.add_argument("--force", action="store_true")

    # FastF1 (modern engineering data)
    ff1c_parser = subparsers.add_parser(
        "fastf1-canonical", help="Ingest FastF1 stints/weather/race control into the canonical store"
    )
    ff1c_parser.add_argument("--season", type=int, default=2023)
    ff1c_parser.add_argument("--round", type=int, action="append")
    ff1c_parser.add_argument("--sessions", nargs="+", default=None, help="FastF1 session codes (default R)")
    ff1c_parser.add_argument("--cache-dir", type=str, default=None)

    # Catalog
    cat_parser = subparsers.add_parser("catalog", help="Manage historical catalog")
    cat_parser.add_argument("--report", action="store_true")
    cat_parser.add_argument("--list-providers", action="store_true")
    cat_parser.add_argument("--list-entities", action="store_true")

    # Availability
    avail_parser = subparsers.add_parser("availability", help="Check data availability")
    avail_parser.add_argument("--matrix", action="store_true")
    avail_parser.add_argument("--season", type=int)

    # Manifest
    manifest_parser = subparsers.add_parser("manifest", help="Manage dataset manifest")
    manifest_parser.add_argument("--generate", action="store_true")
    manifest_parser.add_argument("--verify", action="store_true")
    manifest_parser.add_argument("--output", "-o", type=str)

    args = parser.parse_args()
    setup_logging(args.verbose)

    commands = {
        "f1db": cmd_f1db,
        "coverage": cmd_coverage,
        "jolpica": cmd_jolpica,
        "fastf1": cmd_fastf1,
        "fastf1-canonical": cmd_fastf1_canonical,
        "catalog": cmd_catalog,
        "availability": cmd_availability,
        "manifest": cmd_manifest,
    }

    if args.command not in commands:
        parser.print_help()
        return 1

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())