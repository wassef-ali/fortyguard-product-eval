"""Streamlit UI — FortyGuard-only environmental analyzer.

Single data provider throughout: FortyGuard. There is no Open-Meteo reference
temperature and no Nominatim geocoding. The area of interest is a fixed GeoJSON
polygon (Downtown Phoenix) or a polygon you paste yourself.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from fortyguard import archive as arch
from fortyguard import client as fg_client
from fortyguard import geo
from fortyguard import parsing
from fortyguard.config import (
    BASIC_MAX_AREA_SQ_MI,
    BASIC_MAX_ENV_ANALYSES,
    DEFAULT_ANALYSES,
    DEFAULT_START_TIME,
    DEFAULT_TIMEZONE,
    ENV_ANALYSES,
    HEATMAP_GRANULARITY_M,
    PHOENIX_AOI,
    PHOENIX_CENTER,
)

load_dotenv()
st.set_page_config(page_title="FortyGuard Analyzer", page_icon="🌡️", layout="wide")

st.title("🌡️ FortyGuard Environmental Analyzer")
st.caption("Street-level heat and environmental parameters — powered by FortyGuard only.")

with st.sidebar:
    st.header("Settings")
    api_key = st.text_input(
        "FortyGuard API key",
        value=os.getenv("FORTYGUARD_API_KEY", ""),
        type="password",
        help="Stored locally in .env; never share it.",
    )
    date_iso = st.date_input("Date", value=datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).date()).isoformat()
    start_time = st.text_input("Time (HH:MM, local Phoenix)", value=DEFAULT_START_TIME)
    resolution = st.select_slider(
        "Heatmap granularity",
        options=["low", "medium", "high"],
        value="medium",
    )
    analyses = st.multiselect(
        f"Environmental parameters (up to {BASIC_MAX_ENV_ANALYSES} on Basic)",
        ENV_ANALYSES,
        default=DEFAULT_ANALYSES,
    )
    if len(analyses) > BASIC_MAX_ENV_ANALYSES:
        st.warning(f"Basic plan allows up to {BASIC_MAX_ENV_ANALYSES} parameters.")
    use_pasted_aoi = st.checkbox("Use pasted GeoJSON instead of Downtown Phoenix AOI", value=False)
    pasted_aoi = ""
    if use_pasted_aoi:
        pasted_aoi = st.text_area("GeoJSON (FeatureCollection/Feature/Polygon)", height=140)
    run = st.button("▶ Run analysis", type="primary", width="stretch")

st.info(
    "Default AOI: a small manually-defined polygon near Downtown Phoenix "
    f"(~{geo.aoi_area_sq_miles(PHOENIX_AOI):.3f} sq mi, under the Basic {BASIC_MAX_AREA_SQ_MI} sq mi cap). "
    "All temperature data comes from the FortyGuard heatmap — no external weather source."
)

if run:
    if not api_key.strip():
        st.error("Add FORTYGUARD_API_KEY to your .env file or enter it in the sidebar.")
        st.stop()
    if not analyses:
        st.error("Select at least one environmental parameter.")
        st.stop()
    if len(analyses) > BASIC_MAX_ENV_ANALYSES:
        st.error(f"Select no more than {BASIC_MAX_ENV_ANALYSES} parameters on Basic.")
        st.stop()
    import re
    if not re.fullmatch(r"\d{2}:\d{2}", start_time.strip()):
        st.error("Time must be HH:MM (24-hour), e.g. 14:00.")
        st.stop()

    aoi = PHOENIX_AOI
    if use_pasted_aoi:
        try:
            aoi = json.loads(pasted_aoi)
        except json.JSONDecodeError:
            st.error("Pasted GeoJSON is not valid JSON.")
            st.stop()

    area_sq_mi = geo.aoi_area_sq_miles(aoi)
    if area_sq_mi <= 0:
        st.error("Could not read a polygon from the AOI.")
        st.stop()
    if area_sq_mi > BASIC_MAX_AREA_SQ_MI:
        st.error(
            f"AOI is ~{area_sq_mi:,.2f} sq mi, over the Basic {BASIC_MAX_AREA_SQ_MI} sq mi cap."
        )
        st.stop()

    client = fg_client.FortyGuardClient(api_key.strip())
    store = arch.ResultArchive(Path("outputs"))
    granularity = HEATMAP_GRANULARITY_M[resolution]

    try:
        with st.status("Running analysis…", expanded=True) as status_box:
            st.write("Submitting single-hour heatmap to FortyGuard…")
            date_time = {"start_date": date_iso, "start_time": start_time.strip(), "filter_type": 1}
            heatmap_body = {
                "polygon_aoi": aoi,
                "date_time": date_time,
                "granularity": granularity,
            }
            cached = store.get("/v1/heatmap", heatmap_body)
            if cached is not None:
                heatmap_response = cached["result"]
                st.write("Served from local archive (no credits spent).")
            else:
                aid = client.submit_heatmap(
                    aoi, date_iso, granularity=granularity, filter_type=1, start_time=start_time.strip()
                )
                heatmap_response = client.wait_for_result(aid)
                store.put("/v1/heatmap", heatmap_body, heatmap_response)

            mean_temp, temp_meta = parsing.extract_mean_temperature_c(heatmap_response)
            tiles = parsing.tiles(parsing._result(heatmap_response))
            st.write(f"Mean temperature: **{mean_temp:.3f} °C** · {len(tiles)} tiles.")

            # env_params at the AOI centre using nearest-tile temperature.
            center_lat, center_lon = PHOENIX_CENTER if aoi is PHOENIX_AOI else _center_of(aoi)
            point_temp, tile, dist_m = geo.nearest_tile_temperature(tiles, center_lat, center_lon)
            st.write(
                f"Sourcing point temperature from nearest tile #{tile['tile_id']} "
                f"({dist_m:.0f} m away): **{point_temp:.3f} °C**"
            )
            env_body = {
                "latitude": center_lat,
                "longitude": center_lon,
                "temperature": point_temp,
                "date_time": date_time,
                "analysis": analyses,
            }
            cached_env = store.get("/v1/env_params", env_body)
            if cached_env is not None:
                env_response = cached_env["result"]
            else:
                aid = client.submit_env_params(
                    center_lat, center_lon, point_temp, dict(date_time), analyses
                )
                env_response = client.wait_for_result(aid)
                store.put("/v1/env_params", env_body, env_response)

            status_box.update(label="Analysis completed", state="complete", expanded=False)

        parsed = parsing.parse_env_params(env_response)
        st.session_state["heatmap_response"] = heatmap_response
        st.session_state["parsed_env"] = parsed
        st.session_state["mean_temp"] = mean_temp
        st.session_state["point_temp"] = point_temp
        st.session_state["run_date"] = date_iso
        st.session_state["resolution"] = resolution
        st.success("Analysis completed successfully.")
    except Exception as exc:  # noqa: BLE001 - surface the real error in the UI
        st.error(f"Analysis failed: {exc}")
        st.stop()

if "heatmap_response" in st.session_state:
    heatmap_response = st.session_state["heatmap_response"]
    parsed = st.session_state["parsed_env"]
    st.divider()
    st.header("Results")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mean temperature", f"{st.session_state['mean_temp']:.2f} °C")
    c2.metric("Point temperature", f"{st.session_state['point_temp']:.2f} °C")
    c3.metric("Date", st.session_state["run_date"])
    c4.metric("Granularity", f"{HEATMAP_GRANULARITY_M[st.session_state['resolution']]} m")

    st.subheader("Street-level heatmap (FortyGuard tiles)")
    try:
        from fortyguard import visualization

        out_path = Path("outputs") / "latest_heatmap.png"
        visualization.render_heatmap(parsing._result(heatmap_response), out_path)
        st.image(str(out_path), width="stretch")
    except ValueError:
        st.warning("No tiles to render (empty result).")

    st.subheader("Environmental parameters at the AOI centre")
    st.caption(
        f"Input temperature {parsed.get('input_temperature_c')} °C, sourced from the nearest heatmap tile."
    )
    timestamps = parsed.get("timestamps") or []
    parameters = parsed.get("parameters") or {}
    if timestamps:
        frame = pd.DataFrame({"timestamp": pd.to_datetime(timestamps, errors="coerce")})
        for name, values in parameters.items():
            if isinstance(values, list) and len(values) == len(timestamps):
                frame[name] = pd.to_numeric(pd.Series(values), errors="coerce")
        st.line_chart(frame.set_index("timestamp") if not frame.empty else frame, width="stretch")
        st.dataframe(frame, width="stretch", hide_index=True)
    else:
        st.info("No timestamps returned.")

    solar = parsed.get("solar_irradiance")
    if solar:
        st.subheader("Solar irradiance")
        st.json(solar)


def _center_of(aoi) -> tuple[float, float]:
    bbox = geo.bbox_of_aoi(aoi)
    if bbox is None:
        return PHOENIX_CENTER
    west, south, east, north = bbox
    lat = (south + north) / 2
    lon = (west + east) / 2
    if not geo.point_in_aoi(lon, lat, aoi):
        # Fall back to a grid point inside the AOI.
        points = geo.grid_points(aoi, dimension=9, max_points=1)
        if points:
            return points[0]
    return (lat, lon)
