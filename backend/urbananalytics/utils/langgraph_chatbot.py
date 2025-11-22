import google.generativeai as genai
from supabase import create_client
from django.conf import settings
import re

# ----------------------------
# Hardcoded Color Legends 
# ----------------------------

COLOR_LEGENDS = {
    "ndvi": {
        "#E7E0E0": "Barren / No Vegetation (< 0.1)",
        "#FFFF00": "Low Vegetation (0.1 – 0.25)",
        "#90EE90": "Moderate Vegetation (0.25 – 0.4)",
        "#008000": "Healthy Vegetation (0.4 – 0.6)",
        "#006400": "Very Dense Vegetation (> 0.6)",
    },

    "thermal": {
        "#87CEEB": "Cool (< 295K)",
        "#32CD32": "Mild (295–300K)",
        "#FF6347": "Warm (300–305K)",
        "#FFA500": "Hot (305–310K)",
        "#800080": "Very Hot (> 310K)",
    },

    "aqi": {
        "#FFC0CB": "Good Air Quality (< 5)",
        "#FF7F50": "Moderate Pollution (5–10)",
        "#FFBF00": "Unhealthy (10–20)",
        "#FFFFE0": "Very Unhealthy (20–30)",
        "#8A2BE2": "Hazardous (> 30)",
    },
}


def detect_trend_with_ai(query: str):
    """
    Uses Gemini to determine if the user is asking for multi-year trends.
    Returns True or False.
    """
    prompt = f"""
    Determine whether the user query is asking for a MULTI-YEAR trend,
    comparison over years, change over time, year-to-year variation,
    or progression.

    Respond ONLY with JSON:
    {{"trend": true}} or {{"trend": false}}

    USER QUERY:
    {query}
    """

    model = genai.GenerativeModel("models/gemini-2.5-pro")
    resp = model.generate_content(prompt)

    text = resp.text.strip()
    text = text.replace("json", "").replace("", "")

    import json
    try:
        data = json.loads(text)
        return bool(data.get("trend", False))
    except:
        return False


def infer_analysis_type(query: str):
    """
    Automatically detect analysis type from user's language.
    Returns: "ndvi" | "thermal" | "aqi" | None
    """
    q = query.lower()

    # THERMAL detection
    if any(w in q for w in [
        "thermal", "temperature", "temp", "heat", "hot", "warm", "cool",
        "surface temp", "hotspots", "hot spots", "urban heat islands",
        "heat islands", "heatislands", "lst", "land surface temperature",
        "surface heating", "heating pattern", "warm areas", "hot region",
        "heatwave", "heat wave"
    ]):
        return "thermal"

    # NDVI detection
    if any(w in q for w in [
        "ndvi", "vegetation", "green", "greenery", "greenness", "plants",
        "plant cover", "tree cover", "trees", "canopy", "land cover",
        "green cover", "vegetation health", "vegetation index",
        "green index", "ecosystem", "eco condition"
    ]):
        return "ndvi"

    # AQI detection
    if any(w in q for w in [
        "aqi", "air quality", "pollution", "air pollution", "smog",
        "dust", "pm2", "pm 2.5", "pm10", "pm 10", "air condition",
        "air health", "weather", "haze", "environment quality",
        "breathing quality", "ambient air", "pollutants"
    ]):
        return "aqi"

    return None


def detect_analysis_type_with_ai(query: str):
    """
    Uses Gemini to determine what analysis type(s) the user is asking for.
    Returns a list like ["ndvi"], ["aqi"], ["thermal"], or combinations.
    """
    prompt = f"""
    From the user query, decide which environmental analysis types are being requested.

    Allowed types:
    - "ndvi" (vegetation, greenery, plants)
    - "aqi" (air quality, pollution, pm2.5, pm10)
    - "thermal" (temperature, heat, hotspots, LST)

    Return ONLY JSON:
    {{"types": ["ndvi", "thermal"]}}

    USER QUERY:
    {query}
    """

    model = genai.GenerativeModel("models/gemini-2.5-pro")
    resp = model.generate_content(prompt)

    raw = resp.text.strip().replace("json", "").replace("", "").strip()

    import json
    try:
        data = json.loads(raw)
        types = data.get("types", [])
        return [t.lower() for t in types if t.lower() in ["ndvi", "aqi", "thermal"]]
    except:
        return []

    return None


