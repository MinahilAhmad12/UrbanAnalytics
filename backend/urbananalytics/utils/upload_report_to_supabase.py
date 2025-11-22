import os
import re
import tempfile
import requests
import pdfplumber
import google.generativeai as genai
from supabase import create_client
from django.conf import settings
from urbananalytics.models import Report

# -------------------------------
# Helper: UC row detector
# -------------------------------
UC_ROW_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9\s'\-\(\)]+?)\s+([A-Za-z]+)\s+([0-9]+\.[0-9]+)\s+(#[A-Fa-f0-9]{6})\s*$",
    re.IGNORECASE | re.MULTILINE,
)


# -------------------------------
# Helper: split text into chunks
# -------------------------------
def split_text(text, chunk_size=800, overlap=100):
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end].strip())
        start += chunk_size - overlap
    return chunks

# -------------------------------
# Helper: extract text + tables + UC rows
# -------------------------------
def extract_pdf_text_and_tables(pdf_path):
    full_text = []
    uc_rows = []
    seen = set()  # Track unique UC rows

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            full_text.append(f"\n--- Page {i} Text ---\n{text}")

            # Extract UC rows from text
                        # Extract UC rows from text
                        # Extract UC rows from text
            for line in text.split("\n"):
                m = UC_ROW_PATTERN.match(line.strip())
                if m:
                    uc_name, city, mean_val, color = m.groups()

                    # normalize fields
                    uc_name_norm = uc_name.strip().lower()
                    city_norm = city.strip().lower()
                    value_norm = float(mean_val)
                    color_norm = color.upper()

                    key = (uc_name_norm, city_norm, value_norm, color_norm)

                    if key in seen:
                        continue
                    seen.add(key)

                    uc_rows.append({
                        "uc_name": uc_name.strip(),
                        "city": city.strip(),
                        "value": value_norm,
                        "color": color_norm,
                    })


            # Extract UC rows from tables
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    row = [str(c).strip() if c else "" for c in row]

                    if len(row) >= 4:
                        name, city, val, color = row[:4]
                        
                        if not re.match(r"^[0-9]+\.[0-9]+$", val):
                            continue
                        if not re.match(r"^#[A-Fa-f0-9]{6}$", color):
                            continue
                        if name.lower().startswith("uc name"):
                            continue

                                    # normalize fields
                        name_norm = name.strip().lower()
                        city_norm = city.strip().lower()
                        val_norm = float(val)
                        color_norm = color.upper()

                        key = (name_norm, city_norm, val_norm, color_norm)

                        if key in seen:
                            continue
                        seen.add(key)
                        
                        uc_rows.append({
                            "uc_name": name.strip(),
                            "city": city,
                            "value": float(val),
                            "color": color.upper(),
                        })

    return "\n".join(full_text), uc_rows


