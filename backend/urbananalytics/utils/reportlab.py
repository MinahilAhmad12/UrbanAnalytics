import os
import uuid
import matplotlib
from reportlab.platypus import Table, TableStyle
from reportlab.lib.enums import TA_LEFT

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from urbananalytics.models import YearlyAnalysis, BeforeAfterAnalysis, Project
from reportlab.platypus import KeepTogether
import boto3
from reportlab.platypus import KeepTogether, PageBreak
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from urbananalytics.models import Report
from django.core.files import File
from datetime import datetime
from urbananalytics.utils.langgraph_summarizer import run_langgraph_summarizer
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_S3_REGION_NAME,
)


def _ensure_reports_dir():
    reports_dir = os.path.join(settings.MEDIA_ROOT, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    return reports_dir


def _unique_filename(base_name, ext):
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    uid = uuid.uuid4().hex[:8]
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in base_name)
    return f"{safe}_{ts}_{uid}.{ext}"


def upload_report_to_s3(
    local_path, project_id, year, api_name="generate_yearly_report"
):
    """Upload generated report (PDF/CSV) to S3 under API-specific folder and return public URL"""
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    s3_domain = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}"

    filename = os.path.basename(local_path)
    s3_key = f"reports/{api_name}/{project_id}/{year}/{filename}"

    s3_client.upload_file(local_path, bucket_name, s3_key)

    if os.path.exists(local_path):
        os.remove(local_path)

    return f"{s3_domain}/{s3_key}"



