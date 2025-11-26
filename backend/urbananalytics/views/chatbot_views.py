from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# IMPORT THE LANGGRAPH FUNCTION
from urbananalytics.utils.langgraph_chatbot import run_chatbot_query_langgraph


@api_view(["POST"])
@permission_classes([AllowAny])
def chatbot_api(request):
    query = request.data.get("query", "")
    if not query:
        return Response({"error": "Missing query"}, status=400)

    try:
        answer = run_chatbot_query_langgraph(query)
        return Response({"answer": answer})
    except Exception as e:
        print("Chatbot error:", e)
        return Response({"error": str(e)}, status=500)