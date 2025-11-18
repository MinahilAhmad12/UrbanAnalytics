import google.generativeai as genai
from supabase import create_client
from django.conf import settings
import re

# ----------------------------
# Configure Gemini + Supabase
# ----------------------------
genai.configure(api_key=settings.GOOGLE_API_KEY)
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


# ----------------------------
# Helper: Generate Embedding (Gemini)
# ----------------------------
def get_embedding(text: str):
    """Generate a 768-dimension embedding using Gemini."""
    result = genai.embed_content(model="models/embedding-001", content=text)
    return result["embedding"]

def parse_query_metadata(query: str):
    """
    Detect analysis type (NDVI, Thermal, AQI), year, and UC name.
    Cleans 'tell me', 'give me', 'about', etc. before extracting UC name.
    """
    query_original = query.strip()
    query_lower = query_original.lower()

    # Detect analysis type
    if "thermal" in query_lower:
        analysis_type = "thermal"
    elif "ndvi" in query_lower:
        analysis_type = "ndvi"
    elif "aqi" in query_lower or "air" in query_lower:
        analysis_type = "aqi"
    else:
        analysis_type = None

    # Detect year
    year_match = re.search(r"\b(20[0-3][0-9])\b", query_lower)
    year = int(year_match.group(1)) if year_match else None

    # Clean filler words
    cleaned_query = re.sub(
        r"\b(tell|give|me|about|data|stats|report|condition|analysis|of|ndvi|thermal|aqi|in\s*\d{4}|in|for|the|year|value|mean|average|please|show|what|is|was)\b",
        "",
        query_lower,
        flags=re.IGNORECASE,
    ).strip()

    # Extract UC name (words before/after 'UC' or last few words)
    uc_match = re.search(r"([A-Za-z\s\-]+?)\s+UC\b", cleaned_query, re.IGNORECASE)
    if uc_match:
        uc_name = uc_match.group(1).strip().title()
    else:
        words = cleaned_query.split()
        uc_name = " ".join(words[-3:]).title() if len(words) >= 2 else (words[-1].title() if words else None)

    if uc_name:
        uc_name = re.sub(r"\s+", " ", uc_name).strip()

    print(f" Parsed -> analysis_type={analysis_type}, year={year}, uc_name={uc_name}")
    return analysis_type, year, uc_name



# ----------------------------
# Helper: Fetch relevant chunks (with safe fallback)
# ----------------------------
def fetch_relevant_chunks(query_embedding, top_k=5, metadata_filter=None):
    """
    Perform vector similarity search via Supabase RPC (match_documents),
    with UC name fallback if the query includes a UC name.
    Ensures UC-level retrieval works even when vector search finds unrelated data.
    """
    params = {
        "query_embedding": query_embedding,
        "match_count": top_k,
    }

    # Exclude uc_name from vector filter (we handle that manually)
    uc_name = None
    if metadata_filter:
        uc_name = metadata_filter.get("uc_name")
        safe_filter = {k: v for k, v in metadata_filter.items() if k != "uc_name"}
        if safe_filter:
            params["filter"] = safe_filter

    # --- STEP 1: Try vector similarity search ---
    response = supabase.rpc("match_documents", params).execute()
    data = response.data or []

    print(f" Vector search returned {len(data)} matches")

    # --- STEP 2: Always run UC fallback if UC name provided ---
    if uc_name:
        year = metadata_filter.get("year") if metadata_filter else None
        analysis_type = metadata_filter.get("analysis_type") if metadata_filter else None

        uc_name = re.sub(r"^(tell|give|me|about)\s+", "", uc_name, flags=re.IGNORECASE).strip()
        print(f"\n⚡ Running UC fallback for '{uc_name}' (year={year}, analysis={analysis_type})...")

        normalized_name = uc_name.strip().lower()
        search_variants = [
            normalized_name,
            normalized_name.title(),
            normalized_name.replace(" uc", "").strip(),
            normalized_name.replace(" ", "%"),
            normalized_name.split()[0] if " " in normalized_name else normalized_name,
        ]

        all_matches = []
        for variant in search_variants:
            print(f"🔍 Trying variant: {variant}")
            query = (
                supabase.table("documents")
                .select("content, metadata")
                .ilike("metadata->>uc_name", f"%{variant}%")
            )
            if analysis_type:
                query = query.eq("metadata->>analysis_type", analysis_type)
            if year:
                # Ensure year comparison works for int or str
                query = query.eq("metadata->>year", str(year))

            result = query.execute()
            if result.data:
                print(f"   ✅ Found {len(result.data)} rows for '{variant}'")
                all_matches.extend(result.data)

        # Deduplicate UC-level results
        unique_matches = {}
        for d in all_matches:
            uc_meta = d["metadata"].get("uc_name", "").strip().lower()
            if uc_meta and normalized_name in uc_meta:
                unique_matches[uc_meta] = d

        if unique_matches:
            print(f"🔎 UC fallback found {len(unique_matches)} unique matches for '{uc_name}'")
            data = list(unique_matches.values())  # override with UC results
        else:
            print(f"⚠️ UC fallback found no matches for '{uc_name}'")

    # --- STEP 3: Return final matched text chunks ---
    return [item["content"] for item in data]