class NumberedCanvas(canvas.Canvas):
    """Canvas subclass that supports Page X of Y numbering."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        """Add page count to each page (Page X of Y)."""
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(total_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, total_pages):
        page = self.getPageNumber()
        text = f"Page {page} of {total_pages}"
        self.setFont("Helvetica", 9)
        self.drawRightString(200 * mm, 10 * mm, text)


def create_annual_report_pdf(instances, filename=None, created_by=None):
    """
    Generate annual environmental report PDF.
    Returns absolute path to the generated file.
    """
    if not instances.exists():
        raise ValueError("No instances provided for PDF")

    reports_dir = _ensure_reports_dir()

    instance = instances.first()
    project = getattr(instance, "project", None)
    project_name = (
        getattr(project, "name", None)
        or getattr(project, "project_name", None)
        or "N/A"
    )
    base = f"{instance.analysis_type}_{instance.year}_{instance.area_type}"
    filename = filename or _unique_filename(base, "pdf")
    file_path = os.path.join(reports_dir, filename)


    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )
    styles = getSampleStyleSheet()
    story = []
    temp_files = []

   
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        fontSize=20,
        leading=22,
        spaceAfter=12,
    )
   
    analysis_type_lower = instance.analysis_type.lower()

    primary_color = "#2E86C1"  
    table_header_color = "#2E86C1"
    chart_title_color = "#2E86C1"

    if analysis_type_lower == "ndvi":
        primary_color = "#1B5E20"  
        table_header_color = "#2E7D32"  
        chart_title_color = "#2E7D32"  
       
    elif analysis_type_lower == "aqi":
        primary_color = "#1565C0"  
        table_header_color = "#1565C0"  
        chart_title_color = "#1565C0"  
    elif analysis_type_lower == "thermal":
        primary_color = "#E65100"  
        table_header_color = "#F57C00"  
        chart_title_color = "#E65100"  

   
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        fontSize=20,
        leading=22,
        spaceAfter=12,
        textColor=colors.HexColor(primary_color),
    )

    section_title = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        textColor=colors.HexColor(primary_color),
        fontSize=14,
        spaceAfter=6,
    )
    normal = ParagraphStyle(
        "NormalText", parent=styles["Normal"], fontSize=11, leading=16
    )
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        alignment=TA_RIGHT,
        fontSize=9,
        textColor=colors.grey,
    )

    if analysis_type_lower == "ndvi":
        from reportlab.platypus import Table, TableStyle

        dark_green = colors.HexColor("#1B5E20")  
        light_green = colors.HexColor("#DFF0D8")  

        title_table = Table(
            [
                [
                    Paragraph(
                        "Urban Analytics – Annual Environmental Report",
                        ParagraphStyle(
                            "BannerTitle",
                            parent=styles["Heading1"],
                            alignment=TA_CENTER,
                            fontSize=20,
                            leading=24,
                            textColor=colors.white,
                        ),
                    )
                ]
            ],
            colWidths=[460],
        )
        title_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), dark_green),
                    ("BOX", (0, 0), (-1, -1), 0, dark_green),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )

        bg_table = Table([[title_table]], colWidths=[480])
        bg_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), light_green),
                    ("BOX", (0, 0), (-1, -1), 0, light_green),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),  
                    ("TOPPADDING", (0, 0), (-1, -1), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ]
            )
        )

        story.append(bg_table)
        story.append(Spacer(1, 14))
    elif analysis_type_lower == "aqi":
        from reportlab.platypus import Table, TableStyle

        dark_blue = colors.HexColor("#0D47A1")  
        light_blue = colors.HexColor("#E3F2FD")  

        title_table = Table(
            [
                [
                    Paragraph(
                        "Urban Analytics – Annual Environmental Report",
                        ParagraphStyle(
                            "BannerTitle",
                            parent=styles["Heading1"],
                            alignment=TA_CENTER,
                            fontSize=20,
                            leading=24,
                            textColor=colors.white,
                        ),
                    )
                ]
            ],
            colWidths=[460],
        )
        title_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), dark_blue),
                    ("BOX", (0, 0), (-1, -1), 0, dark_blue),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )

        bg_table = Table([[title_table]], colWidths=[480])
        bg_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), light_blue),
                    ("BOX", (0, 0), (-1, -1), 0, light_blue),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 12),  
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 12),  
                ]
            )
        )

        story.append(bg_table)
        story.append(Spacer(1, 14))
    elif analysis_type_lower == "thermal":
        from reportlab.platypus import Table, TableStyle

        dark_orange = colors.HexColor("#E65100")  
        light_orange = colors.HexColor("#FFF3E0")  

        title_table = Table(
            [
                [
                    Paragraph(
                        "Urban Analytics – Annual Environmental Report",
                        ParagraphStyle(
                            "BannerTitle",
                            parent=styles["Heading1"],
                            alignment=TA_CENTER,
                            fontSize=20,
                            leading=24,
                            textColor=colors.white,
                        ),
                    )
                ]
            ],
            colWidths=[460],
        )
        title_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), dark_orange),
                    ("BOX", (0, 0), (-1, -1), 0, dark_orange),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )

        bg_table = Table([[title_table]], colWidths=[480])
        bg_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), light_orange),
                    ("BOX", (0, 0), (-1, -1), 0, light_orange),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ]
            )
        )

        story.append(bg_table)
        story.append(Spacer(1, 14))

    else:
        story.append(
            Paragraph("Urban Analytics – Annual Environmental Report", title_style)
        )
        story.append(Spacer(1, 6))

   
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Project:</b> {project_name}", normal))
    story.append(Paragraph(f"<b>Area Type:</b> {instance.area_type}", normal))
    story.append(
        Paragraph(f"<b>Analysis Type:</b> {instance.analysis_type.upper()}", normal)
    )

    if hasattr(instance, "year"):
        story.append(Paragraph(f"<b>Year:</b> {instance.year}", normal))

    if (
        hasattr(
            instance,
            "comparison_years",
        )
        and instance.comparison_years
    ):
        story.append(
            Paragraph(f"<b>Compared Years:</b> {instance.comparison_years}", normal)
        )

    story.append(
        Paragraph(
            f"<b>Generated On:</b> {datetime.now().strftime('%d %b %Y %H:%M')}", normal
        )
    )
    story.append(Spacer(1, 14))

   
    story.append(Paragraph("1. Overview", section_title))
    story.append(
        Paragraph(
            f"This report presents an overview of <b>{instance.analysis_type.upper()}</b> patterns for the year "
            f"<b>{instance.year}</b>. It summarizes variations across urban units (UCs) based on mean satellite-derived "
            "indices. Higher values typically indicate better environmental conditions, while lower values highlight "
            "areas requiring ecological restoration or improvement efforts.",
            normal,
        )
    )
    story.append(Spacer(1, 12))


    story.append(Paragraph("2. Statistical Summary", section_title))
    data = [["UC Name", "City", "Mean Value", "Color"]]
    hist_values = []
    color_cells = []  

    for idx, inst in enumerate(instances, start=1):
        stats = inst.stats or {}
        mean_val = stats.get("mean", 0)
        hist_values.append(mean_val)
        color_hex = stats.get("color", "#FFFFFF") or "#FFFFFF"
        data.append(
            [
                inst.uc_name or "-",
                inst.city_name or "-",
                round(mean_val, 4),
                color_hex,  
            ]
        )
        color_cells.append((3, idx, color_hex))  

    table = Table(data, colWidths=[130, 130, 90, 90])
    table_style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(table_header_color)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-2, -1), [colors.whitesmoke, colors.lightgrey]),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
        ]
    )

    from reportlab.lib.utils import ImageReader

    for col, row, hex_code in color_cells:
        try:
            bg_color = colors.HexColor(hex_code)

            hex_str = hex_code.lstrip("#")
            r, g, b = tuple(int(hex_str[i : i + 2], 16) for i in (0, 2, 4))
            brightness = r * 0.299 + g * 0.587 + b * 0.114
            text_color = colors.black if brightness > 150 else colors.white

            table_style.add("BACKGROUND", (col, row), (col, row), bg_color)
            table_style.add("TEXTCOLOR", (col, row), (col, row), text_color)
            table_style.add("BOX", (col, row), (col, row), 0.3, colors.grey)

        except Exception:
            table_style.add("BACKGROUND", (col, row), (col, row), colors.white)
            table_style.add("TEXTCOLOR", (col, row), (col, row), colors.black)

    table.setStyle(table_style)
    story.append(table)
    story.append(Spacer(1, 12))
   
    story.append(Paragraph("3. Color Legend", section_title))

   
    if analysis_type_lower == "ndvi":
        legend_data = [
            ["#ffffcc", "No vegetation – bare soil, urban areas, water, sand (< 0.2)"],
            ["#c2e699", "Sparse vegetation – grassland, low crop cover (0.2 – 0.39)"],
            ["#78c679", "Moderate vegetation – healthy crops (0.4 – 0.59)"],
            ["#31a354", "Dense vegetation – forests, parks (0.6 – 0.79)"],
            ["#006837", "Very dense vegetation – extremely healthy canopy (≥ 0.8)"],
        ]

    elif analysis_type_lower == "thermal":
        legend_data = [
            ["#00008B", "Very cold (< 288 K | < 14.85 °C)"],
            ["#00FFFF", "Cool (288 – 292.99 K | 14.85 – 19.85 °C)"],
            ["#00FF00", "Moderate / Mild (293 – 297.99 K | 19.85 – 24.85 °C)"],
            ["#FFFF00", "Warm (298 – 302.99 K | 24.85 – 29.85 °C)"],
            ["#FFA500", "Hot (303 – 307.99 K | 29.85 – 34.85 °C)"],
            ["#FF4500", "Very Hot (308 – 312.99 K | 34.85 – 39.85 °C)"],
            ["#FF0000", "Extremely Hot (≥ 313 K | ≥ 39.85 °C)"],
        ]

    elif analysis_type_lower == "aqi":
        legend_data = [
            ["#00E400", "Good (0 – 50)"],
            ["#FFFF00", "Moderate (51 – 100)"],
            ["#FF7E00", "Unhealthy for Sensitive Groups (101 – 150)"],
            ["#FF0000", "Unhealthy (151 – 200)"],
            ["#8F3F97", "Very Unhealthy (201 – 300)"],
            ["#7E0023", "Hazardous (> 300)"],
        ]

    else:
        legend_data = [["#FFFFFF", "Legend not available for this analysis type."]]


    legend_table = Table(legend_data, colWidths=[80, 320])
    legend_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )

    for i, (color_code, _) in enumerate(legend_data):
        legend_table.setStyle(
            [("BACKGROUND", (0, i), (0, i), colors.HexColor(color_code))]
        )

    legend_table.hAlign = "CENTER"
    story.append(Spacer(1, 6))
    story.append(legend_table)
    story.append(Spacer(1, 16))
   
    if hist_values:
        overall_mean = round(float(np.mean(hist_values)), 4)
        min_val = round(float(np.min(hist_values)), 4)
        max_val = round(float(np.max(hist_values)), 4)
        hetero_val = round(float(np.std(hist_values)), 4)
   
    try:
        report_text = f"""
        Analysis Type: {instance.analysis_type}
        Year: {instance.year}
        Mean: {overall_mean}
        Min: {min_val}
        Max: {max_val}
        Std Dev: {hetero_val}
        UC Count: {len(hist_values)}
        """

        summary, interpretation, recommendation = run_langgraph_summarizer(
            report_text=report_text, report_type="annual"
        )

    except Exception as e:
        print("LangGraph summarization failed:", e)
        summary, interpretation, recommendation = ("", "", "")

   
    summary_data = [
        ["Metric", "Value"],
        ["Total Urban Units", len(hist_values)],
        ["Average Value", overall_mean],
        ["Minimum Value", min_val],
        ["Maximum Value", max_val],
        ["Heterogeneity (Std. Dev.)", hetero_val],
    ]
    summary_table = Table(summary_data, colWidths=[220, 160])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(table_header_color)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
            ]
        )
    )
    story.append(Paragraph("4. Overall Summary Statistics", section_title))
    story.append(summary_table)
    story.append(Spacer(1, 14))

   
    try:
        if hist_values:
            line_path = os.path.join(
                reports_dir,
                _unique_filename(
                    f"summary_{instance.analysis_type}_{instance.year}", "png"
                ),
            )
            metrics = ["Min", "Max", "Avg", "Heterogeneity"]
            values = [min_val, max_val, overall_mean, hetero_val]
            colors_list = ["#E74C3C", "#2ECC71", "#3498DB", "#F1C40F"]

            plt.figure(figsize=(5.8, 3.2))
            plt.plot(
                metrics, values, marker="o", linewidth=2.5, color="#34495E", alpha=0.8
            )
            for i, val in enumerate(values):
                plt.scatter(
                    metrics[i],
                    val,
                    color=colors_list[i],
                    s=90,
                    edgecolors="black",
                    linewidths=0.7,
                    zorder=5,
                )
                plt.text(
                    metrics[i],
                    val + (0.015 if val != 0 else 0.01),
                    f"{val:.3f}",
                    ha="center",
                    fontsize=9,
                    fontweight="bold",
                    color="#2C3E50",
                )
            plt.title(
                f"{instance.analysis_type.upper()} Summary Statistics ({instance.year})",
                fontsize=11,
                fontweight="bold",
                color="#2C3E50",
                pad=10,
            )
            plt.ylabel("Value", fontsize=9)
            plt.grid(alpha=0.3, linestyle="--", linewidth=0.7)
            plt.legend(
                ["Trend", "Min", "Max", "Avg", "Heterogeneity"],
                fontsize=8,
                loc="upper right",
                frameon=False,
            )
            plt.tight_layout()
            plt.savefig(line_path, dpi=130, bbox_inches="tight")
            plt.close()

            temp_files.append(line_path)

            chart_section = KeepTogether(
                [
                    Paragraph("5. Summary Statistics Line Chart", section_title),
                    Spacer(1, 6),
                    RLImage(line_path, width=400, height=200),
                    Spacer(1, 6),
                    Paragraph(
                        f"<font size=9 color='gray'>Visualizes {instance.analysis_type.upper()} summary indicators "
                        f"for {instance.year}, showing minimum, maximum, average, and heterogeneity across all Union Councils.</font>",
                        normal,
                    ),
                    Spacer(1, 14),
                ]
            )
            story.append(chart_section)

    except Exception as e:
        print("Summary line chart generation failed:", e)

   

    try:
        if hist_values:
            analysis_type_lower = instance.analysis_type.lower()
            story.append(
                Paragraph(f"6. {instance.analysis_type.upper()} Summary", section_title)
            )
            story.append(Spacer(1, 8))

            avg_val = round(float(np.mean(hist_values)), 2)
            max_val = round(float(np.max(hist_values)), 2)
            min_val = round(float(np.min(hist_values)), 2)

           
            color_map = {
                "ndvi": ["#F4B400", "#0F9D58", "#DB4437"],  # Yellow, Green, Red
                "thermal": ["#E67E22", "#C0392B", "#7D6608"],  # Warm tones
                "aqi": ["#F4B400", "#58D68D", "#A93226"],  # AQI colors
            }
            colors_used = color_map.get(
                analysis_type_lower, ["#F4B400", "#0F9D58", "#DB4437"]
            )

            card_data = [
                [
                    Paragraph(
                        f"<b>{instance.analysis_type.upper()} Avg</b><br/><font size=14><b>{avg_val}</b></font>",
                        ParagraphStyle(
                            "card", alignment=TA_CENTER, textColor=colors.white
                        ),
                    ),
                    Paragraph(
                        f"<b>{instance.analysis_type.upper()} Max</b><br/><font size=14><b>{max_val}</b></font>",
                        ParagraphStyle(
                            "card", alignment=TA_CENTER, textColor=colors.white
                        ),
                    ),
                    Paragraph(
                        f"<b>{instance.analysis_type.upper()} Min</b><br/><font size=14><b>{min_val}</b></font>",
                        ParagraphStyle(
                            "card", alignment=TA_CENTER, textColor=colors.white
                        ),
                    ),
                ]
            ]

            card_table = Table(card_data, colWidths=[140, 140, 140], rowHeights=40)
            card_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(colors_used[0])),
                        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(colors_used[1])),
                        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor(colors_used[2])),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.white),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                        ("FONTSIZE", (0, 0), (-1, -1), 10),
                        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.white),
                    ]
                )
            )
            story.append(card_table)
            story.append(Spacer(1, 14))

           
            if analysis_type_lower == "ndvi":
                categories = {
                    "Bad": 0,
                    "Moderate": 0,
                    "Good": 0,
                    "Very Good": 0,
                    "Excellent": 0,
                }
                for val in hist_values:
                    if val < 0.2:
                        categories["Bad"] += 1
                    elif val < 0.4:
                        categories["Moderate"] += 1
                    elif val < 0.6:
                        categories["Good"] += 1
                    elif val < 0.8:
                        categories["Very Good"] += 1
                    else:
                        categories["Excellent"] += 1
                chart_title = f"NDVI Quality Distribution ({instance.year})"
                colors_used = ["#ffffcc", "#c2e699", "#78c679", "#31a354", "#006837"]
                ylabel = "Percentage (%)"

            elif analysis_type_lower == "thermal":
                categories = {
                    "<288K": 0,
                    "288–292.99K": 0,
                    "293–297.99K": 0,
                    "298–302.99K": 0,
                    "303–307.99K": 0,
                    "308–312.99K": 0,
                    "≥313K": 0,
                }
                for val in hist_values:
                    if val < 288:
                        categories["<288K"] += 1
                    elif val < 293:
                        categories["288–292.99K"] += 1
                    elif val < 298:
                        categories["293–297.99K"] += 1
                    elif val < 303:
                        categories["298–302.99K"] += 1
                    elif val < 308:
                        categories["303–307.99K"] += 1
                    elif val < 313:
                        categories["308–312.99K"] += 1
                    else:
                        categories["≥313K"] += 1
                chart_title = f"Thermal Range Distribution ({instance.year})"
                colors_used = ["#00008B", "#00FFFF", "#00FF00", "#FFFF00", "#FFA500", "#FF4500", "#FF0000"]
                ylabel = "Percentage (%)"

            else:  
                categories = {
                    "Good": 0,
                    "Moderate": 0,
                    "Unhealthy for Sensitive Groups": 0,
                    "Unhealthy": 0,
                    "Very Unhealthy": 0,
                    "Hazardous": 0,
                }
                for val in hist_values:
                    if val <= 50:
                        categories["Good"] += 1
                    elif val <= 100:
                        categories["Moderate"] += 1
                    elif val <= 150:
                        categories["Unhealthy for Sensitive Groups"] += 1
                    elif val <= 200:
                        categories["Unhealthy"] += 1
                    elif val <= 300:
                        categories["Very Unhealthy"] += 1
                    else:
                        categories["Hazardous"] += 1
                chart_title = f"AQI Category Distribution ({instance.year})"
                colors_used = ["#00E400", "#FFFF00", "#FF7E00", "#FF0000", "#8F3F97", "#7E0023"]
                ylabel = "Percentage (%)"

            total = sum(categories.values()) or 1
            percentages = {k: (v / total) * 100 for k, v in categories.items()}

            dist_path = os.path.join(
                reports_dir,
                _unique_filename(f"dist_{analysis_type_lower}_{instance.year}", "png"),
            )
            plt.figure(figsize=(7.2, 4.5))
            bars = plt.bar(
                list(percentages.keys()),
                list(percentages.values()),
                color=colors_used,
                edgecolor="black",
                alpha=0.9,
            )
            plt.xticks(rotation=20, ha="right")
            plt.gca().set_xticklabels(
            [label.get_text().replace(" for ", "\nfor ").replace(" ", "\n", 1) for label in plt.gca().get_xticklabels()]
            )

            plt.ylim(0, 110)  

            for i, bar in enumerate(bars):
                height = bar.get_height()
                plt.text(
                    bar.get_x() + bar.get_width() / 2,
                    height + 2,
                    f"{list(percentages.values())[i]:.1f}%",
                    ha="center",
                    fontsize=9,
                    fontweight="bold",
                    color="#333333",
                )

            plt.title(
                chart_title,
                fontsize=11,
                fontweight="bold",
                pad=8,
                color=chart_title_color,
            )

            plt.ylabel(ylabel, fontsize=9)
            plt.grid(axis="y", linestyle="--", alpha=0.4)
            # plt.tight_layout()
            plt.tight_layout(rect=[0, 0.12, 1, 1])
            plt.savefig(dist_path, dpi=130)
            plt.close()
            temp_files.append(dist_path)

            story.append(RLImage(dist_path, width=460, height=340))
            story.append(Spacer(1, 1.5))
           
            if analysis_type_lower == "ndvi":
                text = (
                    f"The NDVI analysis for {instance.year} highlights vegetation coverage across urban areas. "
                    f"Higher NDVI values represent greener zones (parks, trees), while lower values represent "
                    f"built-up or barren surfaces. Approximately {percentages['Excellent']:.1f}% of regions "
                    f"show excellent vegetation, while {percentages['Bad']:.1f}% show poor greenness. "
                    f"The most prominent category is <b>{max(percentages, key=percentages.get)}</b> "
                    f"with <b>{max(percentages.values()):.1f}%</b> of total regions."
                )

            elif analysis_type_lower == "thermal":
                text = (
                    f"The thermal analysis for {instance.year} identifies spatial heat variations. "
                    f"Higher temperatures (>305K) indicate urban heat islands, while cooler areas (<295K) "
                    f"often correspond to vegetated or water-rich zones. "
                    f"A total of {percentages['≥313K']:.1f}% regions recorded extreme heat levels. "
                    f"The dominant temperature range is <b>{max(percentages, key=percentages.get)}</b> "
                    f"covering <b>{max(percentages.values()):.1f}%</b> of areas."
                )

            else:  # AQI
                text = (
                    f"The AQI analysis for {instance.year} reveals overall air quality across the city. "
                    f"About {percentages['Good']:.1f}% of regions maintain healthy air, whereas "
                    f"{percentages['Hazardous']:.1f}% experience severe pollution levels. "
                    f"The most prominent air quality category is <b>{max(percentages, key=percentages.get)}</b>, "
                    f"representing <b>{max(percentages.values()):.1f}%</b> of all UCs."
                )

            story.append(Paragraph(text, normal))
            story.append(Spacer(1, 16))

    except Exception as e:
        print("Dynamic summary section failed:", e)

   
    disclaimer_text = (
    "<b>DISCLAIMER</b><br/>"
    "The following interpretation and recommendations are generated using "
    "AI-assisted analysis of environmental data. These insights are indicative "
    "and intended to support planning and decision-making. They should be "
    "validated using field data, local expertise, and applicable regulatory "
    "standards before implementation."
)

    disclaimer_table = Table(
        [[
            Paragraph(
                disclaimer_text,
                ParagraphStyle(
                    "DisclaimerText",
                    parent=normal,
                    fontSize=9,
                    leading=12,
                    textColor=colors.HexColor("#856404"),
                    alignment=TA_LEFT,
                )
            )
        ]],
        colWidths=[460],
    )

    disclaimer_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF3CD")),  # light yellow
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#FFEEBA")),
            ("LINEBEFORE", (0, 0), (0, -1), 4, colors.HexColor("#FFC107")),  # left accent
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])
    )

    story.append(disclaimer_table)
    story.append(Spacer(1, 14))
    story.append(Paragraph("7. Interpretation", section_title))
    if interpretation:
        story.append(Paragraph(interpretation, normal))
    else:
        story.append(Paragraph("Interpretation unavailable.", normal))
    story.append(Spacer(1, 10))

    story.append(Paragraph("8. Recommendations", section_title))
    if recommendation:
        for rec in recommendation.split("\n"):
            rec = rec.strip("-• ").strip()
            if rec:
                story.append(Paragraph(f"• {rec}", normal))
    else:
        story.append(Paragraph("No recommendations available.", normal))
    story.append(Spacer(1, 12))

   
    story.append(
        Paragraph(
            f"Generated by Urban Analytics System • {datetime.now().strftime('%d %b %Y %H:%M')}",
            footer_style,
        )
    )

   
    doc.build(story, canvasmaker=NumberedCanvas)

    for fpath in temp_files:
        try:
            os.remove(fpath)
        except Exception:
            pass


    return file_path


def create_before_after_report_pdf(entries, filename=None, created_by=None):
    """Generate PDF for before-after comparison report."""
    if not entries.exists():
        raise ValueError("No entries found for report")

    reports_dir = _ensure_reports_dir()
    instance = entries.first()
    project = getattr(instance, "project", None)
    project_name = (
        getattr(project, "name", None)
        or getattr(project, "project_name", None)
        or "N/A"
    )

    base = f"{instance.analysis_type}_{instance.before_year}_{instance.after_year}"
    filename = filename or _unique_filename(base, "pdf")
    file_path = os.path.join(reports_dir, filename)

    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )
    styles = getSampleStyleSheet()
    story = []
   
    analysis_type_lower = instance.analysis_type.lower()

    primary_color = "#2E86C1"  
    table_header_color = "#2E86C1"  
    chart_title_color = "#2E86C1"  
    header_dark = "#2E86C1"
    header_light = "#EAF2F8"

    if analysis_type_lower == "ndvi":
        primary_color = "#1B5E20"  
        table_header_color = "#2E7D32"
        chart_title_color = "#2E7D32"
        header_dark = "#1B5E20"
        header_light = "#DFF0D8"

    elif analysis_type_lower == "aqi":
        primary_color = "#1565C0"
        table_header_color = "#1565C0"
        chart_title_color = "#1565C0"
        header_dark = "#0D47A1"
        header_light = "#E3F2FD"

    elif analysis_type_lower == "thermal":
        primary_color = "#E65100"
        table_header_color = "#F57C00"
        chart_title_color = "#E65100"
        header_dark = "#E65100"
        header_light = "#FFF3E0"

    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        fontSize=20,
    )

    section = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        textColor=colors.HexColor(primary_color),
        fontSize=14,
        spaceAfter=6,
    )

    normal = ParagraphStyle(
        "Normal",
        parent=styles["Normal"],
        fontSize=11,
        leading=15,
    )
   
    from reportlab.platypus import Table, TableStyle

    dark_color = colors.HexColor(header_dark)
    light_color = colors.HexColor(header_light)

    title_table = Table(
        [
            [
                Paragraph(
                    "Urban Analytics – Before-After Comparison Report",
                    ParagraphStyle(
                        "BannerTitle",
                        parent=styles["Heading1"],
                        alignment=TA_CENTER,
                        fontSize=20,
                        leading=24,
                        textColor=colors.white,
                    ),
                )
            ]
        ],
        colWidths=[460],
    )

    title_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), dark_color),
                ("BOX", (0, 0), (-1, -1), 0, dark_color),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )

    bg_table = Table([[title_table]], colWidths=[480])
    bg_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), light_color),
                ("BOX", (0, 0), (-1, -1), 0, light_color),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )

    story.append(bg_table)
    story.append(Spacer(1, 14))

    story.append(Spacer(1, 10))
    story.append(Paragraph(f"<b>Project:</b> {project_name}", normal))
    story.append(
        Paragraph(f"<b>Analysis Type:</b> {instance.analysis_type.upper()}", normal)
    )
    story.append(
        Paragraph(
            f"<b>Compared Years:</b> {instance.before_year} → {instance.after_year}",
            normal,
        )
    )
    story.append(
        Paragraph(
            f"<b>Generated On:</b> {datetime.now().strftime('%d %b %Y %H:%M')}", normal
        )
    )
    story.append(Spacer(1, 12))
   
    story.append(Paragraph("1. Overview", section))
    story.append(
        Paragraph(
            f"This report presents a comparative overview of <b>{instance.analysis_type.upper()}</b> patterns "
            f"between <b>{instance.before_year}</b> and <b>{instance.after_year}</b>. "
            f"It analyzes spatial and statistical differences across urban units (UCs) to assess "
            "environmental progress or degradation over time. "
            "Higher values generally indicate improved environmental quality, whereas lower values "
            "reflect stress or declining conditions.",
            normal,
        )
    )
    story.append(Spacer(1, 12))

   
    story.append(Paragraph("1. UC-wise Comparison Summary", section))
    data = [["UC Name", "City", "Before Mean", "After Mean", "Change", "Status"]]
    before_vals, after_vals, diffs = [], [], []
    changes = {"increase": 0, "decrease": 0, "no_change": 0}

    for e in entries:
        comp = e.comparison or {}
        before = comp.get("before_mean")
        after = comp.get("after_mean")
        status = comp.get("status", "-")

        if before is not None and after is not None:
            before_vals.append(before)
            after_vals.append(after)
            diffs.append(after - before)

        if status in changes:
            changes[status] += 1

        change_val = (after - before) if before and after else None
        data.append(
            [
                e.uc_name or "-",
                e.city_name or "-",
                round(before, 3) if before else "-",
                round(after, 3) if after else "-",
                round(change_val, 3) if change_val else "-",
                status,
            ]
        )

    table = Table(data, colWidths=[120, 100, 70, 70, 60, 70])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(table_header_color)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.whitesmoke, colors.lightgrey],
                ),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 12))

    try:
        story.append(Paragraph("2.1 Overall Summary Statistics", section))

        total_ucs = len(entries)
        avg_before = np.mean(before_vals) if before_vals else 0
        avg_after = np.mean(after_vals) if after_vals else 0
        min_before = np.min(before_vals) if before_vals else 0
        min_after = np.min(after_vals) if after_vals else 0
        max_before = np.max(before_vals) if before_vals else 0
        max_after = np.max(after_vals) if after_vals else 0
        std_before = np.std(before_vals) if before_vals else 0
        std_after = np.std(after_vals) if after_vals else 0

        stats_data = [
            [
                "Metric",
                f"Before ({instance.before_year})",
                f"After ({instance.after_year})",
            ],
            ["Total Urban Units", total_ucs, total_ucs],
            ["Average Value", f"{avg_before:.4f}", f"{avg_after:.4f}"],
            ["Minimum Value", f"{min_before:.4f}", f"{min_after:.4f}"],
            ["Maximum Value", f"{max_before:.4f}", f"{max_after:.4f}"],
            ["Heterogeneity (Std. Dev.)", f"{std_before:.4f}", f"{std_after:.4f}"],
        ]

        stats_table = Table(stats_data, colWidths=[180, 100, 100])
        stats_table.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.HexColor(table_header_color),
                    ),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.whitesmoke, colors.lightgrey],
                    ),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                ]
            )
        )

        stats_table.hAlign = "CENTER"
        stats_table.spaceBefore = 12
        stats_table.spaceAfter = 18

        story.append(stats_table)
        story.append(Spacer(1, 12))

    except Exception as e:
        print("Overall Summary Statistics generation failed:", e)

    dist_chart_path = None
    try:
        if before_vals and after_vals:
            atype = instance.analysis_type.lower()

            # Clean numeric values
            def to_valid_floats(values):
                clean = []
                for v in values:
                    try:
                        fv = float(v)
                        if not np.isnan(fv):
                            clean.append(fv)
                    except Exception:
                        continue
                return clean or [0.0]

            before_clean = to_valid_floats(before_vals)
            after_clean = to_valid_floats(after_vals)

            avg_before = np.mean(before_clean)
            avg_after = np.mean(after_clean)
            max_before = np.max(before_clean)
            max_after = np.max(after_clean)
            min_before = np.min(before_clean)
            min_after = np.min(after_clean)

            def safe_round(v):
                try:
                    return round(float(np.nan_to_num(v)), 2)
                except Exception:
                    return 0.00

            # --- Cards ---
            if atype == "ndvi":
                cards = [
                    (
                        "NDVI Avg",
                        safe_round(avg_before),
                        safe_round(avg_after),
                        "#F1C40F",
                    ),
                    (
                        "NDVI Max",
                        safe_round(max_before),
                        safe_round(max_after),
                        "#27AE60",
                    ),
                    (
                        "NDVI Min",
                        safe_round(min_before),
                        safe_round(min_after),
                        "#E74C3C",
                    ),
                ]
                section_title = "NDVI Summary"
                desc = "Higher NDVI indicates healthier vegetation and better environmental conditions."
            elif atype == "thermal":
                cards = [
                    (
                        "Temp Avg",
                        safe_round(avg_before),
                        safe_round(avg_after),
                        "#3498DB",
                    ),
                    (
                        "Temp Max",
                        safe_round(max_before),
                        safe_round(max_after),
                        "#E67E22",
                    ),
                    (
                        "Temp Min",
                        safe_round(min_before),
                        safe_round(min_after),
                        "#E74C3C",
                    ),
                ]
                section_title = "Thermal Summary"
                desc = "Higher temperature values indicate urban heat concentration or low vegetation areas."
            elif atype == "aqi":
                cards = [
                    (
                        "AQI Avg",
                        safe_round(avg_before),
                        safe_round(avg_after),
                        "#F1C40F",
                    ),
                    (
                        "AQI Max",
                        safe_round(max_before),
                        safe_round(max_after),
                        "#E74C3C",
                    ),
                    (
                        "AQI Min",
                        safe_round(min_before),
                        safe_round(min_after),
                        "#27AE60",
                    ),
                ]
                section_title = "Air Quality Summary"
                desc = "Lower AQI values represent better air quality; higher values indicate pollution."
            else:
                cards = [
                    (
                        "Average",
                        safe_round(avg_before),
                        safe_round(avg_after),
                        "#5DADE2",
                    ),
                    (
                        "Maximum",
                        safe_round(max_before),
                        safe_round(max_after),
                        "#2E86C1",
                    ),
                    (
                        "Minimum",
                        safe_round(min_before),
                        safe_round(min_after),
                        "#AED6F1",
                    ),
                ]
                section_title = f"{atype.upper()} Summary"
                desc = "Statistical overview of before-after comparison metrics."

            card_cells = []
            for label, val_before, val_after, color in cards:
                arrow = (
                    "↑"
                    if val_after > val_before
                    else ("↓" if val_after < val_before else "→")
                )
                arrow_color = "#000000"
                card_cells.append(
                    Paragraph(
                        f"<b>{label}</b><br/>"
                        f"<font size=11>{val_before:.2f} → "
                        f"<font color='black'>{val_after:.2f}</font> "
                        f"<font color='{arrow_color}'>{arrow}</font></font>",
                        ParagraphStyle(
                            name="CardText",
                            alignment=TA_CENTER,
                            textColor=colors.white,
                            leading=14,
                        ),
                    )
                )

            card_table = Table(
                [card_cells], colWidths=[160] * len(cards), rowHeights=[55]
            )
            for i, (_, _, _, color) in enumerate(cards):
                card_table.setStyle(
                    TableStyle([("BACKGROUND", (i, 0), (i, 0), colors.HexColor(color))])
                )
            card_table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("BOX", (0, 0), (-1, -1), 0.25, colors.grey),
                        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.white),
                    ]
                )
            )

            story.append(Paragraph(section_title, section))
            story.append(Spacer(1, 6))
            story.append(card_table)
            story.append(Spacer(1, 6))
            story.append(Paragraph(f"<font size=9 color='gray'>{desc}</font>", normal))
            story.append(Spacer(1, 10))

            if atype == "ndvi":
                categories = ["Bad", "Moderate", "Good", "Very Good", "Excellent"]
                colors_palette_before = [
                    "#F1948A",
                    "#F8C471",
                    "#F9E79F",
                    "#ABEBC6",
                    "#7DCEA0",
                ]
                colors_palette_after = [
                    "#E74C3C",
                    "#F39C12",
                    "#F1C40F",
                    "#58D68D",
                    "#27AE60",
                ]

                def classify(v):
                    if v < 0.2:
                        return "Bad"
                    elif v < 0.4:
                        return "Moderate"
                    elif v < 0.6:
                        return "Good"
                    elif v < 0.8:
                        return "Very Good"
                    else:
                        return "Excellent"
            elif atype == "thermal":
                categories = [
                    "<288K",
                    "288–292.99K",
                    "293–297.99K",
                    "298–302.99K",
                    "303–307.99K",
                    "308–312.99K",
                    "≥313K",
                ]
                colors_palette_before = [
                    "#D6EAF8",
                    "#AED6F1",
                    "#A9CCE3",
                    "#F9E79F",
                    "#EDBB99",
                    "#F5B7B1",
                    "#F1948A",
                ]
                colors_palette_after = [
                    "#85C1E9",
                    "#5DADE2",
                    "#3498DB",
                    "#F4D03F",
                    "#E67E22",
                    "#FF7043",
                    "#E74C3C",
                ]

                def classify(v):
                    if v < 288:
                        return "<288K"
                    elif v < 293:
                        return "288–292.99K"
                    elif v < 298:
                        return "293–297.99K"
                    elif v < 303:
                        return "298–302.99K"
                    elif v < 308:
                        return "303–307.99K"
                    elif v < 313:
                        return "308–312.99K"
                    else:
                        return "≥313K"

            elif atype == "aqi":
                categories = [
                    "Good",
                    "Moderate",
                    "Unhealthy for Sensitive Groups",
                    "Unhealthy",
                    "Very Unhealthy",
                    "Hazardous",
                ]
                colors_palette_before = [
                    "#ABEBC6",
                    "#F9E79F",
                    "#FAD7A0",
                    "#F5CBA7",
                    "#F1948A",
                    "#C39BD3",
                ]
                colors_palette_after = [
                    "#00E400",
                    "#FFFF00",
                    "#FF7E00",
                    "#FF0000",
                    "#8F3F97",
                    "#7E0023",
                ]

                def classify(v):
                    if v <= 50:
                        return "Good"
                    elif v <= 100:
                        return "Moderate"
                    elif v <= 150:
                        return "Unhealthy for Sensitive Groups"
                    elif v <= 200:
                        return "Unhealthy"
                    elif v <= 300:
                        return "Very Unhealthy"
                    else:
                        return "Hazardous"

            else:
                categories = ["Low", "Medium", "High"]
                colors_palette_before = ["#D6EAF8", "#AED6F1", "#85C1E9"]
                colors_palette_after = ["#AED6F1", "#5DADE2", "#2E86C1"]

                def classify(v):
                    if v < 0.33:
                        return "Low"
                    elif v < 0.66:
                        return "Medium"
                    else:
                        return "High"

            before_counts = {c: 0 for c in categories}
            after_counts = {c: 0 for c in categories}
            for v in before_clean:
                before_counts[classify(v)] += 1
            for v in after_clean:
                after_counts[classify(v)] += 1

            total_before = sum(before_counts.values()) or 1
            total_after = sum(after_counts.values()) or 1
            before_perc = [before_counts[c] / total_before * 100 for c in categories]
            after_perc = [after_counts[c] / total_after * 100 for c in categories]

            x = np.arange(len(categories))
            bar_width = 0.35
            plt.figure(figsize=(7.5, 4.5))
            for i in range(len(categories)):
                plt.bar(
                    x[i] - bar_width / 2,
                    before_perc[i],
                    bar_width,
                    color=colors_palette_before[i],
                    edgecolor="black",
                    linewidth=0.3,
                    label=f"{instance.before_year}" if i == 0 else "",
                )
                plt.bar(
                    x[i] + bar_width / 2,
                    after_perc[i],
                    bar_width,
                    color=colors_palette_after[i],
                    edgecolor="black",
                    linewidth=0.3,
                    alpha=0.9,
                    label=f"{instance.after_year}" if i == 0 else "",
                )
                plt.text(
                    x[i] - bar_width / 2,
                    before_perc[i] + 1,
                    f"{before_perc[i]:.1f}%",
                    ha="center",
                    fontsize=8,
                )
                plt.text(
                    x[i] + bar_width / 2,
                    after_perc[i] + 1,
                    f"{after_perc[i]:.1f}%",
                    ha="center",
                    fontsize=8,
                )

            plt.xticks(x, categories)
            plt.gca().set_xticklabels(
            [c.replace("–", "\n–").replace(" for ", "\nfor ") for c in categories],
            rotation=20,
            ha="right"
)

            plt.ylabel("Percentage (%)")
            plt.title(
                f"{instance.analysis_type.upper()} Category Distribution ({instance.before_year} vs {instance.after_year})",
                fontsize=11,
                color=chart_title_color,
            )

            plt.grid(axis="y", linestyle="--", alpha=0.3)
            plt.tight_layout(rect=[0, 0.12, 1, 1])

            dist_chart_path = os.path.join(
                reports_dir, _unique_filename("before_after_distribution", "png")
            )
            plt.savefig(dist_chart_path, dpi=130)
            plt.close()

            chart_block = []
            chart_block.append(
                Paragraph("2. Before–After Category Distribution", section)
            )
            chart_block.append(Spacer(1, 6))
            chart_block.append(RLImage(dist_chart_path, width=460, height=320))
            chart_block.append(Spacer(1, 8))
            chart_block.append(
                Paragraph(
                    f"<font size=9 color='gray'>Comparison of {instance.analysis_type.upper()} category distribution "
                    f"between {instance.before_year} and {instance.after_year}, showing how regions shifted between performance levels.</font>",
                    normal,
                )
            )
            chart_block.append(Spacer(1, 12))
            story.append(KeepTogether(chart_block))

    except Exception as e:
        print("Distribution chart generation failed:", e)

   
    line_chart_path = None
    try:
        if before_vals and after_vals:
            stats = {
                "Min": [np.min(before_vals), np.min(after_vals)],
                "Max": [np.max(before_vals), np.max(after_vals)],
                "Avg": [np.mean(before_vals), np.mean(after_vals)],
                "Heterogeneity": [np.std(before_vals), np.std(after_vals)],
            }

            years = [int(instance.before_year), int(instance.after_year)]

            atype = instance.analysis_type.lower()

            if atype == "thermal":
                fig, ax1 = plt.subplots(figsize=(6.2, 4.5))
                ax2 = ax1.twinx()

                ax1.plot(
                    years,
                    stats["Min"],
                    marker="o",
                    color="#E74C3C",
                    linewidth=2.2,
                    label="Min",
                )
                ax1.plot(
                    years,
                    stats["Max"],
                    marker="o",
                    color="#2ECC71",
                    linewidth=2.2,
                    label="Max",
                )
                ax1.plot(
                    years,
                    stats["Avg"],
                    marker="o",
                    color="#3498DB",
                    linewidth=2.5,
                    label="Avg",
                )

                ax2.plot(
                    years,
                    stats["Heterogeneity"],
                    marker="o",
                    color="#F1C40F",
                    linewidth=2.2,
                    label="Heterogeneity",
                )

                for label, values, color in [
                    ("Min", stats["Min"], "#E74C3C"),
                    ("Max", stats["Max"], "#2ECC71"),
                    ("Avg", stats["Avg"], "#3498DB"),
                ]:
                    for i, y in enumerate(values):
                        ax1.text(
                            years[i],
                            y + 0.2,
                            f"{y:.2f}",
                            color=color,
                            ha="center",
                            fontsize=8,
                            fontweight="bold",
                        )

                for i, y in enumerate(stats["Heterogeneity"]):
                    ax2.text(
                        years[i],
                        y + 0.1,
                        f"{y:.2f}",
                        color="#F1C40F",
                        ha="center",
                        fontsize=8,
                        fontweight="bold",
                    )
                ax1.set_xlabel("Year", fontsize=9)
                ax1.set_ylabel(
                    "Temperature (Kelvin)", fontsize=9, color=chart_title_color
                )
                ax2.set_ylabel("Heterogeneity (Std. Dev.)", fontsize=9, color="#F1C40F")
                ax1.set_title(
                    f"{instance.analysis_type.upper()} Summary Comparison",
                    fontsize=11,
                    color=chart_title_color,
                    pad=10,
                )
                ax1.grid(alpha=0.3, linestyle="--", linewidth=0.7)
                ax1.tick_params(axis="y", labelcolor=chart_title_color)
                ax2.tick_params(axis="y", labelcolor="#F1C40F")

                lines1, labels1 = ax1.get_legend_handles_labels()
                lines2, labels2 = ax2.get_legend_handles_labels()
                ax1.legend(
                    lines1 + lines2,
                    labels1 + labels2,
                    fontsize=8,
                    loc="upper right",
                    frameon=False,
                )

                ax1.set_xticks(years)
                ax1.set_xticklabels([str(y) for y in years])

                all_temp = [*stats["Min"], *stats["Max"], *stats["Avg"]]
                y_min, y_max = min(all_temp), max(all_temp)
                buffer = (y_max - y_min) * 0.1
                ax1.set_ylim(y_min - buffer, y_max + buffer)
                ax2.set_ylim(0, max(stats["Heterogeneity"]) * 1.5)

                plt.tight_layout()

            else:
                plt.figure(figsize=(6.2, 4.5))
                plt.plot(
                    years,
                    stats["Min"],
                    marker="o",
                    color="#E74C3C",
                    linewidth=2.2,
                    label="Min",
                )
                plt.plot(
                    years,
                    stats["Max"],
                    marker="o",
                    color="#2ECC71",
                    linewidth=2.2,
                    label="Max",
                )
                plt.plot(
                    years,
                    stats["Avg"],
                    marker="o",
                    color="#3498DB",
                    linewidth=2.5,
                    label="Avg",
                )
                plt.plot(
                    years,
                    stats["Heterogeneity"],
                    marker="o",
                    color="#F1C40F",
                    linewidth=2.2,
                    label="Heterogeneity",
                )

                for label, color in zip(
                    stats.keys(), ["#E74C3C", "#2ECC71", "#3498DB", "#F1C40F"]
                ):
                    vals = stats[label]
                    for i, y in enumerate(vals):
                        plt.text(
                            years[i],
                            y + 0.01,
                            f"{y:.2f}",
                            color=color,
                            ha="center",
                            va="bottom",
                            fontsize=8,
                            fontweight="bold",
                        )

                plt.xticks(years, [str(y) for y in years])

                plt.title(
                    f"{instance.analysis_type.upper()} Category Distribution ({instance.before_year} vs {instance.after_year})",
                    fontsize=11,
                    color=chart_title_color,
                )

                plt.xlabel("Year", fontsize=9)
                plt.ylabel("Value", fontsize=9)
                plt.legend(fontsize=8, loc="upper right", frameon=False)
                plt.grid(alpha=0.3, linestyle="--", linewidth=0.7)
                plt.tight_layout()

                if atype == "ndvi":
                    plt.ylim(0, 1)
                elif atype == "aqi":
                    plt.ylim(0, 30)

            # Save line chart image
            line_chart_path = os.path.join(
                reports_dir, _unique_filename("before_after_linechart", "png")
            )
            plt.savefig(line_chart_path, dpi=130, bbox_inches="tight")
            plt.close()

            avg_before = np.mean(before_vals)
            avg_after = np.mean(after_vals)
            trend_percent = ((avg_after - avg_before) / avg_before) * 100 if avg_before else 0
            trend_direction = "up" if trend_percent > 0 else "down"

            arrow = "↑" if trend_percent > 0 else ("↓" if trend_percent < 0 else "→")

            story.append(
                KeepTogether([
                    Paragraph("3. Before–After Summary Chart", section),
                    Spacer(1, 6),
                    RLImage(line_chart_path, width=400, height=180),  
                ])
            )
            story.append(Spacer(1, 6))

            story.append(
                Paragraph(
                    f"<font size=9 color='gray'>Shows before–after trends in min, max, avg, and heterogeneity "
                    f"for {instance.analysis_type.upper()} between {instance.before_year} and {instance.after_year}.</font>",
                    normal,
                )
            )
            story.append(Spacer(1, 6))

            story.append(
                Paragraph(
                    "<font size=8 color='gray'><i>Note: All temperature values are expressed in Kelvin (K).</i></font>",
                    normal,
                )
            )
            story.append(Spacer(1, 6))

            story.append(
                Paragraph(
                    f"<b>{instance.analysis_type.upper()}</b> is trending {arrow} <b>{trend_direction}</b> by "
                    f"<b>{abs(trend_percent):.1f}%</b> between {instance.before_year} and {instance.after_year}.",
                    ParagraphStyle(
                        "Trend",
                        parent=normal,
                        textColor=colors.HexColor(chart_title_color),
                    ),
                )
            )
            story.append(Spacer(1, 10))



    except Exception as e:
        print("Line chart generation failed:", e)

    try:

        report_text = f"""
        Analysis Type: {instance.analysis_type}
        Before Year: {instance.before_year}
        After Year: {instance.after_year}
        Avg Before: {np.mean(before_vals) if before_vals else 0}
        Avg After: {np.mean(after_vals) if after_vals else 0}
        Change (%): {((np.mean(after_vals) - np.mean(before_vals)) / (np.mean(before_vals) or 1)) * 100 if before_vals and after_vals else 0}
        """

        summary, interpretation, recommendation = run_langgraph_summarizer(
            report_text=report_text,
            report_type="before_after"
        )
       
        disclaimer_text = (
            "<b>DISCLAIMER</b><br/>"
            "The following interpretation and recommendations are generated using "
            "AI-assisted analysis of environmental data. These insights are indicative "
            "and intended to support planning and decision-making. They should be "
            "validated using field data, local expertise, and applicable regulatory "
            "standards before implementation."
        )

        disclaimer_table = Table(
            [[
                Paragraph(
                    disclaimer_text,
                    ParagraphStyle(
                        "DisclaimerText",
                        parent=normal,
                        fontSize=9,
                        leading=12,
                        textColor=colors.HexColor("#856404"),
                        alignment=TA_LEFT,
                    )
                )
            ]],
            colWidths=[460],
        )

        disclaimer_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF3CD")),  # light yellow
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#FFEEBA")),
                ("LINEBEFORE", (0, 0), (0, -1), 4, colors.HexColor("#FFC107")),  # left accent
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ])
        )

        story.append(disclaimer_table)
        story.append(Spacer(1, 14))

        story.append(Paragraph("4. Interpretation", section))
        if interpretation:
            story.append(Paragraph(interpretation, normal))
        else:
            story.append(Paragraph("Interpretation unavailable.", normal))
        story.append(Spacer(1, 10))

        story.append(Paragraph("5. Recommendations", section))
        if recommendation:
            for rec in recommendation.split("\n"):
                rec = rec.strip("-• ").strip()
                if rec:
                    story.append(Paragraph(f"• {rec}", normal))
        else:
            story.append(Paragraph("No recommendations available.", normal))
        story.append(Spacer(1, 12))

    except Exception as e:
        print("Interpretation & Recommendations failed:", e)

        story.append(Paragraph("5. Recommendations", section))

        if atype == "ndvi":
            rec_text = (
                "Urban planners should focus on areas with decreasing NDVI for reforestation, green corridors, "
                "and urban forest initiatives to restore vegetation health and reduce surface heating."
            )
        elif atype == "thermal":
            rec_text = (
                "Introduce reflective materials, increase vegetation and permeable surfaces, "
                "and promote vertical greening to counter rising heat and enhance thermal comfort."
            )
        elif atype == "aqi":
            rec_text = (
                "Implement stricter emission controls, promote cleaner transport modes, and increase green buffer zones "
                "to maintain and improve air quality across critical urban areas."
            )
        else:
            rec_text = (
                "Maintain regular environmental monitoring and prioritize improvement in low-performing UCs "
                "based on observed changes."
            )

        story.append(Paragraph(rec_text, normal))
        story.append(Spacer(1, 12))

    except Exception as e:
        print("Interpretation & Recommendations block failed:", e)

   
    if before_vals and after_vals:
        avg_diff = np.mean(after_vals) - np.mean(before_vals)
        overall_change = "increase" if avg_diff > 0 else "decrease"
        story.append(
            Paragraph(
                f"On average, there was a <b>{overall_change}</b> of <b>{abs(avg_diff):.3f}</b> in "
                f"{instance.analysis_type.upper()} values between {instance.before_year} and {instance.after_year}.",
                normal,
            )
        )
        story.append(Spacer(1, 8))

    story.append(
        Paragraph(
            "This report summarizes the changes in environmental indicators across UCs, "
            "helping urban planners identify improvement or deterioration trends between two time periods.",
            normal,
        )
    )
    story.append(Spacer(1, 12))

    story.append(
        Paragraph(
            f"Generated by Urban Analytics System • {datetime.now().strftime('%d %b %Y %H:%M')}",
            ParagraphStyle(
                "Footer", alignment=TA_RIGHT, fontSize=9, textColor=colors.grey
            ),
        )
    )

    doc.build(story, canvasmaker=NumberedCanvas)

    try:
        if dist_chart_path and os.path.exists(dist_chart_path):
            os.remove(dist_chart_path)
        if line_chart_path and os.path.exists(line_chart_path):
            os.remove(line_chart_path)
    except Exception:
        pass

    return file_path