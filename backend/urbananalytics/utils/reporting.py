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
        "palette": ["#E7E0E0", "#FFFF00", "#90EE90", "#008000", "#006400"],
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
            ("No vegetation / bare soil", 0.00, 0.20),
            ("Sparse vegetation / stressed crops", 0.20, 0.40),
            ("Moderately healthy vegetation", 0.40, 0.60),
            ("Dense healthy vegetation", 0.60, 0.80),
            ("Very dense & healthy vegetation (forests)", 0.80, 1.00)
        ],
    },
    "thermal": {
        "palette": ["#87CEEB", "#32CD32", "#FF6347", "#FFA500", "#800080"],
        "table_border_color": "#FF6347",
        "heading_color": "#FF6347",
        "description": (
            "The Thermal analysis measures the surface temperature (in Kelvin) across different areas to identify "
            "urban heat zones, vegetation cooling effects, and land surface variations. High thermal readings often "
            "indicate dense urbanization and low vegetation, while lower readings are typical of greener or water-rich zones. "
            "Understanding this helps in addressing heat stress, improving urban design, and mitigating climate-related risks."
        ),
        "categories": [
            ("Cool (water bodies, shaded regions)", 290, 295),
            ("Slightly cool, vegetated zones", 295, 300),
            ("Moderate temperature: mixed land use", 300, 305),
            ("Hot zones: built-up areas, roads", 305, 310),
            ("Very hot: urban heat islands, deserts", 310, 320),
        ],
    },
    "aqi": {
        "palette": ["#FFC0CB", "#FF7F50", "#FFBF00", "#FFFFE0", "#FF00FF", "#8A2BE2"],
        "table_border_color": "#8A2BE2",
        "heading_color": "#8A2BE2",
        "description": (
            "The Air Quality Index (AQI) analysis is based on NO₂ concentration data and indicates the degree of "
            "pollution in the studied region. Lower AQI values denote good air quality, while higher values represent "
            "increasingly unhealthy conditions for humans and the environment. AQI is a critical factor in assessing "
            "urban livability, respiratory health risks, and the need for emission control strategies."
        ),
        "categories": [
            ("Good air quality", 0, 5),
            ("Moderate, acceptable", 5, 10),
            ("Unhealthy for sensitive groups", 10, 15),
            ("Unhealthy", 15, 20),
            ("Very unhealthy", 20, 25),
            ("Hazardous air quality", 25, 30)
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

    
    bin_edges = [cat[1] for cat in categories] + [categories[-1][2]]  
    bin_labels = [f"{categories[i][1]:.2f}–{categories[i][2]:.2f}" for i in range(len(categories))]
    
    counts, _ = np.histogram(values, bins=bin_edges)
    
    
    colors = []
    for i in range(len(counts)):
        if i < len(palette):
            colors.append(palette[i])
        else:
            colors.append("#cccccc")

    
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


# def generate_dynamic_insights(analysis_type, stats, counts, categories):
#     total = sum(counts.values()) or 1
#     dominant_category = max(counts, key=counts.get) if counts else "N/A"
#     dominant_percent = (counts.get(dominant_category, 0) / total) * 100 if total else 0
#     mean_val = stats['mean']
#     interpretation = ""
#     recommendations = []

#     if analysis_type == "ndvi":
#         if mean_val < 0.3:
#             interpretation = (
#                 f"Overall vegetation condition across the analyzed area is poor (average NDVI = {mean_val:.2f}). "
#                 f"A significant portion of the region falls under the '{dominant_category}' category, "
#                 f"covering nearly {dominant_percent:.1f}% of UCs. The results indicate stressed vegetation, "
#                 "possibly due to prolonged dry periods, soil degradation, or lack of irrigation infrastructure. "
#                 "These areas require immediate ecological attention to prevent further decline in green cover."
#             )
#             recommendations = [
#                 "Introduce efficient irrigation systems and adopt drought-resistant crop varieties.",
#                 "Implement reforestation programs in low-NDVI UCs to restore vegetation density.",
#                 "Encourage sustainable agricultural practices and soil conservation methods.",
#                 "Increase public awareness about deforestation and urban encroachment impacts.",
#                 "Use satellite monitoring every quarter to observe recovery trends."
#             ]
#         elif mean_val < 0.6:
#             interpretation = (
#                 f"The region exhibits moderately healthy vegetation (average NDVI = {mean_val:.2f}), "
#                 f"with '{dominant_category}' dominating ({dominant_percent:.1f}% of UCs). "
#                 "Some localized zones show signs of vegetation stress, indicating uneven agricultural health. "
#                 "While most parts remain productive, sustained land management and water regulation are required "
#                 "to prevent degradation over time."
#             )
#             recommendations = [
#                 "Maintain irrigation schedules and monitor soil moisture regularly.",
#                 "Introduce crop rotation and organic fertilizers to maintain soil fertility.",
#                 "Encourage precision farming using satellite-based insights.",
#                 "Identify and support UCs with below-average NDVI values through targeted interventions.",
#                 "Adopt community-based plantation drives in semi-arid pockets."
#             ]
#         else:
#             interpretation = (
#                 f"The vegetation condition is excellent (average NDVI = {mean_val:.2f}). "
#                 f"Most UCs fall within the '{dominant_category}' class, indicating dense and healthy vegetation cover. "
#                 "This reflects successful agricultural and ecological management. However, continual monitoring "
#                 "is essential to ensure that expanding urban infrastructure does not reduce these green zones in the future."
#             )
#             recommendations = [
#                 "Preserve forest zones and prevent conversion of green lands into construction sites.",
#                 "Promote agroforestry and mixed cropping for long-term ecological balance.",
#                 "Monitor temperature and precipitation trends to safeguard vegetation health.",
#                 "Use this NDVI dataset to identify high-potential zones for eco-tourism or conservation.",
#                 "Share success models from high-performing UCs with surrounding communities."
#             ]

#     elif analysis_type == "thermal":
#         if mean_val < 300:
#             interpretation = (
#                 f"The overall surface temperature is relatively cool (average {mean_val:.1f} K), "
#                 f"with '{dominant_category}' dominating ({dominant_percent:.1f}% of UCs). "
#                 "The presence of cooler surfaces indicates healthy vegetation and water bodies acting as natural coolants. "
#                 "These conditions are favorable for both human comfort and ecological sustainability."
#             )
#             recommendations = [
#                 "Protect and expand vegetated and water-covered areas to maintain cool surface temperatures.",
#                 "Encourage green roofing and reflective building materials in new developments.",
#                 "Integrate tree planting along roads and public spaces for better heat regulation.",
#                 "Monitor land-use changes to prevent loss of natural cooling zones.",
#                 "Continue observation across multiple seasons to detect early signs of heat buildup."
#             ]
#         elif mean_val < 308:
#             interpretation = (
#                 f"The analyzed area shows moderate surface temperatures (average {mean_val:.1f} K). "
#                 f"'{dominant_category}' represents around {dominant_percent:.1f}% of UCs, "
#                 "indicating balanced conditions but rising urban heat in certain locations. "
#                 "Built-up surfaces and reduced vegetation could be contributing to localized temperature peaks."
#             )
#             recommendations = [
#                 "Increase vegetation density in built-up areas through pocket parks and rooftop gardens.",
#                 "Adopt reflective materials and light-colored surfaces in construction to reduce heat absorption.",
#                 "Expand monitoring to identify consistently hot UCs and assess their contributing factors.",
#                 "Promote energy-efficient urban planning that reduces heat emissions.",
#                 "Implement awareness campaigns on heat safety and sustainable city design."
#             ]
#         else:
#             interpretation = (
#                 f"The area shows high surface temperatures (average {mean_val:.1f} K), "
#                 f"dominated by '{dominant_category}' ({dominant_percent:.1f}% of UCs). "
#                 "This suggests a strong urban heat island effect, particularly in highly developed regions. "
#                 "The heat levels may adversely affect air quality, water evaporation, and human well-being if left unmitigated."
#             )
#             recommendations = [
#                 "Develop urban greening programs targeting the hottest UCs first.",
#                 "Mandate green spaces in residential and commercial construction projects.",
#                 "Increase the use of high-albedo and cool pavement technologies.",
#                 "Establish heat-monitoring networks and provide public heat alerts.",
#                 "Prioritize afforestation around industrial or densely populated areas."
#             ]
#     elif analysis_type == "aqi":
#         if mean_val < 5:
#             interpretation = (
#                 f"The air quality across most UCs is excellent (average AQI = {mean_val:.1f}). "
#                 f"'{dominant_category}' accounts for approximately {dominant_percent:.1f}% of the region. "
#                 "This indicates minimal industrial or vehicular pollution, likely due to sufficient greenery and "
#                 "low emission activity. The atmosphere is well-balanced for public health and environmental safety."
#             )
#             recommendations = [
#                 "Maintain strict emission control standards and encourage renewable energy adoption.",
#                 "Promote non-motorized and public transport systems to sustain low NO₂ levels.",
#                 "Continue afforestation programs to absorb airborne pollutants.",
#                 "Regularly monitor pollutant levels to maintain compliance with air quality standards.",
#                 "Educate citizens about preserving clean air through community initiatives."
#             ]
#         elif mean_val < 15:
#             interpretation = (
#                 f"The air quality is moderate (average AQI = {mean_val:.1f}). "
#                 f"'{dominant_category}' dominates ({dominant_percent:.1f}% of UCs), "
#                 "indicating a gradual increase in emissions possibly from traffic or small industries. "
#                 "While still acceptable, air quality must be actively managed to prevent further deterioration."
#             )
#             recommendations = [
#                 "Introduce stricter emissions policies in moderately polluted zones.",
#                 "Enhance public transport infrastructure to reduce vehicle dependence.",
#                 "Deploy air quality monitoring sensors at UC level for continuous observation.",
#                 "Encourage clean-energy adoption in domestic and industrial sectors.",
#                 "Conduct periodic awareness campaigns on pollution prevention and mitigation."
#             ]
#         else:
#             interpretation = (
#                 f"The AQI results reveal poor air quality (average AQI = {mean_val:.1f}), "
#                 f"with '{dominant_category}' covering {dominant_percent:.1f}% of UCs. "
#                 "These values exceed safe thresholds, signaling heavy pollution from traffic, industry, or open burning. "
#                 "Immediate regulatory and community-level interventions are essential to protect public health."
#             )
#             recommendations = [
#                 "Implement emergency air pollution control measures such as traffic restrictions.",
#                 "Ban open burning and impose emission limits on industrial facilities.",
#                 "Launch public health advisories for sensitive populations.",
#                 "Promote urban green belts and air-purifying vegetation.",
#                 "Invest in clean energy transitions and emission-free public transportation."
#             ]
#     else:
#         interpretation = "No dynamic interpretation available."
#         recommendations = ["No specific recommendations available."]

#     return interpretation, recommendations
def generate_dynamic_insights(analysis_type, stats, counts, categories):
    """
    Uses LangGraph summarizer (LangGraph pipeline) for AI-based insights.
    """
    # Prepare text input for summarization
    report_text = f"""
    Analysis Type: {analysis_type}
    Mean: {stats['mean']}
    Min: {stats['min']}
    Max: {stats['max']}
    Std Dev: {stats['std']}
    Category Counts: {counts}
    """

    # Use 'average' report type for this report
    summary, interpretation, recommendation = run_langgraph_summarizer(
        report_text=report_text,
        report_type="average"
    )

    # Convert recommendation text into a list (split by newline or bullet)
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
      gap: 60px; 
      margin-top: 25px;
  ">
    <!-- Left: Pie chart -->
    <div style="
        flex: 0 0 45%; 
        text-align: center;
        display: flex; 
        justify-content: flex-end;
    ">
      <img src="data:image/png;base64,{{ pie_chart }}" 
           style="width: 100%; max-width: 420px; border-radius: 8px; border: 2px solid #ccc;" />
    </div>

    <!-- Right: Legend section -->
    <div style="
        flex: 1;
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
        align-items: flex-start;
        padding-top: 10px;
        border-left: 3px solid #ddd;
        padding-left: 40px;
    ">
      <h4 style="margin-bottom: 15px; font-size: 18px; color: #333;">Legend</h4>

      <div style="
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          gap: 12px;
          width: 100%;
      ">
        {% for item in legend %}
        <div style="
            display: flex; 
            align-items: center; 
            gap: 10px; 
            font-size: 14px; 
            line-height: 1.5; 
            width: 100%;
        ">
          <div style="
              width: 25px; 
              height: 18px; 
              background: {{item.color}}; 
              border: 1px solid #aaa; 
              border-radius: 3px;
          "></div>
          <div style="flex: 1; text-align: left;">
            <strong>{{item.label}}</strong>
          </div>
        </div>
        {% endfor %}
      </div>
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
            if lo <= v < hi or (hi == categories[-1][2] and lo <= v <= hi):
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