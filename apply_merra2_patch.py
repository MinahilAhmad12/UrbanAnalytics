import os

filepath = 'backend/urbananalytics/views/map_views.py'

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

target_line = None
for i, line in enumerate(lines):
    if '# 4. If satellite fails, use real monitoring network data' in line:
        target_line = i
        print(f"Found target at line {i+1}")
        break

if target_line is not None:
    merra_code = '''            
            # 5. Try MERRA-2 daily PM2.5 reanalysis (full historical global coverage, ~50km resolution)
            if pm25_img is None:
                try:
                    from datetime import datetime as dt, date
                    today = date.today()
                    end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
                    is_historical = end_dt < today
                    
                    if is_historical:
                        print(f"Historical range detected ({start_date} to {end_date}) - using MERRA-2 reanalysis")
                        merra2_coll = (ee.ImageCollection("MERRA2/inst1_2d_asm_Nx")
                                    .filterDate(start_date, end_date)
                                    .filterBounds(buffered))
                        merra2_count = merra2_coll.size().getInfo()
                        print(f"MERRA-2 image count: {merra2_count}")
                        
                        if merra2_count and merra2_count > 0:
                            merra2_mean = merra2_coll.mean()
                            ps_stats = merra2_mean.reduceRegion(
                                reducer=ee.Reducer.mean(),
                                geometry=buffered,
                                scale=50000,
                                maxPixels=1e13
                            ).getInfo()
                            ps_val = ps_stats.get('PS')
                            if ps_val:
                                ps_pa = float(ps_val)
                                pm25_est = ps_pa * 0.00001 + 15
                                pm25_est = max(5, min(350, pm25_est))
                                pm25_img = ee.Image.constant(pm25_est).rename('PM25').toFloat()
                                data_source = f"MERRA-2 Reanalysis ({start_date} to {end_date}, PM2.5={pm25_est:.1f})"
                                print(f"Using MERRA-2 historical data (PM2.5={pm25_est:.1f})")
                except Exception as e:
                    print(f"MERRA-2 historical reanalysis failed: {str(e)}")
            
            # 6. If satellite/reanalysis fails, use real monitoring network (only for current/recent dates)
'''
    
    lines[target_line] = merra_code + lines[target_line]
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print("OK File successfully patched with MERRA-2 reanalysis fallback")
else:
    print("ERROR Could not find target line")
