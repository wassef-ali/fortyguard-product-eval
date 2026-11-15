"""Terminal pipeline: FortyGuard heatmap -> exact mean -> nearest-tile env_params.

One data provider throughout: FortyGuard. No Open-Meteo, no Nominatim.

Workflow (single-hour basis, because env_params is point-in-time):
  1. (optional) read account plan/credits via /v1/system/fetch-api-key-usage
  2. submit a single-hour heatmap (filter_type: 1) and poll until completed
  3. extract the explicit area mean from stats_data (fallback: tile mean)
  4. source a per-point temperature from the NEAREST heatmap tile
  5. submit env_params at those points (same hour) and poll until completed
  6. archive everything locally and write a provenance-bearing summary
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from fortyguard import archive as arch
from fortyguard import client as fg_client
from fortyguard import geo
from fortyguard import parsing
from fortyguard.config import (
    BASIC_MAX_AREA_SQ_MI,
    DEFAULT_ANALYSES,
    DEFAULT_START_TIME,
    DEFAULT_TIMEZONE,
    HEATMAP_GRANULARITY_M,
    PHOENIX_AOI,
    PHOENIX_CENTER,
)

FILTER_SINGLE_HOUR = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FortyGuard-only heatmap -> env_params automation."
    )
    parser.add_argument("--date", help="Local date YYYY-MM-DD; defaults to today in Phoenix.")
    parser.add_argument(
        "--time",
        default=DEFAULT_START_TIME,
        help=f"Local HH:MM (America/Phoenix) for single-hour analyses. Default {DEFAULT_START_TIME}.",
    )
    parser.add_argument(
        "--resolution",
        choices=["low", "medium", "high"],
        default="medium",
        help="Heatmap granularity: low=100m, medium=80m, high=60m.",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=1,
        help="Number of env_params sample points (1..25). Default 1 for a low-cost first run.",
    )
    parser.add_argument(
        "--temperature-only",
        action="store_true",
        help="Run heatmap and extract its mean, but skip env_params.",
    )
    parser.add_argument(
        "--usage",
        action="store_true",
        help="Print account plan/credits first (one extra API call).",
    )
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
    parser.add_argument("--output", default="outputs", help="Output directory.")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    if args.max_points < 1 or args.max_points > 25:
        raise SystemExit("--max-points must be between 1 and 25.")

    api_key = os.getenv("FORTYGUARD_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "FORTYGUARD_API_KEY is missing. Copy .env.example to .env and set your key."
        )

    local_now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
    date_iso = args.date or local_now.date().isoformat()
    try:
        datetime.strptime(date_iso, "%Y-%m-%d")
    except ValueError:
        raise SystemExit("--date must use YYYY-MM-DD.")

    if not re.fullmatch(r"\d{2}:\d{2}", args.time or ""):
        raise SystemExit("--time must use HH:MM (24-hour), e.g. 14:00.")

    granularity = HEATMAP_GRANULARITY_M[args.resolution]
    area_sq_mi = geo.aoi_area_sq_miles(PHOENIX_AOI)
    if area_sq_mi > BASIC_MAX_AREA_SQ_MI:
        raise SystemExit(
            f"Safety stop: AOI is {area_sq_mi:.3f} sq mi (> Basic {BASIC_MAX_AREA_SQ_MI} sq mi limit)."
        )

    print("\n=== FortyGuard automation (FortyGuard-only) ===")
    print(f"City / AOI   : Downtown Phoenix small test AOI")
    print(f"Date / hour  : {date_iso} {args.time} ({DEFAULT_TIMEZONE})")
    print(f"Resolution   : {args.resolution} ({granularity} m)")
    print(f"AOI area     : {area_sq_mi:.4f} sq mi (Basic ceiling: {BASIC_MAX_AREA_SQ_MI})")
    print(f"Env points   : {0 if args.temperature_only else args.max_points}")
    print("Data source  : FortyGuard only (no external weather service)")
    print("\nThis run submits billable/credit-consuming API requests.")
    if not args.yes:
        answer = input("Continue? Type YES to submit: ").strip()
        if answer != "YES":
            print("Cancelled; no API request was sent.")
            return

    client = fg_client.FortyGuardClient(api_key)
    store = arch.ResultArchive(Path(args.output))
    run_dir = Path(args.output) / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    # The date_time object used for BOTH heatmap and env_params, so that the
    # temperature genuinely matches the heatmap "for the same place and time".
    date_time = {
        "start_date": date_iso,
        "start_time": args.time,
        "filter_type": FILTER_SINGLE_HOUR,
    }

    if args.usage:
        print("\n[usage] Reading account plan/credits ...")
        try:
            usage = client.usage()
            print(json.dumps(usage, indent=2, ensure_ascii=False, default=str))
            (run_dir / "usage.json").write_text(
                json.dumps(usage, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except fg_client.FortyGuardError as exc:
            print(f"[usage] skipped ({exc})")

    # --- heatmap ---------------------------------------------------------- #
    heatmap_body = {
        "polygon_aoi": PHOENIX_AOI,
        "date_time": date_time,
        "granularity": granularity,
    }
    cached = store.get("/v1/heatmap", heatmap_body)
    if cached is not None:
        heatmap_response = cached["result"]
        print("\n[1/4] Heatmap served from local archive (no credits spent).")
    else:
        print("\n[1/4] Submitting single-hour heatmap ...")
        activity_id = client.submit_heatmap(
            PHOENIX_AOI,
            date_iso,
            granularity=granularity,
            filter_type=FILTER_SINGLE_HOUR,
            start_time=args.time,
        )
        print(f"      activity_id={activity_id}")
        heatmap_response = client.wait_for_result(activity_id)
        store.put("/v1/heatmap", heatmap_body, heatmap_response)

    (run_dir / "heatmap_response.json").write_text(
        json.dumps(heatmap_response, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    print("\n[2/4] Extracting mean temperature ...")
    mean_temp_c, temp_meta = parsing.extract_mean_temperature_c(heatmap_response)
    print(f"      mean temperature = {mean_temp_c:.3f} °C ({temp_meta['method']})")
    (run_dir / "heatmap_temperature.json").write_text(
        json.dumps(temp_meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    heatmap_tiles = parsing.tiles(parsing._result(heatmap_response))
    print(f"      tiles returned   = {len(heatmap_tiles)}")

    print("\n[3/4] Rendering heatmap ...")
    try:
        png = fg_visualize(heatmap_response, run_dir / "heatmap.png")
        print(f"      saved {png.name}")
    except ValueError as exc:
        print(f"      skipped ({exc})")

    env_points: list[tuple[float, float]] = []
    env_results = []
    env_failures = []
    if not args.temperature_only:
        if args.max_points == 1:
            env_points = [PHOENIX_CENTER]
        else:
            dimension = 5 if args.resolution == "medium" else (3 if args.resolution == "low" else 7)
            env_points = geo.grid_points(PHOENIX_AOI, dimension=dimension, max_points=args.max_points)
            env_points = env_points or [PHOENIX_CENTER]

        print(f"\n[4/4] env_params at {len(env_points)} point(s) ...")
        for index, (lat, lon) in enumerate(env_points, start=1):
            try:
                point_temp, tile, dist_m = geo.nearest_tile_temperature(heatmap_tiles, lat, lon)
            except ValueError as exc:
                print(f"      point {index}: skipped ({exc})")
                continue
            print(
                f"      point {index}/{len(env_points)}: lat={lat:.5f} lon={lon:.5f} "
                f"temp={point_temp:.3f} °C (tile {tile['tile_id']}, {dist_m:.0f} m away)"
            )
            body = {
                "latitude": lat,
                "longitude": lon,
                "temperature": point_temp,
                "date_time": date_time,
                "analysis": DEFAULT_ANALYSES,
            }
            cached_env = store.get("/v1/env_params", body)
            if cached_env is not None:
                response = cached_env["result"]
            else:
                try:
                    aid = client.submit_env_params(
                        lat, lon, point_temp, dict(date_time), DEFAULT_ANALYSES
                    )
                    response = client.wait_for_result(aid)
                    store.put("/v1/env_params", body, response)
                except fg_client.FortyGuardError as exc:
                    (run_dir / f"env_params_error_point{index}.json").write_text(
                        json.dumps({"request": body, "error": str(exc)}, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    env_failures.append({"point": {"latitude": lat, "longitude": lon}, "error": str(exc)})
                    print(f"      point {index}: FAILED — {exc}")
                    continue
            parsed = parsing.parse_env_params(response)
            env_results.append(
                {
                    "point": {"latitude": lat, "longitude": lon},
                    "temperature_source": {
                        "method": "nearest_heatmap_tile",
                        "tile_id": tile["tile_id"],
                        "tile_centroid": [tile["lon"], tile["lat"]],
                        "distance_m": round(dist_m, 1),
                        "temperature_c": point_temp,
                    },
                    "env_params": parsed,
                }
            )
        (run_dir / "env_params.json").write_text(
            json.dumps(env_results, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        if env_failures:
            (run_dir / "env_params_failures.json").write_text(
                json.dumps(env_failures, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )

    summary = {
        "provider": "FortyGuard",
        "city": "Phoenix, Arizona",
        "area_name": "Downtown Phoenix small test AOI",
        "date": date_iso,
        "start_time": args.time,
        "filter_type": FILTER_SINGLE_HOUR,
        "timezone": DEFAULT_TIMEZONE,
        "resolution": args.resolution,
        "heatmap_granularity_m": granularity,
        "area_sq_miles": area_sq_mi,
        "mean_temperature_c": mean_temp_c,
        "temperature_extraction": temp_meta,
        "tile_count": len(heatmap_tiles),
        "env_params_points": len(env_results),
        "env_params_failed": env_failures,
        "env_params_analyses": DEFAULT_ANALYSES,
        "temperature_sourcing": "per-point nearest heatmap tile; no external source",
    }
    (run_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    print("\n=== SUCCESS ===")
    print(f"Mean temperature: {mean_temp_c:.3f} °C (FortyGuard heatmap)")
    print(f"Output directory: {run_dir.resolve()}")
    print("Saved: heatmap_response.json, heatmap_temperature.json, run_summary.json")
    if env_results:
        print("Saved: env_params.json")
    if env_failures:
        print(f"Warning: {len(env_failures)} env_params point(s) failed — see env_params_failures.json.")
    if not env_points and not args.temperature_only:
        print("Note: no env_params point fell inside the AOI; nothing was submitted.")


def fg_visualize(heatmap_response: dict, out_path: Path) -> Path:
    from fortyguard import visualization

    result = parsing._result(heatmap_response)
    return visualization.render_heatmap(result, out_path)


if __name__ == "__main__":
    main()