# -------------------------------
# Main upload function
# -------------------------------
def upload_report_to_supabase(report_id):
    """Download, extract, embed, and upload report data to Supabase."""
    genai.configure(api_key=settings.GOOGLE_API_KEY)
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

    report = Report.objects.get(id=report_id)
    pdf_url = report.file.url
    report_type_raw = (report.report_type or "").lower()

    # --------------------------------------------------
    # STRICT RULE: Only yearly reports can store embeddings
    # --------------------------------------------------

    # Skip if no year (means range or comparison)
    if not report.year:
        print(" Skipping embeddings:(range/comparison report).")
        return

    if any(keyword in report_type_raw for keyword in [
        "before", "after", "comparison", "compare", "range", "2yr", "two year", "start", "end"
    ]):
     return 
    year = report.year
    raw_type = report.analysis_type.lower() if report.analysis_type else ""

    # Normalize analysis type
    if "aqi" in raw_type or "air" in raw_type:
        normalized_type = "aqi"
    elif "thermal" in raw_type or "temperature" in raw_type:
        normalized_type = "thermal"
    else:
        normalized_type = "ndvi"

    # --------------------------------------------------
    # Step 0: Skip upload if embeddings already exist
    # --------------------------------------------------
    check = (
        supabase.table("documents")
        .select("id")
        .eq("metadata->>analysis_type", normalized_type)
        .eq("metadata->>year", str(year))
        .limit(1)
        .execute()
    )

    if check.data:
        print(f"Embeddings already exist for {normalized_type} {year} — skipping upload.")
        return

    print(f"Uploading new embeddings for {normalized_type} {year} ...")

    # --------------------------------------------------
    # Step 1: Download the PDF
    # --------------------------------------------------
    from urllib.parse import unquote
    pdf_url = unquote(pdf_url)

    if pdf_url.startswith("/media/https"):
        pdf_url = pdf_url.replace("/media/", "").replace("https:/", "https://")

    print(f"Downloading report from {pdf_url}")
    response = requests.get(pdf_url)

    if response.status_code != 200:
        raise Exception(f"Failed to download PDF (status {response.status_code})")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(response.content)
        pdf_path = tmp_file.name

    combined_text, uc_rows = extract_pdf_text_and_tables(pdf_path)

    if not combined_text.strip():
        raise ValueError("No readable text or tables found in the PDF.")

    # --------------------------------------------------
    # Step 2: Build metadata
    # --------------------------------------------------
    metadata = {
        "analysis_type": normalized_type,
        "report_type": report.report_type,
        "area_type": report.area_type,
        "year": year,
    }

    model = "models/embedding-001"

    # --------------------------------------------------
    # Step 3: Extract and upload Overall Summary
    # --------------------------------------------------
    summary_match = re.search(
        r"(Overall Summary Statistics|Average Value)[\s\S]*?Average Value\s+([0-9.]+)",
        combined_text,
        re.IGNORECASE,
    )

    if summary_match:
        avg_val = float(summary_match.group(2))
        summary_text = (
            f"Overall Summary for {year} ({normalized_type.upper()}):\n"
            f"Average Value: {avg_val}"
        )

        result = genai.embed_content(model=model, content=summary_text)
        embedding = result["embedding"]

        supabase.table("documents").insert({
            "content": summary_text,
            "metadata": {
                **metadata,
                "area_type": "city",
                "report_type": "summary",
                "mean_value": avg_val,
            },
            "embedding": embedding,
        }).execute()

        print(f"Uploaded summary stats for {year} (avg={avg_val})")

    # --------------------------------------------------
    # Step 4: Upload UC-level rows
    # --------------------------------------------------
    if uc_rows:
        print(f"Found {len(uc_rows)} UC rows — uploading individually.")
        for i, uc in enumerate(uc_rows, start=1):
            uc_text = (
                f"UC: {uc['uc_name']}, City: {uc['city']}, "
                f"Mean Value: {uc['value']}, Color: {uc['color']}"
            )

            result = genai.embed_content(model=model, content=uc_text)
            embedding = result["embedding"]

            supabase.table("documents").insert({
                "content": uc_text,
                "metadata": {
                    **metadata,
                    "uc_name": uc["uc_name"],
                    "mean_value": uc["value"],
                    "color": uc["color"],
                },
                "embedding": embedding,
            }).execute()

            print(f" Uploaded UC {i}/{len(uc_rows)}: {uc['uc_name']}")

    # --------------------------------------------------
    # Step 5: Upload full report text chunks
    # --------------------------------------------------
    chunks = split_text(combined_text)
    print(f"Uploading {len(chunks)} general text chunks.")

    for i, chunk in enumerate(chunks, start=1):
        result = genai.embed_content(model=model, content=chunk)
        embedding = result["embedding"]

        supabase.table("documents").insert({
            "content": chunk,
            "metadata": metadata,
            "embedding": embedding,
        }).execute()

        print(f" Uploaded report chunk {i}/{len(chunks)}")
    os.remove(pdf_path)

    print("Report fully indexed (UC-level + legend + general text + summary).")