import re
import json
import google.generativeai as genai
from supabase import create_client
from django.conf import settings

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

genai.configure(api_key=settings.GOOGLE_API_KEY)
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


def detect_trend_with_ai(query: str) -> bool:
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
    text = text.replace("json", "").strip()

    try:
        data = json.loads(text)
        return bool(data.get("trend", False))
    except Exception:
        return False


def detect_analysis_type_with_ai(query: str):
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

    raw = resp.text.strip().replace("json", "").strip()
    try:
        data = json.loads(raw)
        types = data.get("types", [])
        return [t.lower() for t in types if t.lower() in ["ndvi", "aqi", "thermal"]]
    except Exception:
        return []


def normalize_uc_name(name: str):
    if not name:
        return None
    name = name.lower().strip()
    name = re.sub(r"[-_]+", " ", name)
    name = re.sub(r"\b(qilla|killa)\b", "qila", name)
    name = re.sub(r"\b(sittara|sitara)\b", "sittara", name)
    name = re.sub(r"\b(johartown|johar town)\b", "johar town", name)
    name = re.sub(r"\s+", " ", name)
    return name


def get_embedding(text: str):
    result = genai.embed_content(model="models/embedding-001", content=text)
    return result["embedding"]


def parse_query_metadata(query: str):
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
    - If a year is mentioned globally, apply it to ALL analysis types.
    - If no year is mentioned for a type, return years = null.
    - UC names are geographic places.

    USER QUERY:
    {query}

    NOW RETURN ONLY THE JSON:
    """

    model = genai.GenerativeModel("models/gemini-2.5-pro")
    response = model.generate_content(prompt)

    raw = response.text.strip().replace("json", "").strip()
    try:
        data = json.loads(raw)
        return data.get("tasks", []), data.get("uc_names", [])
    except Exception:
        return [], []


def build_synthetic_context(row):
    meta = row.get("metadata", {})
    uc = meta.get("uc_name")
    year = meta.get("year")
    val = meta.get("mean_value")
    color = meta.get("color")
    a_type = meta.get("analysis_type", "").upper()

    return (
        f"{a_type} REPORT — UC: {uc}, Year: {year}\n"
        f"Mean Value: {val}, Color: {color}\n"
    )
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END


class ChatState(TypedDict, total=False):
    query: str
    years_in_query: List[int]
    tasks: List[Dict[str, Any]]
    uc_name: Any
    comparative_query: bool
    query_embedding: List[float]
    fetched: Dict[str, Dict[int, List[dict]]]
    context_text: str
    final_answer: str
    answered_directly: bool


# ------------- Node 1: Analyze query & early color handling -------------
def analyze_query_node(state: ChatState) -> ChatState:
    query = state["query"]

    # 1) Early color legend check
    hex_match = re.search(r"#(?:[0-9A-Fa-f]{6})", query)
    if hex_match:
        color = hex_match.group().upper()
        for analysis_type, legend_map in COLOR_LEGENDS.items():
            if color in legend_map:
                meaning = legend_map[color]
                state["final_answer"] = f"{color} means: {meaning} ({analysis_type.upper()} legend)"
                state["answered_directly"] = True
                return state
        state["final_answer"] = (
            f"I could not find any meaning for color {color} in NDVI, AQI, or Thermal legends."
        )
        state["answered_directly"] = True
        return state

    # 2) Extract years (with range support)
    years_found = re.findall(r"\b(20[0-9]{2})\b", query)
    years_found = [int(y) for y in years_found]
    year_in_query: List[int] = []

    if len(years_found) >= 2:
        start, end = years_found[0], years_found[1]
        q_lower = query.lower()
        if ("from" in q_lower and "to" in q_lower) or \
           ("between" in q_lower and "and" in q_lower):
            if start <= end:
                year_in_query = list(range(start, end + 1))
            else:
                year_in_query = list(range(end, start + 1))
        else:
            year_in_query = years_found
    else:
        year_in_query = years_found

    state["years_in_query"] = year_in_query

    # 3) Parse AI metadata (tasks + uc_name)
    tasks, uc_name = parse_query_metadata(query)
    state["tasks"] = tasks
    state["uc_name"] = uc_name

    q_lower = query.lower()

    # 4) AI + regex analysis-type detection
    ai_types = detect_analysis_type_with_ai(query)
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

    multi_types = list(set(ai_types + regex_types))
    if not multi_types:
        state["final_answer"] = (
        "Please mention the analysis type you want. "
        "For example: NDVI, AQI, or Thermal."
    )
        state["answered_directly"] = True
        return state

    if multi_types and (not tasks or len(tasks) == 1):
        tasks = [{"analysis_type": t, "years": None} for t in multi_types]

        # Per-analysis-type year extraction
        lower_q = query.lower()
        for t in tasks:
            atype = t["analysis_type"]
            pattern = rf"{atype}[^0-9]((?:20[0-9]{{2}}(?:\s,?|\s+and\s+)?)*)"
            match = re.search(pattern, lower_q)
            if match:
                years = [int(y) for y in re.findall(r"20[0-9]{2}", match.group(1))]
                if years:
                    t["years"] = years

        # Merge global years
        if year_in_query:
            for t in tasks:
                if t.get("years") is None:
                    t["years"] = year_in_query
                else:
                    t["years"] = sorted(list(set(t["years"] + year_in_query)))

    state["tasks"] = tasks

    # 5) Comparative detection (regex + AI + implicit words)
    regex_detected_trend = bool(
        re.search(
        r"(trend|over\s+the\s+years|over\s+years|yearly\s+trend|multi\s+year|year\s+wise|"
        r"across\s+years|across\s+the\s+years|variation\s+over\s+years|"
        r"change\s+over\s+time|how\s+did.*change|comparison|compare)",
        query,
        re.IGNORECASE,)
    )
    ai_detected_trend = detect_trend_with_ai(query)
    implicit_compare = bool(
        re.search(
            r"(better|best|worse|worst|improve|improved|decline|increase|decrease|"
            r"highest|lowest|max|min|hotter|cooler)",
            query,
            re.IGNORECASE,
        )
    )

    state["comparative_query"] = regex_detected_trend or ai_detected_trend or implicit_compare
    state["answered_directly"] = False
    return state


# Used by LangGraph routing: decide next step
def route_after_analyze(state: ChatState) -> str:
    if state.get("answered_directly"):
        return "done"
    return "continue"


# ------------- Node 2: Embedding -------------
def embedding_node(state: ChatState) -> ChatState:
    state["query_embedding"] = get_embedding(state["query"])
    return state


# Helper: latest year lookup
def latest_year_for_analysis(a_type: str) -> Optional[int]:
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
        except Exception:
            return None
    return None


# ------------- Node 3: Fetch data (with UC fallback + comparative logic) -------------
def fetch_data_node(state: ChatState) -> ChatState:
    tasks = state.get("tasks") or []
    uc_name = state.get("uc_name")
    query_embedding = state.get("query_embedding")
    comparative = state.get("comparative_query", False)

    fetched: Dict[str, Dict[int, List[dict]]] = {}
    any_data_found = False

    for task in tasks:
        a_type = task.get("analysis_type")
        years = task.get("years")  # may be None or list

        if not a_type:
            continue

        if a_type not in fetched:
            fetched[a_type] = {}

        #  FIXED SMART YEAR LOGIC
        if not years:

            # If NOT comparative → use ONLY latest year
            if not comparative:
                latest = latest_year_for_analysis(a_type)
                if latest:
                    years = [latest]
                else:
                    continue

            # If comparative → fetch ALL years
            else:
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

                if not years:
                    latest = latest_year_for_analysis(a_type)
                    if latest:
                        years = [latest]
                    else:
                        continue

        if isinstance(years, int):
            years = [years]
        elif isinstance(years, tuple):
            years = list(years)

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

            # UC fallback
            if not rows and uc_name:
                uc_variants = (
                    [normalize_uc_name(u) for u in uc_name]
                    if isinstance(uc_name, list)
                    else [
                        normalize_uc_name(u.strip())
                        for u in re.split(r"\band\b|,|&", uc_name)
                        if u.strip()
                    ]
                )

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

            for d in rows:
                meta = d.get("metadata", {})
                try:
                    meta["year"] = int(meta.get("year", y))
                except Exception:
                    meta["year"] = y
                if uc_name:
                    meta["uc_name"] = uc_name
                d["metadata"] = meta

            if rows:
                any_data_found = True
                fetched[a_type].setdefault(y, []).extend(rows)
            else:
                print(f"  No rows found for {a_type} {y} (uc={uc_name})")

    state["fetched"] = fetched

    if not any_data_found:
        state["final_answer"] = "I don’t have sufficient report data to answer that."
        state["answered_directly"] = True

    return state



def route_after_fetch(state: ChatState) -> str:
    if state.get("answered_directly"):
        return "done"
    return "continue"
    

# ------------- Node 4: Build context text -------------
def build_context_node(state: ChatState) -> ChatState:
    fetched = state.get("fetched") or {}
    context_blocks: List[str] = []

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

    state["context_text"] = "\n".join(context_blocks)
    return state


# ------------- Node 5: Ask Gemini for final answer -------------
def answer_node(state: ChatState) -> ChatState:
    context_text = state.get("context_text", "")
    query = state["query"]

    prompt = f"""
    You are an Urban Analytics Assistant.

    CONTEXT:
    {context_text}

    USER QUESTION:
    {query}

    RULES:
    - Use NDVI / AQI / THERMAL color legends when interpreting numbers.
    - If multiple years are present, compare them explicitly.
    - If data is missing say: "I don’t have sufficient report data to answer that."
    """

    model = genai.GenerativeModel("models/gemini-2.5-pro")
    response = model.generate_content(prompt)

    state["final_answer"] = (
        response.text.strip()
        if response and hasattr(response, "text")
        else "No answer generated."
    )
    return state
from langgraph.graph import StateGraph, END


def build_langgraph():
    graph = StateGraph(ChatState)

    graph.add_node("analyze_query", analyze_query_node)
    graph.add_node("embedding", embedding_node)
    graph.add_node("fetch_data", fetch_data_node)
    graph.add_node("build_context", build_context_node)
    graph.add_node("answer", answer_node)

    graph.set_entry_point("analyze_query")

    # After analyze: either done (color legend) or continue
    graph.add_conditional_edges(
        "analyze_query",
        route_after_analyze,
        {
            "done": END,
            "continue": "embedding",
        },
    )

    graph.add_edge("embedding", "fetch_data")

    # After fetch: either stop or continue
    graph.add_conditional_edges(
        "fetch_data",
        route_after_fetch,
        {
            "done": END,
            "continue": "build_context",
        },
    )

    graph.add_edge("build_context", "answer")
    graph.add_edge("answer", END)

    return graph.compile()


# -------------------------------
# LangGraph app cache (performance)
# -------------------------------
_LANGGRAPH_APP = None


def run_chatbot_query_langgraph(query: str) -> str:
    global _LANGGRAPH_APP

    if not query.strip():
        raise ValueError("Query cannot be empty")

    if _LANGGRAPH_APP is None:
        _LANGGRAPH_APP = build_langgraph()

    final_state = _LANGGRAPH_APP.invoke({"query": query})
    return final_state.get("final_answer", "No answer generated.")