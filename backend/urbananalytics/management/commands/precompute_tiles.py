# backend/management/commands/precompute_tiles.py
import os
import re
import time
import math
import shutil
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand
from django.conf import settings
import json
import numpy as np
from PIL import Image
import mercantile
from pyproj import Transformer
import rasterio
from rasterio.enums import Resampling
from rio_tiler.io import COGReader

from urbananalytics.models import UnionCouncil
from urbananalytics.views.map_views import run_pixelwise_analysis, init_ee

import geemap
import ee

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class Command(BaseCommand):
    help = "Precompute monthly NDVI, Thermal, AQI tiles for UC areas"

    def add_arguments(self, parser):
        parser.add_argument(
            "--years", type=int, nargs=2, metavar=("START_YEAR", "END_YEAR"),
            help="Range of years to compute (inclusive). Defaults to past 5 years."
        )
        parser.add_argument(
            "--analyses", type=str, nargs="+", default=["ndvi", "thermal", "aqi"],
            help="Analysis types to compute (default: ndvi thermal aqi)."
        )
        parser.add_argument(
            "--max-workers", type=int, default=5,
            help="Maximum parallel workers (default: 5)."
        )

    def handle(self, *args, **options):
        init_ee()
        analyses = options["analyses"]
        max_workers = options["max_workers"]
        today = datetime.now()
        years = options.get("years")
        if not years:
            start_year, end_year = today.year - 5, today.year
        else:
            start_year, end_year = years


        # Get all UCs
        ucs = list(UnionCouncil.objects.all())

        base_dir = os.path.join(settings.MEDIA_ROOT, "tiles", "pixelwise")

        for year in range(start_year, end_year + 1):
            for month in range(1, 13):
                start_date = datetime(year, month, 1)
                last_day = (datetime(year, month + 1, 1) - timedelta(days=1)).day if month != 12 else 31
                end_date = datetime(year, month, last_day)
                month_key = f"{start_date.strftime('%Y-%m-%d')}-{end_date.strftime('%Y-%m-%d')}"
                logger.info(f"Processing month {month_key}")

                for analysis in analyses:
                    logger.info(f"→ Generating {analysis.upper()} tiles")

                    def process_uc(feature):
                        try:
                            uc_name = feature.uc_name
                            city_name = feature.city_name
                            geojson_str = feature.geometry.geojson
                            uc_safe = re.sub(r"[^\w\-]", "_", uc_name)

                            month_dir = os.path.join(base_dir, "uc", analysis, city_name, month_key, uc_safe)
                            tiles_dir = os.path.join(month_dir, "tiles")
                            os.makedirs(tiles_dir, exist_ok=True)

                            local_tif = os.path.join(month_dir, f"{analysis}_{month_key}.tif")

                            if not geojson_str:
                                raise ValueError("Missing geometry")
                            geojson_dict = json.loads(geojson_str)  
                            polygon = ee.Geometry(geojson_dict)    
              

                            # Determine scale
                            if analysis.lower() != "aqi":
                                area_sq_m = polygon.area().getInfo()
                                default_scales = {"ndvi": 10, "thermal": 100}
                                scale = default_scales.get(analysis.lower(), 10)

                                if area_sq_m > 1e9:
                                    scale = max(scale, 60)
                                elif area_sq_m > 5e8:
                                    scale = max(scale, 40)
                                elif area_sq_m > 1e8:
                                    scale = max(scale, 20)

                                if area_sq_m < (scale ** 2):
                                    scale = max(int(area_sq_m ** 0.5), 1)
                                if analysis.lower() == "ndvi" and area_sq_m < 1e4:
                                    scale = max(scale, 20)
                                if area_sq_m < 100:
                                    logger.warning(f"Skipped {uc_name} — area too small ({area_sq_m:.2f} m²)")
                                    return

                            # Run analysis
                            if analysis.lower() == "aqi":
                                image, vis_params, scale = run_pixelwise_analysis(analysis, polygon, start_date, end_date)
                            else:
                                image, vis_params, _ = run_pixelwise_analysis(analysis, polygon, start_date, end_date)

                            if not image:
                                logger.warning(f"No image generated for {uc_name}")
                                return

                            # Clip & visualize
                            polygon_3857 = polygon.transform("EPSG:3857", maxError=1)
                            image = image.clip(polygon_3857)

                            # Compute min/max for visualization
                            try:
                                stats = image.reduceRegion(
                                    reducer=ee.Reducer.percentile([5, 95]),
                                    geometry=polygon,
                                    scale=scale,
                                    bestEffort=True,
                                    maxPixels=1e13
                                ).getInfo()
                                band_name = list(stats.keys())[0]
                                vmin = float(stats.get(f"{band_name}_p5", vis_params.get("min", 0)))
                                vmax = float(stats.get(f"{band_name}_p95", vis_params.get("max", 1)))
                                if vmin == vmax:
                                    vmax += 1e-3
                            except Exception:
                                vmin = vis_params.get("min", 0)
                                vmax = vis_params.get("max", 1)

                            vis_image = image.visualize(min=vmin, max=vmax, palette=vis_params.get("palette"))
                            vis_image = vis_image.reproject(crs="EPSG:3857", scale=scale)

                            # Export with retries
                            export_success = False
                            attempt = 0
                            max_attempts = 4
                            while not export_success and attempt < max_attempts:
                                try:
                                    attempt += 1
                                    geemap.ee_export_image(
                                        vis_image,
                                        filename=local_tif,
                                        scale=scale,
                                        file_per_band=False,
                                        crs="EPSG:3857"
                                    )
                                    if os.path.exists(local_tif) and os.path.getsize(local_tif) > 0:
                                        export_success = True
                                    else:
                                        raise Exception("Empty export")
                                except Exception as e:
                                    if "Total request size" in str(e):
                                        scale = min(scale * 2, 200)
                                        logger.info(f"Retrying {uc_name} with scale {scale}")
                                        time.sleep(2)
                                    else:
                                        logger.error(f"Export failed for {uc_name}: {e}")
                                        break
                            if not export_success:
                                return

                            # Build overviews
                            with rasterio.open(local_tif, "r+") as src:
                                factors = [2, 4, 8, 16]
                                valid_factors = [f for f in factors if f < min(src.width, src.height)]
                                if valid_factors:
                                    src.build_overviews(valid_factors, Resampling.nearest)
                                    src.update_tags(ns="rio_overview", resampling="nearest")

                            # Generate tiles
                            if os.path.exists(tiles_dir):
                                shutil.rmtree(tiles_dir)
                            os.makedirs(tiles_dir, exist_ok=True)

                            with COGReader(local_tif) as cog:
                                left, bottom, right, top = cog.bounds
                                transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
                                lon_left, lat_bottom = transformer.transform(left, bottom)
                                lon_right, lat_top = transformer.transform(right, top)

                                def scale_to_zoom(scale_m):
                                    return int(round(math.log2(156543.03392804097 / scale_m)))

                                target_zoom = max(0, min(18, scale_to_zoom(scale)))
                                min_zoom = max(0, target_zoom - 4)
                                max_zoom = min(18, target_zoom + 2)

                                for z in range(min_zoom, max_zoom + 1):
                                    n = 2 ** z
                                    tile_list = list(mercantile.tiles(lon_left, lat_bottom, lon_right, lat_top, [z]))
                                    tile_list = [t for t in tile_list if 0 <= t.x < n and 0 <= t.y < n]

                                    for t in tile_list:
                                        data, mask = cog.tile(t.x, t.y, t.z)
                                        if data is None:
                                            continue
                                        img = np.moveaxis(data, 0, 2)
                                        img = (img * 255).astype(np.uint8) if img.max() <= 1 else img
                                        if img.shape[2] == 3:
                                            alpha = np.any(img > 0, axis=2).astype(np.uint8) * 255
                                            img = np.dstack((img, alpha))
                                        pil_img = Image.fromarray(img, mode="RGBA")
                                        tile_path = os.path.join(tiles_dir, str(z), str(t.x))
                                        os.makedirs(tile_path, exist_ok=True)
                                        pil_img.save(os.path.join(tile_path, f"{t.y}.png"))

                        except Exception as e:
                            logger.error(f"Failed {uc_name}: {e}")

                    # Process all UCs in parallel
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = [executor.submit(process_uc, uc) for uc in ucs]
                        for f in as_completed(futures):
                            f.result()

        logger.info("All precompute tasks finished.")
