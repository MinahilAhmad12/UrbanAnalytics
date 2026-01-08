#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('backend/urbananalytics/views/map_views.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_text = """                except Exception as e:
                    print(f"VIIRS failed: {str(e)}")
            
            # # 4. If all satellite sources fail, generate synthetic variation based on UC location"""

new_text = """                except Exception as e:
                    print(f"VIIRS failed: {str(e)}")
            
            # 4. Try GWR PM2.5 (global PM2.5, 1km resolution, full historical)
            if pm25_img is None:
                try:
                    gwr_coll = (ee.ImageCollection("NASA/SEDAC/GPWv4/unmodelled_pm2_5")
                                .filterDate(start_date, end_date)
                                .filterBounds(buffered))
                    gwr_count = gwr_coll.size().getInfo()
                    print(f"GWR PM2.5 image count: {gwr_count}")
                    
                    if gwr_count and gwr_count > 0:
                        pm25_img = gwr_coll.mean().rename('PM25').clip(buffered)
                        data_source = "GWR PM2.5 (Hammer et al.)"
                        print("OK Using GWR PM2.5 data")
                except Exception as e:
                    print(f"GWR PM2.5 failed: {str(e)}")
            
            # # 5. If all satellite sources fail, generate synthetic variation based on UC location"""

if old_text in content:
    content = content.replace(old_text, new_text)
    with open('backend/urbananalytics/views/map_views.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("OK File updated successfully")
else:
    print("ERROR Old text not found in file")
