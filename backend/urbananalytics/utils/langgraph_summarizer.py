
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from typing import TypedDict
import os
import re


load_dotenv()

DISCLAIMER = (
    "The interpretations and recommendations are derived from a robust analysis "
    "of environmental data using AI-assisted tools. They provide indicative insights "
    "and are intended to support decision-making, but should be validated by domain experts "
    "before implementation."
)

class SummaryState(TypedDict):
    report_text: str
    report_type: str  
    summary: str
    interpretation: str
    recommendation: str



def summarize_report(state: SummaryState):
    llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",  
    google_api_key=os.getenv("GOOGLE_API_KEY")
)

    text = state["report_text"]
    r_type = state["report_type"]

    prompt = f"""
    You are an expert environmental analyst.
    Summarize the following {r_type} report in 4–6 clear lines.

    Focus on:
    - Key data findings
    - Trends or variations
    - Any noticeable differences (if comparison)
    - Implications for the environment

    ### Report Content:
    {text}
    """

    summary = llm.invoke(prompt).content
    return {"summary": summary}



def generate_interpretations(state: SummaryState):
    llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",  
    google_api_key=os.getenv("GOOGLE_API_KEY"))
    summary = state["summary"]
    r_type = state["report_type"]

    prompt = f"""
    You are an environmental expert.
    Based on the following {r_type} report summary, write detailed interpretations.
    Discuss what the data patterns mean in context of vegetation, temperature, or air quality.
    
    Write the interpretation, without any introductory phrases like “The provided summary…” or “According to the report…”.
    Start directly with the explanation of what the data indicates.
    
    ### Summary:
    {summary}
    """

    interpretation = llm.invoke(prompt).content
    return {"interpretation": interpretation}



def generate_recommendations(state: SummaryState):
    llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",  
    google_api_key=os.getenv("GOOGLE_API_KEY"))
    summary = state["summary"]
    r_type = state["report_type"]

    prompt = f"""
    You are an environmental policy advisor.
    Based on this {r_type} report summary, list 3–5 clear and actionable recommendations.
    Each recommendation should be practical, result-focused, and helpful for urban planners or decision-makers.
    Write only the recommendations as a numbered list. Do not include any introduction or conclusion.

    ### Summary:
    {summary}
    """

    recommendation = llm.invoke(prompt).content
    recommendation = re.sub(r'^\s*\d+[\.\)\-]\s*', '', recommendation, flags=re.MULTILINE)
    recommendation = re.sub(r"#+\s*", "", recommendation)
    return {"recommendation": recommendation}



graph = StateGraph(SummaryState)

graph.add_node("summarize", summarize_report)
graph.add_node("interpret", generate_interpretations)
graph.add_node("recommend", generate_recommendations)

graph.set_entry_point("summarize")
graph.add_edge("summarize", "interpret")
graph.add_edge("interpret", "recommend")
graph.set_finish_point("recommend")  


summarizer_graph = graph.compile()



def run_langgraph_summarizer(report_text: str, report_type: str):
    result = summarizer_graph.invoke({
        "report_text": report_text,
        "report_type": report_type
    })

    summary = result.get("summary", "")
    interpretation = result.get("interpretation", "")
    recommendation = result.get("recommendation", "")

    
    interpretation = f"{DISCLAIMER}\n\n{interpretation}"
    recommendation = f"{DISCLAIMER}\n\n{recommendation}"

    return summary, interpretation, recommendation