def normalize_uc_name(name: str):
    """Normalize UC names for consistent matching."""
    if not name:
        return None
    name = name.lower().strip()
    name = re.sub(r"[-_]+", " ", name)
    name = re.sub(r"\b(qilla|killa)\b", "qila", name)
    name = re.sub(r"\b(sittara|sitara)\b", "sittara", name)
    name = re.sub(r"\b(johartown|johar town)\b", "johar town", name)
    name = re.sub(r"\s+", " ", name)
    return name


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


def extract_uc_names_with_ai(query: str):
    """
    Bulletproof UC extractor using Gemini.
    Forces JSON output, then safely parses it.
    Returns a clean Python list of UC names.
    """
    prompt = f"""
    Extract ONLY the Union Council (UC) names from the following question.

    OUTPUT RULES:
    - Return ONLY a JSON list (array) of strings.
    - NO explanation.
    - NO extra words.
    - NO python list, ONLY pure JSON.
    - Example: ["Johar Town", "Paji", "Minhala"]

    USER QUERY:
    {query}

    NOW RETURN ONLY THE JSON LIST:
    """

    model = genai.GenerativeModel("models/gemini-2.5-pro")
    response = model.generate_content(prompt)

    raw = response.text.strip()

    # Remove code fences if Gemini returns json ... 
    raw = raw.replace("json", "").replace("", "").strip()

    # Try to parse JSON strictly
    import json

    try:
        data = json.loads(raw)
        if isinstance(data, list):
            # Normalize names
            clean = []
            for u in data:
                if isinstance(u, str) and len(u.strip()) > 0:
                    clean.append(u.title().strip())
            return clean
    except:
        return []

    return []


def parse_query_metadata(query: str):
    """
    Uses Gemini to extract analysis types + years + UC names
    in clean structured JSON format.
    """

    prompt = f"""
    Extract the environmental analysis requests from the user query.

    Analysis types allowed: "ndvi", "aqi", "thermal".

    RETURN RULES:
    - Return ONLY JSON.
    - Do NOT include explanations.
    - Structure:
      {{
         "tasks": [
            {{"analysis_type": "...", "years": [ ... ] }},
            {{"analysis_type": "...", "years": [ ... ] }}
         ],
         "uc_names": [ ... ]
      }}

    DETECTION RULES:
    - If a year appears near an analysis type, assign it there.
    - If a year is mentioned globally (e.g., "of 2021"), apply it to ALL analysis types.
    - If no year is mentioned for a type, return years = null.]
    - If UC names exist, extract them.
    - UC names are geographic places (not analysis types, not years).

    USER QUERY:
    {query}

    NOW RETURN ONLY THE JSON:
    """

    model = genai.GenerativeModel("models/gemini-2.5-pro")
    response = model.generate_content(prompt)

    raw = response.text.strip()
    raw = raw.replace("json", "").replace("", "").strip()

    import json

    try:
        data = json.loads(raw)
        return data.get("tasks", []), data.get("uc_names", [])
    except:
        return [], []


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

    # Exclude uc_name from vector filter
    uc_name = None
    if metadata_filter:
        uc_name = metadata_filter.get("uc_name")

    safe_filter = (
        {k: v for k, v in metadata_filter.items() if k != "uc_name"}
        if metadata_filter
        else {}
    )
    if safe_filter:
        params["filter"] = safe_filter

    # --- STEP 1: Vector similarity search ---
    response = supabase.rpc("match_documents", params).execute()
    data = response.data or []
    print(f" Vector search returned {len(data)} matches")

    # If no UC fallback needed, return vector results
    if not uc_name:
        print(" No UC name provided — returning vector search results.")
        return [item["content"] for item in data]

    # --- STEP 2: UC fallback search ---
    if uc_name:
        year = metadata_filter.get("year") if metadata_filter else None
        analysis_type = (
            metadata_filter.get("analysis_type") if metadata_filter else None
        )

        # Normalize UC list
        if isinstance(uc_name, list):
            uc_list = [normalize_uc_name(u) for u in uc_name]
        else:
            uc_split = re.split(r"\band\b|,|&", uc_name, flags=re.IGNORECASE)
            uc_list = [normalize_uc_name(u.strip()) for u in uc_split if u.strip()]

        all_matches = []

        for single_uc in uc_list:
            print(
                f"\n Running UC fallback for '{single_uc}' (year={year}, analysis={analysis_type})..."
            )

            search_variants = [
                single_uc,
                single_uc.title(),
                single_uc.replace(" uc", "").strip(),
                single_uc.replace(" ", "%"),
                single_uc.split()[0] if " " in single_uc else single_uc,
            ]

            for variant in search_variants:
                print(f" Trying variant: {variant}")

                query = (
                    supabase.table("documents")
                    .select("content, metadata")
                    .ilike("metadata->>uc_name", f"%{variant}%")
                )

                # Analysis type filter
                if analysis_type:
                    query = query.eq("metadata->>analysis_type", analysis_type)

                # YEAR FILTER (fully fixed)
                if year is not None:
                    if isinstance(year, (list, tuple)):
                        valid_years = [str(y) for y in year]
                        query = query.in_("metadata->>year", valid_years)
                    else:
                        query = query.eq("metadata->>year", str(year))

                result = query.execute()
                if result.data:
                    print(f" Found {len(result.data)} rows for '{variant}'")
                    all_matches.extend(result.data)

        # Deduplicate
        unique_matches = {}
        for d in all_matches:
            uc_meta = d["metadata"].get("uc_name", "").strip().lower()
            for target_uc in uc_list:
                if target_uc in uc_meta:
                    unique_matches[uc_meta] = d

        if unique_matches:
            print(f" UC fallback found {len(unique_matches)} unique matches.")
            data = list(unique_matches.values())  # replace with UC data
        else:
            print("⚠ UC fallback found no matches.")

    # --- STEP 3: Final output ---
    return [item["content"] for item in data]


