import re
import json
import google.generativeai as genai
from supabase import create_client
from django.conf import settings
from urbananalytics.models import ProjectChatMessage

def is_safe_for_uc_extraction(query: str) -> bool:
    q = query.lower().strip()
    return not (
        is_contextual_followup(q)
        or is_trend_followup(q)
        or "summarize" in q
        or "report" in q
    )


SMALL_TALK = [
    "hi", "hello", "hey", "salam", "assalamualaikum",
    "how are you", "good morning", "good evening", "hi there", "hey there"
]

OFF_TOPIC = [
    "weather", "rain", "sunny", "picnic", "joke", "funny",
    "football", "cricket", "movie", "song", "recipe", "travel",
    "trip", "fashion", "game", "love", "relationship"
]

COLOR_LEGENDS = {
    "ndvi": {
        "#ffffcc": "No vegetation – bare soil, urban areas, water, or sand (< 0.2)",
        "#c2e699": "Sparse vegetation – few plants, grassland, low crop coverage (0.2 – 0.39)",
        "#78c679": "Moderate vegetation – healthy plants, crop fields (0.4 – 0.59)",
        "#31a354": "Dense vegetation – forests, parks, thick crops (0.6 – 0.79)",
        "#006837": "Very dense vegetation – tropical forest, extremely healthy canopy (≥ 0.8)",
    },

    "thermal": {
        "#00008B": "Very cold / coolest surfaces (< 288 K | < 14.85°C)",
        "#00FFFF": "Cool surfaces (288 – 292.99 K | 14.85 – 19.85°C)",
        "#00FF00": "Moderate / mild surfaces (293 – 297.99 K | 19.85 – 24.85°C)",
        "#FFFF00": "Warm surfaces (298 – 302.99 K | 24.85 – 29.85°C)",
        "#FFA500": "Hot surfaces (303 – 307.99 K | 29.85 – 34.85°C)",
        "#FF4500": "Very hot surfaces (308 – 312.99 K | 34.85 – 39.85°C)",
        "#FF0000": "Extremely hot / highest LST (≥ 313 K | ≥ 39.85°C)",
    },

    "aqi": {
        "#00E400": "Good – Air quality is satisfactory, little or no health risk (0 – 50)",
        "#FFFF00": "Moderate – Air quality acceptable, sensitive groups may be affected (51 – 100)",
        "#FF7E00": "Unhealthy for Sensitive Groups – Sensitive people may experience effects (101 – 150)",
        "#FF0000": "Unhealthy – Everyone may begin to experience health effects (151 – 200)",
        "#8F3F97": "Very Unhealthy – Health alert, everyone may experience serious effects (201 – 300)",
        "#7E0023": "Hazardous – Emergency conditions, entire population at risk (> 300)",
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
    q_lower = query.lower()
    
    uc_names = set()
    
    uc_with_suffix = re.findall(r'(\b(?:[a-z]+ )?[a-z]+)\s+(?:uc|union council)', q_lower)
    if uc_with_suffix:
        uc_names.update(uc_with_suffix)
    
    before_uc = re.split(r'\s+(?:uc|union council)', q_lower)
    for i, part in enumerate(before_uc[:-1]):
        words = part.split()
        for j in range(len(words) - 1, -1, -1):
            if words[j] not in ['tell', 'show', 'me', 'for', 'of', 'the', 'a', 'an', 'and']:
                candidate = ' '.join(words[j:])
                if len(candidate.split()) <= 3 and not any(y in candidate for y in ['2024', '2023', '2022', '2021', '2020', 'ndvi', 'aqi', 'thermal']):
                    uc_names.add(candidate)
                break
    
    banned_uc_words = ['hi', 'hello', 'hey', 'thanks', 'ok', 'fine', 'salam', 'assalamualaikum', 'good', 'morning', 'evening', 'what', 'how', 'why', 'when', 'where', 'who', 'which', 'tell', 'show', 'me', 'please', 'about', 'tell me', 'show me']
    
    query_without_prefix = re.sub(r'^(tell\s+me|show\s+me|give\s+me|get\s+me)\s+', '', q_lower)
    
    parts = re.split(r'[,&]|\s+and\s+', query_without_prefix)
    for part in parts:
        part = part.strip()
        if part and len(part) > 1:
            if not any(kw in part for kw in ['2024', '2023', '2022', '2021', '2020', '2025', 'ndvi', 'aqi', 'thermal', 'year', 'data', 'what', 'how', 'why', '?']) and 'uc' not in part and 'union' not in part:
                if len(part.split()) <= 3:
                    if part not in banned_uc_words and part not in ['the', 'a', 'an', 'for', 'of', 'at', 'in', 'on']:
                        uc_names.add(part)
    
    uc_names = [u for u in uc_names if u]
    
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
    - Handle typos: "nd vi" = "ndvi", "nd vi" = "ndvi", "aqi" variations

    USER QUERY:
    {query}

    NOW RETURN ONLY THE JSON:
    """

    model = genai.GenerativeModel("models/gemini-2.5-pro")
    response = model.generate_content(prompt)

    raw = response.text.strip().replace("json", "").strip()
    try:
        data = json.loads(raw)
        ai_ucs = data.get("uc_names", [])
        final_ucs = ai_ucs if ai_ucs else uc_names
        return data.get("tasks", []), final_ucs
    except Exception:
        return [], uc_names


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
    last_detected_analysis_type: Optional[str]
    last_years: Optional[List[int]]
    last_uc_names: Optional[List[str]]
    project_id: int
    history: str

def clear_uc_for_followup(state: ChatState) -> ChatState:
    state["uc_name"] = None
    return state
def is_contextual_followup(query: str) -> bool:
    q = query.lower().strip()

    followup_phrases = [
        "what about",
        "how about",
        "and what about",
        "and",
        "earlier",
        "previous",
        "last year",
        # explanation
        "explain",
        "explain more",
        "tell me more",
        "what does this mean",
        "elaborate",
        "expand",

        # why / cause
        "why is it",
        "why is this",
        "reason",
        "cause",
        "because of",

        # impact
        "impact",
        "effect",
        "consequence",
        "health impact",
        "environmental impact",

        # improvement / recommendation
        "how can we improve",
        "how to improve",
        "how can we reduce",
        "how to reduce",
        "solution",
        "recommendation",
        "what should be done",

        # judgement
        "is it bad",
        "is it good",
        "is this normal",
    ]

    return any(p in q for p in followup_phrases)
def is_trend_followup(query: str) -> bool:
    q = query.lower().strip()
    return any(
        p in q
        for p in [
            "year by year",
            "over years",
            "worsening",
            "improving",
            "trend",
            "increase",
            "decrease",
            "change over time",
        ]
    )

def analyze_query_node(state: ChatState) -> ChatState:
    query = state["query"]
    q_lower = query.lower().strip()
    is_followup = is_contextual_followup(q_lower) or is_trend_followup(q_lower)
    project_id = state.get("project_id")  

    has_analysis_type = any(kw in q_lower for kw in ['ndvi', 'aqi', 'thermal', 'vegetation', 'air quality', 'pollution', 'temperature', 'heat', 'thermal'])
    if any(greet in q_lower for greet in SMALL_TALK) and not has_analysis_type:
        state["final_answer"] = (
            "Hello! I can help you with environmental analytics such as NDVI, AQI, "
            "and Thermal data. Ask me anything related to vegetation, pollution, "
            "heat, UC-based yearly analysis, or satellite reports."
        )
        state["answered_directly"] = True
        return state

    if any(word in q_lower for word in OFF_TOPIC):
        state["final_answer"] = (
            "I may not be able to answer this because it is not related to satellite "
            "analytics. I can help you analyze NDVI (vegetation), AQI (air quality), "
            "Thermal (surface heat), yearly trends, UC comparisons, and project reports."
        )
        state["answered_directly"] = True
        return state
    
    analysis_keywords = [
        "summarize",
        "conclude",
        "tell me further",
        "tell me more",
        "analyze this",
        "what do you think",
        "your opinion",
        "insights on",
    ]

    has_summary_intent = any(kw in q_lower for kw in analysis_keywords)

    has_year = bool(re.search(r"\b20[0-9]{2}\b", q_lower))
    has_explicit_analysis_type = any(
        kw in q_lower
        for kw in [
            "ndvi",
            "aqi",
            "thermal",
            "air quality",
            "vegetation",
            "temperature",
        ]
    )

    if has_summary_intent and not has_year and not has_explicit_analysis_type:
        model = genai.GenerativeModel("models/gemini-2.5-pro")

        prompt = f"""
        The user is asking to summarize or analyze text they provided.

        USER REQUEST:
        {query}

        RULES:
        - Summarize or analyze ONLY the provided text
        - Do NOT fetch database reports
        - If no text is provided yet, politely ask the user to paste it
        """

        response = model.generate_content(prompt)

        state["final_answer"] = (
            response.text.strip()
            if response and hasattr(response, "text")
            else "Please provide the text you want me to summarize."
        )
        state["answered_directly"] = True
        return state

    last_analysis_type = None
    
    state_last_type = state.get("last_detected_analysis_type")
    if state_last_type:
        last_analysis_type = state_last_type

    years_found = re.findall(r"\b(20[0-9]{2})\b", query)
    years_found = [int(y) for y in years_found]
    year_in_query: List[int] = []

    if len(years_found) >= 2:
        start, end = years_found[0], years_found[1]
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

    if not year_in_query and state.get("last_years"):
        year_in_query = state.get("last_years", [])

    state["years_in_query"] = year_in_query


    if (
        is_contextual_followup(q_lower)
        and not has_explicit_analysis_type
    ):
        last_type = state.get("last_detected_analysis_type")
        last_years = state.get("last_years")

        if last_type:
            state["tasks"] = [
                {
                    "analysis_type": last_type,
                    "years":state.get("years_in_query") or last_years,
                }
            ]
            state["comparative_query"] = False
            state["last_detected_analysis_type"] = last_type
            state["uc_name"] = None   # force citywide
            state["answered_directly"] = False
            return state

    if (
        is_trend_followup(q_lower)
        and not has_year
    ):
        last_type = state.get("last_detected_analysis_type")

        if last_type:
            state["tasks"] = [
                {
                    "analysis_type": last_type,
                    "years": None,   # fetch ALL years
                }
            ]
            state["comparative_query"] = True
            state["uc_name"] = None   # citywide only
            return state


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

    
    tasks, uc_name = parse_query_metadata(query)
    if is_contextual_followup(q_lower) or is_trend_followup(q_lower):
        if not uc_name:   
           uc_name = None

    if (not tasks or len(tasks) == 0) and last_analysis_type:
        tasks = [{"analysis_type": last_analysis_type, "years": None}]
    

    citywide_keywords = ["citywide", "all ucs", "overall", "city wide", "entire city", "all union councils"]
    is_citywide_request = any(kw in q_lower for kw in citywide_keywords)
    
    has_year_range = len(year_in_query) > 1 or ("from" in q_lower and "to" in q_lower) or ("between" in q_lower and "and" in q_lower)
   
    regex_detected_trend = bool(
        re.search(
            r"(trend|over\s+the\s+years|over\s+years|yearly\s+trend|multi\s+year|year\s+wise|"
            r"across\s+years|change\s+over\s+time|comparison|compare)",
            query, re.IGNORECASE
        )
    )
    implicit_compare = bool(
        re.search(
            r"(better|best|worse|worst|increase|decrease|max|min|hotter|cooler)",
            query, re.IGNORECASE
        )
    )
    
    ai_detected_trend = False
    if regex_detected_trend or implicit_compare or len(year_in_query) > 1:
        ai_detected_trend = detect_trend_with_ai(query)

    state["comparative_query"] = regex_detected_trend or ai_detected_trend or implicit_compare    
    
    explicit_uc_in_text = bool(re.search(r"\b(uc|union council|colony|town|township|sector|block|park|gate|pura|abad|bagh|nagar)\b", q_lower))

    if (
        not uc_name
        and state.get("last_uc_names")
        and not is_citywide_request
        and not has_year_range
        and not state.get("comparative_query")  
        and not explicit_uc_in_text 
    ):
        uc_name = state.get("last_uc_names")

    state["tasks"] = tasks
    state["uc_name"] = uc_name

    ai_types = detect_analysis_type_with_ai(query)
    regex_types = []

    ndvi_pattern = r"(ndvi|n\s*d\s*v\s*i|vegetation|green|greenery|trees|plants|tree\s+cover|canopy|vegetation\s+index|land\s+cover)"
    aqi_pattern = r"(aqi|a\s*q\s*i|air\s+quality|pollution|pm2|pm10|smog|dust|haze|air\s+pollution)"
    thermal_pattern = r"(thermal|temperature|temp|heat|hotspots|urban\s+heat|lst|surface\s+temp|heatwave)"

    if re.search(ndvi_pattern, q_lower):
        regex_types.append("ndvi")
    
    if re.search(aqi_pattern, q_lower):
        regex_types.append("aqi")
    
    if re.search(thermal_pattern, q_lower):
        regex_types.append("thermal")

    multi_types = list(set(ai_types + regex_types))
    if not multi_types and last_analysis_type:
            multi_types=[last_analysis_type]
    elif not multi_types:
            state["final_answer"] = (
            "Please mention the analysis type you want. Examples: NDVI, AQI, Thermal."
            )
            state["answered_directly"] = True
            return state

    if multi_types and (not tasks or len(tasks) == 1):
        tasks = [{"analysis_type": t, "years": None} for t in multi_types]

        lower_q = q_lower
        for t in tasks:
            atype = t["analysis_type"]
            pattern = rf"{atype}[^0-9]((?:20[0-9]{{2}}(?:\s,?|\s+and\s+)?)*)"
            match = re.search(pattern, lower_q)
            if match:
                years = [int(y) for y in re.findall(r"20[0-9]{2}", match.group(1))]
                if years:
                    t["years"] = years

        if year_in_query:
            for t in tasks:
                if t.get("years") is None:
                    t["years"] = year_in_query
                else:
                    t["years"] = sorted(list(set(t["years"] + year_in_query)))

    state["tasks"] = tasks

    state["answered_directly"] = False
    if multi_types:
       state["last_detected_analysis_type"] = multi_types[0]
    
    if not state.get("answered_directly"):
        if uc_name and isinstance(uc_name, (list, tuple)) and len(uc_name) > 0:
            state["last_uc_names"] = uc_name
        elif uc_name and isinstance(uc_name, str):
            state["last_uc_names"] = [uc_name]

    return state

def route_after_analyze(state: ChatState) -> str:
    if state.get("answered_directly"):
        return "done"
    return "continue"


def embedding_node(state: ChatState) -> ChatState:
    state["query_embedding"] = get_embedding(state["query"])
    return state

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


def fetch_data_node(state: ChatState) -> ChatState:
    tasks = state.get("tasks") or []
    uc_name = state.get("uc_name")
    query_embedding = state.get("query_embedding")
    comparative = state.get("comparative_query", False)

    fetched: Dict[str, Dict[int, List[dict]]] = {}
    any_data_found = False

    for task in tasks:
        a_type = task.get("analysis_type")
        years = task.get("years")  

        if not a_type:
            continue

        if a_type not in fetched:
            fetched[a_type] = {}

        if not years:

            if not comparative:
                latest = latest_year_for_analysis(a_type)
                if latest:
                    years = [latest]
                else:
                    continue

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
            if comparative and not uc_name:
               rows = [
                  r for r in rows
                 if not r.get("metadata", {}).get("uc_name")
               ]

        
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


def answer_node(state: ChatState) -> ChatState:
    context_text = state.get("context_text", "")
    query = state["query"]

    comparative = state.get("comparative_query", False)
    
    comparison_rule = ""
    if comparative:
        comparison_rule = "- If multiple years are present in the data, compare them explicitly and highlight trends."
    else:
        comparison_rule = "- Do NOT compare with other years unless explicitly asked. Focus only on the requested year(s)."
    no_uc_rule = ""
    if comparative and not state.get("uc_name"):
        no_uc_rule = (
            "- This is a CITYWIDE analysis.\n"
            "- Do NOT mention any specific Union Council (UC) names.\n"
            "- Do NOT compare individual UCs.\n"
            "- Describe trends using overall averages, minimums, maximums, or general patterns only.\n"
        )
    
    prompt = f"""
    You are an Urban Analytics Assistant.

    CONVERSATION HISTORY (PROJECT-SPECIFIC):
    {state.get("history", "")}

    REPORT CONTEXT:
    {context_text}

    USER QUESTION:
    {query}

    RULES:
    - Use NDVI / AQI / THERMAL color legends when interpreting numbers.
    {no_uc_rule}
    {comparison_rule}
    - Only discuss the analysis types requested in the USER QUESTION.
    - Do NOT introduce geographic names unless explicitly asked by the user.
    - Do NOT mention or apologize for missing data types that were not requested.
    - Only say "I don't have sufficient report data" if the requested analysis type has no data.
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

    graph.add_conditional_edges(
        "analyze_query",
        route_after_analyze,
        {
            "done": END,
            "continue": "embedding",
        },
    )

    graph.add_edge("embedding", "fetch_data")

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

def get_last_analysis_type(project_id):
    user_msgs = (
        ProjectChatMessage.objects
        .filter(project_id=project_id, role="user")
        .order_by("-timestamp")
    )

    for msg in user_msgs:
        text = msg.message.lower()

        if is_contextual_followup(text) or is_trend_followup(text):
            continue

        if "thermal" in text or "temperature" in text or "heat" in text:
            return "thermal"

        if "aqi" in text or "air quality" in text or "pollution" in text:
            return "aqi"

        if "ndvi" in text or "vegetation" in text or "green" in text:
            return "ndvi"

    return None


def get_last_years(project_id):
    user_msgs = (
        ProjectChatMessage.objects
        .filter(project_id=project_id, role="user")
        .order_by("-timestamp")
    )

    for msg in user_msgs:
        text = msg.message.lower()

        if is_contextual_followup(text) or is_trend_followup(text):
            continue

        if not any(k in text for k in [
            "ndvi", "aqi", "thermal",
            "air quality", "vegetation", "temperature"
        ]):
            continue

        years = re.findall(r"\b(20[0-9]{2})\b", text)
        if years:
            return [int(y) for y in years]

    return None



def get_last_uc_names(project_id):
    user_msgs = (
        ProjectChatMessage.objects
        .filter(project_id=project_id, role="user")
        .order_by("-timestamp")
        .all()
    )

    for msg in user_msgs:
        message = msg.message
        if not is_safe_for_uc_extraction(message):
           continue

        tasks, uc_names = parse_query_metadata(message)
        if uc_names:
           return uc_names

    
    return None
def strip_uc_from_history(history: str) -> str:
    uc_keywords = ["township", "minhala", "union council", "uc"]
    lines = history.split("\n")
    cleaned = [
        line for line in lines
        if not any(uc in line.lower() for uc in uc_keywords)
    ]
    return "\n".join(cleaned)

_LANGGRAPH_APP = None

def run_chatbot_query_langgraph(query: str, project_id: int) -> str:
    global _LANGGRAPH_APP

    if not query.strip():
        raise ValueError("Query cannot be empty")

    history_qs = ProjectChatMessage.objects.filter(project_id=project_id).order_by("timestamp")
    history_text = "\n".join([f"{m.role}: {m.message}" for m in history_qs])

    if detect_trend_with_ai(query) and not is_safe_for_uc_extraction(query):
       history_text = strip_uc_from_history(history_text)
    last_type = get_last_analysis_type(project_id)
    last_years = get_last_years(project_id)
    last_ucs = get_last_uc_names(project_id)

    if _LANGGRAPH_APP is None:
        _LANGGRAPH_APP = build_langgraph()

    initial_state = {
        "query": query,
        "history": history_text,
        "project_id": project_id,
        "last_detected_analysis_type": last_type,
        "last_years": last_years,
        "last_uc_names": last_ucs,
    }

    final_state = _LANGGRAPH_APP.invoke(initial_state)

    ProjectChatMessage.objects.create(project_id=project_id, role="user", message=query)
    ProjectChatMessage.objects.create(project_id=project_id, role="assistant", message=final_state.get("final_answer", ""))

    return final_state.get("final_answer", "No answer generated.")