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
# Example line: "Paji Lahore 0.2653 #FFFF00"
# -------------------------------
UC_ROW_PATTERN = re.compile(
    r"([A-Za-zÀ-ÖØ-öø-ÿ\s\'\-]+)\s+Lahore\s+([\d\.]+)\s+(#[A-F0-9]{6})", re.IGNORECASE
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
    """Extract text, tables, and UC-level rows."""
    full_text = []
    uc_rows = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            full_text.append(f"\n--- Page {i} Text ---\n{text}")

            # Extract UC rows from text
            matches = UC_ROW_PATTERN.findall(text)
            for match in matches:
                uc_name, mean_val, color = match
                uc_rows.append({
                    "uc_name": uc_name.strip(),
                    "city": "Lahore",
                    "value": float(mean_val),
                    "color": color
                })

            # Extract tables
            tables = page.extract_tables()
            for t_index, table in enumerate(tables, start=1):
                full_text.append(f"\n--- Page {i} Table {t_index} ---\n")
                for row in table:
                    row_text = " | ".join([str(cell) if cell else "" for cell in row])
                    full_text.append(row_text)

    return "\n".join(full_text), uc_rows


# -------------------------------
# Main function
# -------------------------------
def upload_report_to_supabase(report_id):
    """
    Fetches a Report by ID, downloads its PDF, extracts UC rows + text,
    generates embeddings, and uploads them to Supabase.
    """
    genai.configure(api_key=settings.GOOGLE_API_KEY)
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

    report = Report.objects.get(id=report_id)
    pdf_url = report.file.url

    # Fix broken or encoded URLs
    from urllib.parse import unquote
    pdf_url = unquote(pdf_url)
    if pdf_url.startswith("/media/https"):
        pdf_url = pdf_url.replace("/media/", "").replace("https:/", "https://")

    print(f" Downloading report from {pdf_url}")
    response = requests.get(pdf_url)
    if response.status_code != 200:
        raise Exception(f"Failed to download PDF (status {response.status_code})")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(response.content)
        pdf_path = tmp_file.name

    combined_text, uc_rows = extract_pdf_text_and_tables(pdf_path)
    os.remove(pdf_path)

    if not combined_text.strip():
        raise ValueError("No readable text or tables found in the PDF.")

    metadata = {
        "project": report.project.project_name if report.project else None,
        "analysis_type": report.analysis_type.lower(),
        "report_type": report.report_type,
        "area_type": report.area_type,
        "year": report.year,
    }

    model = "models/embedding-001"

    #  Upload UC-level rows (fine-grained)
    if uc_rows:
        print(f"📊 Found {len(uc_rows)} UC rows — uploading individually.")
        for i, uc in enumerate(uc_rows, start=1):
            uc_text = f"UC: {uc['uc_name']}, City: {uc['city']}, Mean Value: {uc['value']}, Color: {uc['color']}"
            result = genai.embed_content(model=model, content=uc_text)
            embedding = result["embedding"]

            record = {
                "content": uc_text,
                "metadata": {
                    **metadata,
                    "uc_name": uc["uc_name"],
                    "mean_value": uc["value"],
                    "color": uc["color"]
                },
                "embedding": embedding,
            }
            supabase.table("documents").insert(record).execute()
            print(f" Uploaded UC {i}/{len(uc_rows)}: {uc['uc_name']}")
    else:
        print(" No UC-level rows found.")

    #  Upload full report (for summaries)
    chunks = split_text(combined_text)
    print(f" Uploading {len(chunks)} general text chunks.")
    for i, chunk in enumerate(chunks, start=1):
        result = genai.embed_content(model=model, content=chunk)
        embedding = result["embedding"]
        supabase.table("documents").insert({
            "content": chunk,
            "metadata": metadata,
            "embedding": embedding,
        }).execute()
        print(f" Uploaded report chunk {i}/{len(chunks)}")

    print(" Report fully indexed (UC-level + general text).")
