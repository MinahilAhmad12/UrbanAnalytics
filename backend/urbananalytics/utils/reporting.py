import io
import uuid
import base64
import statistics
from datetime import datetime

from django.template import Template, Context
from django.conf import settings
from weasyprint import HTML

import matplotlib
matplotlib.use("Agg")   
import matplotlib.pyplot as plt
import pandas as pd
import boto3
import numpy as np
from urbananalytics.utils.langgraph_summarizer import run_langgraph_summarizer


from urbananalytics.models import AreaAnalysis, Project, Report


REPORT_CONFIG = {
    "ndvi": {
        "palette": ["#ffffcc", "#c2e699", "#78c679", "#31a354", "#006837"],
        "table_border_color": "#006400",
        "heading_color": "#006400",
        "description": (
            "The NDVI (Normalized Difference Vegetation Index) measures the density and health of vegetation "
            "within the selected area. Higher NDVI values indicate healthy, dense vegetation, whereas lower values "
            "suggest barren or non-vegetated regions. This analysis evaluates how vegetation health varies across "
            "Union Councils (UCs) and helps to assess agricultural productivity, forest density, and the impact of "
            "urbanization on green cover during the selected date range."
        ),
        "categories": [
            ("No vegetation – bare soil, urban areas, water, or sand", None, 0.20),
            ("Sparse vegetation – few plants, grassland, low crop coverage", 0.20, 0.40),
            ("Moderate vegetation – healthy plants, crop fields", 0.40, 0.60),
            ("Dense vegetation – forests, parks, thick crops", 0.60, 0.80),
            ("Very dense vegetation – tropical forest, extremely healthy canopy", 0.80, None)
        ],
    },
    "thermal": {
        "palette": ["#00008B", "#00FFFF", "#00FF00", "#FFFF00","#FFA500","#FF4500", "#FF0000"],
        "table_border_color": "#FF6347",
        "heading_color": "#FF6347",
        "description": (
            "The Thermal analysis measures the surface temperature (in Kelvin) across different areas to identify "
            "urban heat zones, vegetation cooling effects, and land surface variations. High thermal readings often "
            "indicate dense urbanization and low vegetation, while lower readings are typical of greener or water-rich zones. "
            "Understanding this helps in addressing heat stress, improving urban design, and mitigating climate-related risks."
        ),
        "categories": [
            ("Very cold / coolest surfaces (shaded areas, water bodies)", None, 288),        
            ("Cool surfaces (vegetated zones, mild areas)", 288, 293),                        
            ("Moderate / mild surfaces (mixed land use)", 293, 298),                           
            ("Warm surfaces (built-up areas, roads)", 298, 303),                               
            ("Hot surfaces (urban heat islands, industrial zones)", 303, 308),                
            ("Very hot surfaces (deserts, bare soil)", 308, 313),                             
            ("Extremely hot / highest LST (rooftops, concrete)", 313, None),                 
        ]

    },
    "aqi": {
        "palette": ["#00E400", "#FFFF00", "#FF7E00", "#FF0000", "#8F3F97", "#7E0023"],
        "table_border_color": "#8A2BE2",
        "heading_color": "#8A2BE2",
        "description": (
            "The Air Quality Index (AQI) analysis is based on NO₂ concentration data and indicates the degree of "
            "pollution in the studied region. Lower AQI values denote good air quality, while higher values represent "
            "increasingly unhealthy conditions for humans and the environment. AQI is a critical factor in assessing "
            "urban livability, respiratory health risks, and the need for emission control strategies."
        ),
        "categories": [
            ("Good – Air quality is satisfactory, little or no health risk", None, 51),
            ("Moderate – Air quality acceptable, but sensitive groups may be affected", 51, 101),
            ("Unhealthy for Sensitive Groups – Sensitive people may experience health effects", 101, 151),
            ("Unhealthy – Everyone may begin to experience health effects", 151, 201),
            ("Very Unhealthy – Health alert: everyone may experience more serious effects", 201, 301),
            ("Hazardous – Health warnings of emergency conditions, entire population at risk", 301, None)
        ],
    }
}


def fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, bbox_inches='tight', dpi=150)
    buf.seek(0)
    data = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    return data





def generate_mean_distribution_chart(values, analysis_type, palette, categories):
    fig, ax = plt.subplots(figsize=(8, 4.5))

    if not values:
        values = [0]  

    min_val = min(values)
    max_val = max(values)

    
    bin_edges = []
    for i, (label, lo, hi) in enumerate(categories):
        
        if lo is None:
            lo_safe = min_val - 1
        else:
            lo_safe = lo
        bin_edges.append(lo_safe)
    
    last_hi = categories[-1][2] if categories[-1][2] is not None else max_val + 1
    bin_edges.append(last_hi)

    
    for i in range(1, len(bin_edges)):
        if bin_edges[i] <= bin_edges[i-1]:
            bin_edges[i] = bin_edges[i-1] + 0.01 

    
    def format_edge(val):
        return f"{val:.2f}" if val is not None else "∞"

    bin_labels = [f"{format_edge(categories[i][1])}–{format_edge(categories[i][2])}" for i in range(len(categories))]

    counts, _ = np.histogram(values, bins=bin_edges)

    colors = [palette[i] if i < len(palette) else "#cccccc" for i in range(len(counts))]

    bars = ax.bar(bin_labels, counts, color=colors, edgecolor="black", alpha=0.9)

    ax.set_title(f"{analysis_type.upper()} Mean Value Distribution", fontsize=14, fontweight="bold", pad=10)
    ax.set_xlabel("Mean Value Range", fontsize=12)
    ax.set_ylabel("Number of UCs", fontsize=12)
    ax.tick_params(axis='x', rotation=45, labelsize=10)
    ax.tick_params(axis='y', labelsize=10)
    ax.grid(axis='y', linestyle='--', alpha=0.5)

    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1, 
                str(count), ha='center', va='bottom', fontsize=9, fontweight='bold')

    fig.tight_layout()
    return fig_to_base64(fig)




def generate_pie_with_legend(counts, categories, palette, title):
    
    labels = [c[0] for c in categories]
    sizes = [counts.get(lbl, 0) for lbl in labels]
    colors = palette[:len(labels)]

    fig, ax = plt.subplots(figsize=(7, 5))  
    if sum(sizes) == 0:
        ax.text(0.5, 0.5, "No data", horizontalalignment='center', verticalalignment='center', fontsize=12)
    else:
        wedges, texts, autotexts = ax.pie(
            sizes, labels=None, autopct='%1.1f%%', startangle=90,
            colors=colors, textprops={'fontsize': 11}
        )
        ax.axis('equal')
    ax.set_title(title, fontsize=14, pad=12)
    fig.tight_layout()
    pie_b64 = fig_to_base64(fig)

    
    legend_items = []
    for i, label in enumerate(labels):
        legend_items.append({
            "color": colors[i] if i < len(colors) else "#CCCCCC",
            "label": label,
            "count": counts.get(label, 0)
        })
    return pie_b64, legend_items


def generate_summary_bar(stats_dict, title):
    fig, ax = plt.subplots(figsize=(6,3))
    keys = list(stats_dict.keys())
    values = [stats_dict[k] for k in keys]
    colors = ["#d95f02", "#1b9e77", "#7570b3", "#e7298a"][:len(keys)]
    ax.bar(keys, values, color=colors)
    ax.set_title(title)
    ax.grid(axis='y', linestyle='--', linewidth=0.4, alpha=0.6)
    fig.tight_layout()
    return fig_to_base64(fig)



def generate_dynamic_insights(analysis_type, stats, counts, categories):
    """
    Uses LangGraph summarizer (LangGraph pipeline) for AI-based insights.
    """
    
    report_text = f"""
    Analysis Type: {analysis_type}
    Mean: {stats['mean']}
    Min: {stats['min']}
    Max: {stats['max']}
    Std Dev: {stats['std']}
    Category Counts: {counts}
    """

    
    summary, interpretation, recommendation = run_langgraph_summarizer(
        report_text=report_text,
        report_type="average"
    )

    
    rec_list = [r.strip("-• ").strip() for r in recommendation.split("\n") if r.strip()]
    return interpretation, rec_list