# ----------------------------
#  Main Chatbot RAG Function
# ----------------------------
def run_chatbot_query(query: str):
    """Runs RAG chatbot query using Supabase embeddings and Gemini."""
    if not query.strip():
        raise ValueError("Query cannot be empty")

    # Step 1: Parse query
    analysis_type, year, uc_name = parse_query_metadata(query)

    # Step 2: Generate embedding
    query_embedding = get_embedding(query)

    # Step 3: Build metadata filter
    metadata_filter = {}
    if analysis_type:
        metadata_filter["analysis_type"] = analysis_type
    if year:
        metadata_filter["year"] = year
    if uc_name:
        metadata_filter["uc_name"] = uc_name

    # Step 4: Fetch matching chunks
    relevant_chunks = fetch_relevant_chunks(
        query_embedding=query_embedding,
        top_k=5,
        metadata_filter=metadata_filter if metadata_filter else None
    )

    # Step 5: Combine retrieved content
    context_text = "\n\n".join(relevant_chunks) if relevant_chunks else "No relevant report data found."

    prompt = f"""
You are an **Urban Analytics Assistant**, specialized in interpreting environmental reports (NDVI, AQI, Thermal).
Your knowledge is based on indexed Urban Analytics system reports stored in Supabase.

CONTEXT (from Supabase):
{context_text}

COLOR LEGEND (NDVI Meaning Guide):
#E7E0E0 → Barren / No Vegetation (< 0.1)
#FFFF00 → Low Vegetation (0.1–0.25)
#90EE90 → Moderate Vegetation (0.25–0.4)
#008000 → Healthy Vegetation (0.4–0.6)
#006400 → Very Dense Vegetation (> 0.6)

USER QUESTION:
{query}

RESPONSE RULES:
1. Use the context to interpret environmental conditions.
2. If you see a UC entry like "Mean Value" and "Color", interpret NDVI health based on the color and numeric range.
3. If the UC has NDVI < 0.25 or color #FFFF00, say it has **low vegetation cover**.
4. If NDVI > 0.4, describe it as **healthy vegetation**.
5. Always mention the UC name, NDVI value, and color interpretation clearly.
6. If no relevant context is found, respond with:
   "I don’t have sufficient report data to answer that."
7. Write in concise, analytical sentences.
"""


    # Step 7: Generate answer
    model = genai.GenerativeModel("models/gemini-2.5-pro")
    response = model.generate_content(prompt)

    return response.text.strip() if response and hasattr(response, "text") else "No answer generated."