def build_synthetic_context(row):
    meta = row.get("metadata", {})
    uc = meta.get("uc_name")
    year = meta.get("year")
    val = meta.get("mean_value")
    color = meta.get("color")
    a_type = meta.get("analysis_type").upper()

    return (
        f"{a_type} REPORT — UC: {uc}, Year: {year}\n"
        f"Mean Value: {val}, Color: {color}\n"
    )
    
    
def interpret_color(analysis_type, color):
    if not color:
        return None

    legend = COLOR_LEGENDS.get(analysis_type.lower(), {})
    return legend.get(color.upper())

# ----------------------------
# Main Chatbot RAG Function 
# ----------------------------
def run_chatbot_query(query: str):
    """Runs RAG chatbot query using Supabase embeddings and Gemini.
    Supports NDVI / THERMAL / AQI with multiple years and UC filtering.
    If the user asks a comparative question (which year had better/... overall),
    the function will compare ALL available years for the requested analysis type.
    """

    if not query.strip():
        raise ValueError("Query cannot be empty")

    # -----------------------------------------
    # EARLY CHECK: Color legend direct query
    # -----------------------------------------
    hex_match = re.search(r"#(?:[0-9A-Fa-f]{6})", query)
    if hex_match:
        color = hex_match.group().upper()
        for analysis_type, legend_map in COLOR_LEGENDS.items():
            if color in legend_map:
                meaning = legend_map[color]
                return f"{color} means: {meaning} ({analysis_type.upper()} legend)"
        return f"I could not find any meaning for color {color} in NDVI, AQI, or Thermal legends."

    # -----------------------------------------
    # Extract years
    # -----------------------------------------
    years_found = re.findall(r"\b(20[0-9]{2})\b", query)
    years_found = [int(y) for y in years_found]

    year_in_query = []

    if len(years_found) >= 2:
        start, end = years_found[0], years_found[1]

        query_lower = query.lower()

        # CASE 1: Expand if user clearly wrote a RANGE
        if ("from" in query_lower and "to" in query_lower) or \
           ("between" in query_lower and "and" in query_lower):

            if start <= end:
                year_in_query = list(range(start, end + 1))
            else:
                year_in_query = list(range(end, start + 1))

        # CASE 2: User wrote only separate years → use exact years
        else:
            year_in_query = years_found

    else:
        # zero or one year → use directly
        year_in_query = years_found

    
    # -----------------------------------------
    # Parse AI metadata
    # -----------------------------------------
    tasks, uc_name = parse_query_metadata(query)

    # -----------------------------------------
    # Strong multi-analysis-type detection
    # -----------------------------------------

    # -----------------------------------------
    # AI + Regex Hybrid Analysis Type Detection
    # -----------------------------------------

    q_lower = query.lower()

    # 1. AI detection
    ai_types = detect_analysis_type_with_ai(query)

    # 2. Regex fallback
    regex_types = []

    if any(w in q_lower for w in [
        "ndvi", "vegetation", "green", "greenery", "trees", "plants",
        "tree cover", "canopy", "vegetation index", "land cover"
    ]):
        regex_types.append("ndvi")

    if any(w in q_lower for w in [
        "aqi", "air quality", "pollution", "pm2", "pm10", "smog",
        "dust", "weather", "haze", "air pollution"
    ]):
        regex_types.append("aqi")

    if any(w in q_lower for w in [
        "thermal", "temperature", "temp", "heat", "hotspots",
        "urban heat", "lst", "surface temp", "heatwave"
    ]):
        regex_types.append("thermal")

      # 3. merge both
    multi_types = list(set(ai_types + regex_types))

    if multi_types and (not tasks or len(tasks) == 1):
        print("Detected analysis types:", multi_types)
        tasks = [{"analysis_type": t, "years": None} for t in multi_types]

        # -----------------------------------------
        # HARD RULE — Per-analysis-type year extraction (IMPROVED)
        # -----------------------------------------
        lower_q = query.lower()

        for t in tasks:
            atype = t["analysis_type"]
            pattern = rf"{atype}[^0-9]((?:20[0-9]{{2}}(?:\s,?|\s+and\s+)?)*)"
            match = re.search(pattern, lower_q)

            if match:
                years = [int(y) for y in re.findall(r"20[0-9]{2}", match.group(1))]
                if years:
                    t["years"] = years

        #  SMART MERGE: Keep specific years + also include missed global ones
        if year_in_query:
            print("Detected year(s) from regex:", year_in_query)
            for t in tasks:
                if t.get("years") is None:
                    t["years"] = year_in_query
                else:
                    # merge without duplicates
                    t["years"] = sorted(list(set(t["years"] + year_in_query)))


    # ---------------------------------------------------------
    # detect comparative queries 
    # ---------------------------------------------------------
    regex_detected_trend = bool(
        re.search(
            r"(trend|over\s+years|yearly\s+trend|multi\s+year|year\s+wise|"
            r"across\s+years|variation\s+over\s+years|change\s+over\s+time)",
            query, re.IGNORECASE
        )
    )

    ai_detected_trend = detect_trend_with_ai(query)

    # force comparative mode for implicit comparison words
    implicit_compare = bool(
        re.search(
            r"(better|best|worse|worst|improve|improved|decline|increase|decrease|"
            r"highest|lowest|max|min|hotter|cooler)",
            query,
            re.IGNORECASE
        )
    )

    comparative_query = regex_detected_trend or ai_detected_trend or implicit_compare

    # -----------------------------------------
    # Step 2: Embedding
    # -----------------------------------------
    query_embedding = get_embedding(query)

    fetched = {}  # { analysis_type: { year: [rows...] } }

    # Helper: latest year for analysis
    def latest_year_for_analysis(a_type):
        res = (
            supabase.table("documents")
            .select("metadata")
            .eq("metadata->>analysis_type", a_type)
            .order("metadata->>year", desc=True)
            .limit(1)
            .execute()
        )
        if res.data and "metadata" in res.data[0]:
            try:
                return int(res.data[0]["metadata"]["year"])
            except:
                return None
        return None

    any_data_found = False

    # -----------------------------------------
    # Step 3: Fetch data for each task
    # -----------------------------------------
    for task in tasks:
        a_type = task.get("analysis_type")
        years = task.get("years")  # may be None or list

        if a_type not in fetched:
            fetched[a_type] = {}

        # ----------------------------------------------------
        # If no years → special rules
        # - If it's a comparative query (comparative_query=True)
        #   fetch ALL available years for that analysis_type
        # - Else fallback to latest year
        # ----------------------------------------------------
        if not years:

            if comparative_query:
                # Fetch all indexed years for this analysis_type
                res = (
                    supabase.table("documents")
                    .select("metadata")
                    .eq("metadata->>analysis_type", a_type)
                    .execute()
                )

                years = sorted(
                    {
                        int(r["metadata"]["year"])
                        for r in (res.data or [])
                        if ("metadata" in r and "year" in r["metadata"])
                    }
                )

                if years:
                    print(f"No years provided & comparative question — comparing all {a_type.upper()} years: {years}")
                else:
                    # nothing found: fallback to latest year behavior
                    latest = latest_year_for_analysis(a_type)
                    if latest:
                        years = [latest]
                        print(f"No indexed years for {a_type}; defaulting to latest: {latest}")
                    else:
                        print(f"No indexed data found for analysis_type={a_type}")
                        continue

            else:
                # Fallback: use latest single year
                latest = latest_year_for_analysis(a_type)
                if latest:
                    years = [latest]
                    print(f"No years specified for {a_type} — using latest: {latest}")
                else:
                    print(f"No indexed data found for analysis_type={a_type}")
                    continue

        # Ensure list type
        if isinstance(years, int):
            years = [years]
        elif isinstance(years, tuple):
            years = list(years)

         # -----------------------------------------
        # Fetch each year
        # -----------------------------------------
        for y in years:
            y_str = str(y)
            print(f" Fetching {a_type.upper()} data for {uc_name or 'city'} ({y})")

            rpc_params = {
                "query_embedding": query_embedding,
                "match_count": 10,
                "filter": {"analysis_type": a_type, "year": y},
            }

            if uc_name:
                rpc_params["filter"].pop("uc_name", None)

            if not uc_name:
                rows = (
                    supabase.table("documents")
                    .select("content, metadata")
                    .eq("metadata->>analysis_type", a_type)
                    .eq("metadata->>year", y_str)
                    .execute()
                ).data or []
            else:
                resp = supabase.rpc("match_documents", rpc_params).execute()
                rows = resp.data or []

            # ------------ FIXED INDENT STARTS HERE ------------
            if not rows and uc_name:
                uc_variants = []
                if isinstance(uc_name, list):
                    uc_variants = [normalize_uc_name(u) for u in uc_name]
                else:
                    uc_variants = [
                        normalize_uc_name(u.strip())
                        for u in re.split(r"\band\b|,|&", uc_name)
                        if u.strip()
                    ]

                fallback_rows = []
                for single_uc in uc_variants:
                    search_variants = [
                        single_uc,
                        single_uc.title(),
                        single_uc.replace(" uc", "").strip(),
                        single_uc.replace(" ", "%"),
                        single_uc.split()[0] if " " in single_uc else single_uc,
                    ]
                    for variant in search_variants:
                        q = (
                            supabase.table("documents")
                            .select("content, metadata")
                            .ilike("metadata->>uc_name", f"%{variant}%")
                            .eq("metadata->>analysis_type", a_type)
                            .eq("metadata->>year", y_str)
                        )
                        r = q.execute()
                        if r.data:
                            fallback_rows.extend(r.data)

                rows = fallback_rows

            # Normalize metadata
            for d in rows:
                try:
                    d["metadata"]["year"] = int(d["metadata"].get("year", y))
                except:
                    d["metadata"]["year"] = y

                if uc_name:
                    d["metadata"]["uc_name"] = uc_name

            # Store rows
            if rows:
                any_data_found = True
                fetched[a_type].setdefault(y, []).extend(rows)
            else:
                print(f"  No rows found for {a_type} {y} (uc={uc_name})")
            # ------------ FIXED INDENT ENDS HERE ------------



    if not any_data_found:
        return "I don’t have sufficient report data to answer that."

    # -----------------------------------------
    # Step 4: Build context text to pass to Gemini
    # -----------------------------------------
    context_blocks = []

    for a_type in sorted(fetched.keys()):
        context_blocks.append(f"=== {a_type.upper()} REPORT ===")
        years_dict = fetched[a_type]

        for yr in sorted(years_dict.keys()):
            context_blocks.append(f"--- {yr} ---")
            for r in years_dict[yr]:
                meta = r.get("metadata", {})
                uc = meta.get("uc_name") or "citywide"
                mv = meta.get("mean_value")
                clr = meta.get("color")

                category = None
                if clr and a_type in COLOR_LEGENDS:
                    category = COLOR_LEGENDS[a_type].get(clr)

                # Use synthetic fallback ONLY if content missing
                content = r.get("content") or build_synthetic_context(r)

                if category:
                    context_blocks.append(
                        f"UC: {uc}, Mean: {mv}, Color: {clr} ({category}) | {content[:300]}"
                    )
                else:
                    context_blocks.append(
                        f"UC: {uc}, Mean: {mv}, Color: {clr} | {content[:300]}"
                    )

        context_blocks.append("")

    context_text = "\n".join(context_blocks)


    # -----------------------------------------
    # Step 5: Build prompt and ask Gemini
    # -----------------------------------------
    prompt = f"""
    You are an Urban Analytics Assistant.

    CONTEXT:
    {context_text}

    USER QUESTION:
    {query}

    RULES:
    - Use NDVI / AQI / THERMAL color legends when interpreting numbers.
    - If multiple years are present, compare them explicitly (e.g., mention which year has higher/lower mean).
    - If data is missing say: "I don’t have sufficient report data to answer that."
    """

    model = genai.GenerativeModel("models/gemini-2.5-pro")
    response = model.generate_content(prompt)

    return response.text.strip() if response and hasattr(response, "text") else "No answer generated."