HTML_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<style>
@page {
    size: A4;
    margin: 22mm 18mm;

    @bottom-left {
        content: "Page " counter(page) " of " counter(pages);
        font-size: 12px;
        color: {{heading_color}}; /* analysis type color */
    }
}
body {
  font-family: DejaVu Sans, Arial, sans-serif;
  color:#222;
  line-height:1.5;
  font-size:16px;
}

/* main header */
.top-header { text-align:center; padding:14px 10px; border-radius:8px; margin-bottom:20px; }
.report-title { font-size:34px; font-weight:800; color:#fff; padding:10px 16px; display:inline-block; border-radius:8px; }

/* header row */
.header-row { display:flex; justify-content:space-between; align-items:flex-start; gap:14px; margin-bottom:24px; }
.left-meta { flex:1;font-size:15px; }
.right-project { width:320px; border:2px solid #eee; padding:14px; border-radius:8px; background:#fafafa; }

/* headings and section layout */
.section { margin-top:36px; margin-bottom:12px; }
.section h3 { font-size:22px; margin:10px 0; color:{{heading_color}}; font-weight:700; }
.section p { margin-top:8px; margin-bottom:8px; }

/* tables */
.table { width:100%; border-collapse:collapse; margin-top:12px; font-size:14px; }
.table th {
  padding:8px 10px;
  text-align:left;
  background: {{table_border_color}};
  color:#fff;
  font-weight:700;
  border:1px solid {{table_border_color}};
  font-size:13px;
}
.table td {
  padding:6px 8px;
  border:1px solid #e6e6e6;
  vertical-align:middle;
  font-size:13px;
}

.table tbody tr:nth-child(even) { background:#fbfbfb; }

/* color swatch */
.color-swatch { width:38px; height:16px; display:inline-block; border:1px solid #ccc; margin-right:8px; }

/* charts */
.chart { text-align:center; margin-top:18px; margin-bottom:18px; }
.chart img { border:1px solid #eee; border-radius:8px; }

/* legend for pie chart */
.legend-container { display:flex; justify-content:center; margin-top:10px; }
.legend-grid {
  display:grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap:10px 20px;
  justify-items:start;
  font-size:13px;
}

/* summary stats */
.stats-center { display:flex; justify-content:center; gap:24px; margin-top:16px; flex-wrap:wrap; }
.stat-box { min-width:140px; padding:12px; border-radius:8px; color:#fff; font-weight:700; text-align:center; font-size:14px; }

/* footer */
.footer { margin-top:28px; color:#666; font-size:12px; text-align:center; }
/* Disclaimer box */
.disclaimer-box {
    background-color: #fff3cd;  /* light yellow */
    border-left: 4px solid #ffeeba;  /* darker yellow border */
    padding: 10px 14px;
    margin-bottom: 12px;
    border-radius: 6px;
    font-size: 13px;
    color: #856404;  /* dark yellow/brown text */
    line-height: 1.4;
}

</style>

</head>
<body>

<!-- Main header (colored) -->
<div class="top-header" style="background:{{heading_color}}22; padding-top:6px; padding-bottom:12px;">
  <div class="report-title" style="background:{{heading_color}};">Average Analysis Report</div>
  <div style="margin-top:8px; font-size:12px; color:#444;">Generated: {{generated_on}}</div>
</div>

<div class="header-row">
  <div class="left-meta">
    <h4 style="margin:0 0 6px 0; color:#333;">Analysis</h4>
    <div class="small"><strong>Type:</strong> {{analysis_type|upper}}</div>
    <div class="small"><strong>Date range:</strong> {{report_date_range}}</div>
  </div>

  <div class="right-project">
    <h4 style="margin:0 0 6px 0; color:{{heading_color}};">Project Info</h4>
    <div class="small"><strong>Project:</strong> {{project_name}}</div>
    <div class="small"><strong>City:</strong> {{city_name}}</div>
    <div class="small"><strong>Report type:</strong> {{report_type|default:"average"}}</div>
  </div>
</div>

<div class="section">
  <h3>Analysis Overview</h3>
  <p class="small">{{description}}</p>
</div>

<div class="section">
  <h3>Analysis Data</h3>
  <table class="table">
    <thead>
      <tr>
        <th>UC Name</th><th>City</th><th>Mean</th><th>Color</th>
      </tr>
    </thead>
    <tbody>
      {% for r in results %}
      <tr>
        <td style="width:36%;">{{ r.uc_name }}</td>
        <td style="width:20%;">{{ r.city_name }}</td>
        <td style="width:12%;">{{ r.mean_value }}</td>
        <td style="width:14%;"><span class="color-swatch" style="background:{{ r.color }};"></span> {{ r.color }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<div class="section chart">
  <h3>{{analysis_type|upper}} Mean Value Distribution (Count of UCs per Range)</h3>
  <img src="data:image/png;base64,{{ barh_chart }}" style="width:100%; max-height:520px;" />
  <p style="font-size:12px; color:#555; margin-top:8px; text-align:center;">
    {{mean_chart_caption}}
  </p>
</div>

<div class="section chart">
  <h3>Category Distribution</h3>
  <div style="
      display: flex; 
      align-items: flex-start; 
      justify-content: flex-start; 
      gap: 40px; 
      margin-top: 25px;
      flex-wrap: wrap;
  ">
    <!-- Left: Pie chart -->
    <div style="
        flex: 0 0 45%; 
        text-align: center;
    ">
      <img src="data:image/png;base64,{{ pie_chart }}" 
           style="width: 100%; max-width: 420px; border-radius: 8px; border: 2px solid #ccc;" />
    </div>

    <!-- Right: Legend section -->
    <div style="
        flex: 1;
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
        gap: 8px 16px;
        align-items: start;
        padding-top: 10px;
        border-left: 3px solid #ddd;
        padding-left: 20px;
    ">
      {% for item in legend %}
      <div style="
          display:flex; 
          align-items:flex-start; 
          gap:8px; 
          word-break: break-word;
      ">
        <div style="
            width: 22px; 
            height: 18px; 
            background: {{item.color}}; 
            border: 1px solid #aaa; 
            border-radius: 3px;
            flex-shrink: 0;
            margin-top: 2px;
        "></div>
        <div style="
            font-size:13px; 
            line-height:1.3; 
            word-wrap: break-word; 
            max-width: 140px;
        ">
          {{item.label}}
        </div>
      </div>
      {% endfor %}
    </div>
  </div>
  <p style="font-size:12px; color:#555; margin-top:10px; text-align:center;">
    {{category_chart_caption}}
  </p>
</div>


<div class="section" style="text-align:center;">
  <h3>Summary Statistics</h3>
  <table class="table" style="margin-left:auto; margin-right:auto; width:60%;">
    <thead>
      <tr>
        <th style="
          background:{{table_border_color}};
          color:#fff;
          text-align:center;
          font-size:15px;
          padding:10px;
        ">Stat</th>
        <th style="
          background:{{table_border_color}};
          color:#fff;
          text-align:center;
          font-size:15px;
          padding:10px;
        ">Value</th>
      </tr>
    </thead>
    <tbody>
      <tr><td>Count</td><td>{{stats.count}}</td></tr>
      <tr><td>Mean</td><td>{{stats.mean}}</td></tr>
      <tr><td>Minimum</td><td>{{stats.min}}</td></tr>
      <tr><td>Maximum</td><td>{{stats.max}}</td></tr>
      <tr><td>Std. Dev.</td><td>{{stats.std}}</td></tr>
    </tbody>
  </table>

  <div class="stats-center">
    <div class="stat-box" style="background:{{heading_color}};">Avg<br>{{stats.mean}}</div>
    <div class="stat-box" style="background:#2b8cbe;">Min<br>{{stats.min}}</div>
    <div class="stat-box" style="background:#e07b39;">Max<br>{{stats.max}}</div>
    <div class="stat-box" style="background:#6a4c9a;">Std<br>{{stats.std}}</div>
  </div>
</div>

<div class="section">
  <h3>Legend (Color Palette)</h3>
  <div class="legend">
    {% for item in legend %}
      <div class="legend-item"><span class="color-swatch" style="background:{{item.color}};"></span>{{item.label}}</div>
    {% endfor %}
  </div>
</div>

<div class="section">
  <div class="disclaimer-box">
    {{disclaimer}}
  </div>
</div>

<div class="section">
  <h3>Interpretation</h3>
  <p class="small">{{interpretation}}</p>
</div>


<div class="section recommendations">
  <h3>Recommendations</h3>
  <div class="small">
    <ul>
    {% for rec in recommendations %}
      <li>{{rec}}</li>
    {% endfor %}
    </ul>
  </div>
</div>


<div class="footer">Generated by Urban Analytics • {{generated_on}}</div>
</body>
</html>
"""
def generate_report_with_ai(report_text, report_type):
    summary, interpretation, recommendation = run_langgraph_summarizer(
        report_text=report_text,
        report_type=report_type
    )
    return interpretation, recommendation,summary


def generate_average_report(project_id, analysis_type, report_type, area_type, start_date, end_date, created_by):
    analysis_type = analysis_type.lower()
    report_type = report_type.lower()
    cfg = REPORT_CONFIG.get(analysis_type)
    if not cfg:
        raise ValueError("Unsupported analysis_type")

    
    q = AreaAnalysis.objects.filter(
        project_id=project_id,
        analysis_type=analysis_type,
        start_date=start_date,
        end_date=end_date,
        area_type=area_type,
        is_pixelwise=False
    ).order_by('uc_name')

    results = []
    values = []
    for a in q:
        stats_dict = a.stats if isinstance(a.stats, dict) else {}
        mean = stats_dict.get("mean")
        if mean is None:
            continue
        results.append({
            "uc_name": a.uc_name,
            "city_name": a.city_name,
            "mean_value": round(mean, 4),
            "color": stats_dict.get("color", "#000000"),
            "source": stats_dict.get("source", "")
        })
        values.append(mean)

    if not results:
        raise ValueError("No cached AreaAnalysis results for this query. Run average analysis first.")

    df = pd.DataFrame(results)

    stats = {
        "count": len(values),
        "mean": round(statistics.mean(values), 4) if values else 0,
        "min": round(min(values), 4) if values else 0,
        "max": round(max(values), 4) if values else 0,
        "std": round(statistics.pstdev(values), 4) if len(values) > 1 else 0
    }

    
    categories = cfg["categories"]
    def bucket_value(v):
        for label, lo, hi in categories:
            lo_check = True if lo is None else lo <= v
            hi_check = True if hi is None else v < hi
            
            if lo_check and hi_check:
                return label
        return "Unknown"


    counts = {}
    for v in values:
        label = bucket_value(v)
        counts[label] = counts.get(label, 0) + 1

    
    barh_chart = generate_mean_distribution_chart(values, analysis_type, cfg["palette"], cfg["categories"])
    pie_chart, legend_items = generate_pie_with_legend(counts, categories, cfg.get("palette", []), f"{analysis_type.upper()} category distribution")
    summary_bar = generate_summary_bar({'min': stats['min'], 'mean': stats['mean'], 'max': stats['max'], 'std': stats['std']}, "Summary")
    


    
    palette = cfg.get("palette", [])
    legend = []
    for i, color in enumerate(palette):
        label = categories[i][0] if i < len(categories) else f"Level {i+1}"
        legend.append({"color": color, "label": label})

    interpretation, recommendations = generate_dynamic_insights(analysis_type, stats, counts, categories)
    
    if analysis_type == "ndvi":
        mean_chart_caption = (
            "This bar chart shows the number of Union Councils (UCs) falling within specific NDVI mean value ranges. "
            "Higher NDVI values indicate healthier vegetation, while lower values correspond to barren or stressed areas. "
            "The distribution helps visualize vegetation health patterns and identify regions requiring ecological attention."
        )
        category_chart_caption = (
            "This pie chart represents the proportion of UCs across NDVI-based vegetation health categories. "
            "It visually summarizes how much of the area falls under each vegetation condition — from dense green zones "
            "to sparse or degraded regions."
        )

    elif analysis_type == "thermal":
        mean_chart_caption = (
            "This bar chart displays the distribution of Union Councils (UCs) based on their mean surface temperatures. "
            "Cooler temperature ranges often correspond to vegetated or water-covered zones, while higher temperatures "
            "indicate built-up areas or urban heat islands."
        )
        category_chart_caption = (
            "This pie chart highlights the percentage of UCs that fall under various temperature categories. "
            "It helps in understanding how surface heat is spatially distributed and identifying potential heat stress zones."
        )

    elif analysis_type == "aqi":
        mean_chart_caption = (
            "This bar chart illustrates the count of UCs that lie within specific AQI (Air Quality Index) ranges. "
            "Lower AQI values represent cleaner air, while higher values indicate areas with significant air pollution."
        )
        category_chart_caption = (
            "This pie chart shows the proportion of UCs in each air quality category. "
            "It provides a quick overview of pollution severity levels and the extent of affected regions."
        )

    else:
        mean_chart_caption = "This chart shows the count of Union Councils per calculated range."
        category_chart_caption = "This chart displays the distribution of categories for the selected analysis type."


    project_name = f"Project {project_id}"
    city_name = df['city_name'].iloc[0] if 'city_name' in df and not df.empty else ""

    
    rendered = Template(HTML_TEMPLATE).render(Context({
        "generated_on": datetime.utcnow().strftime("%d %b %Y %H:%M UTC"),
        "project_name": project_name,
        "city_name": city_name,
        "analysis_type": analysis_type,
        "report_type": report_type,
        "report_date_range": f"{start_date} → {end_date}",
        "description": cfg.get("description", ""),
        "results": results,
        "barh_chart": barh_chart,
        "pie_chart": pie_chart,
        "summary_bar": summary_bar,
        "stats": stats,
        "interpretation": interpretation,
        "recommendations": recommendations,
        "legend": legend,
        "legend_items": legend_items,
        "table_border_color": cfg.get("table_border_color", "#333"),
        "heading_color": cfg.get("heading_color", "#333"),
        'mean_chart_caption': mean_chart_caption,
        'category_chart_caption': category_chart_caption,
        "disclaimer": (
              "The interpretations and recommendations are derived from a robust analysis "
              "of environmental data using AI-assisted tools. They provide indicative insights "
              "and are intended to support decision-making, but should be validated by domain experts "
              "before implementation."
          ),
    }))

    
    pdf_bytes = HTML(string=rendered).write_pdf()

    
    report = Report.objects.create(
        project_id=project_id,
        analysis_type=analysis_type,
        report_type=report_type,
        area_type=area_type,
        start_date=start_date,
        end_date=end_date,
        created_by=created_by,
        message=f"{report_type.capitalize()} {analysis_type.upper()} report ({start_date} → {end_date})"
    )

    
    filename_only = f"{area_type}_{analysis_type}_{report_type}_{project_id}_{start_date}_{end_date}.pdf"
    s3_key = f"reports/{report_type}/{project_id}/{report.id}/{filename_only}"

    
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
        aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
        region_name=getattr(settings, "AWS_S3_REGION_NAME", None)
    )
    bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)

    s3_client.put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=pdf_bytes,
        ContentType="application/pdf"
    )

    
    public_url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{s3_key}"

    
    report.file = public_url
    report.save(update_fields=["file"])

    return {"report": report, "s3_key": s3_key, "s3_url": public_url}