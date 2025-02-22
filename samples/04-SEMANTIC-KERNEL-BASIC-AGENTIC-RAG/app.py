import os
import json
import requests
import chainlit as cl
from rich.console import Console
from rich.panel import Panel
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.models import VectorizableTextQuery
from openai import AzureOpenAI

# ----------------------------
# Configuration (set via environment variables)
# ----------------------------
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "your-azure-openai-api-key")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://your-azure-openai-endpoint.openai.azure.com/")
AZURE_OPENAI_CHAT_COMPLETION_DEPLOYED_MODEL_NAME = os.getenv("AZURE_OPENAI_CHAT_COMPLETION_DEPLOYED_MODEL_NAME", "gpt-4o")

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT", "https://your-search-service.search.windows.net")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_ADMIN_KEY", "your-azure-search-key")
SEARCH_INDEX_NAME = "fifa-legal-handbook"

BING_SEARCH_API_KEY = os.getenv("BING_SEARCH_API_KEY", "your-bing-search-api-key")
BING_SEARCH_ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"

# ----------------------------
# Initialize Azure OpenAI client and console
# ----------------------------
openai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
)
console = Console()

# ----------------------------
# Define search functions (tools)
# ----------------------------
def search_azure_ai_search(query: str) -> str:
    """Search the private FIFA Legal Handbook using Azure AI Search."""
    credential = AzureKeyCredential(AZURE_SEARCH_KEY)
    client = SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=SEARCH_INDEX_NAME,
        credential=credential,
    )
    results = client.search(
        search_text=query,
        vector_queries=[
            VectorizableTextQuery(
                text=query, k_nearest_neighbors=50, fields="text_vector"
            )
        ],
        query_type="semantic",
        semantic_configuration_name="default",
        search_fields=["chunk"],
        top=50,
        include_total_count=True,
    )
    retrieved_texts = [result.get("chunk", "") for result in results]
    context_str = "\n".join(retrieved_texts) if retrieved_texts else "No documents found."
    console.print(Panel(f"Tool Invoked: Azure AI Search\nQuery: {query}", style="bold yellow"))
    return context_str

def search_bing(query: str) -> str:
    """Search the public web using Bing Search API."""
    headers = {"Ocp-Apim-Subscription-Key": BING_SEARCH_API_KEY}
    params = {"q": query, "textDecorations": True, "textFormat": "Raw"}
    response = requests.get(BING_SEARCH_ENDPOINT, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        if "webPages" in data and "value" in data["webPages"]:
            snippets = [item.get("snippet", "") for item in data["webPages"]["value"]]
            result_text = "\n".join(snippets)
        else:
            result_text = "No Bing results found."
    else:
        result_text = f"Bing search failed with status code {response.status_code}."
    console.print(Panel(f"Tool Invoked: Bing Search\nQuery: {query}", style="bold magenta"))
    return result_text

# ----------------------------
# Define function schemas for OpenAI
# ----------------------------
functions = [
    {
        "name": "search_azure_ai_search",
        "description": (
            "Use this function to search the private FIFA Legal Handbook for legal guidelines, regulations, and disciplinary rules. "
            "This is used for answering questions related to FIFA rules and legal matters to assist referees."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to retrieve relevant legal data from the FIFA Legal Handbook",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_bing",
        "description": (
            "Use this function to perform a real-time web search for public information, news, and current events related to football. "
            "This helps provide context for queries about match incidents or disciplinary events."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to retrieve recent news and public data from the web",
                },
            },
            "required": ["query"],
        },
    },
]

# ----------------------------
# Define a system prompt to guide the agent's behavior
# ----------------------------
system_prompt = (
    "You are an expert assistant for FIFA referees. You have access to private legal data from the FIFA Legal Handbook "
    "and real-time public information via Bing Search. When a query concerns specific FIFA rules, legal guidelines, or "
    "disciplinary matters, prioritize retrieving information from the FIFA Legal Handbook using Azure AI Search. For queries "
    "about current events or match incidents, use Bing Search. If both aspects are relevant, synthesize answers from both sources."
)

# ----------------------------
# Agent logic: process user query with OpenAI function calling
# ----------------------------
async def run_agent(user_query: str) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query},
    ]
    # Initial call with function definitions
    response = openai_client.chat.completions.create(
        model=AZURE_OPENAI_CHAT_COMPLETION_DEPLOYED_MODEL_NAME,
        messages=messages,
        functions=functions,
        function_call="auto",
    )
    response_message = response.choices[0].message

    # Check if the model decided to call a function
    if response_message.function_call is not None:
        function_name = response_message.function_call.name
        function_args = json.loads(response_message.function_call.arguments)
        query_for_function = function_args.get("query")
        # Invoke the appropriate tool
        if function_name == "search_azure_ai_search":
            function_response = search_azure_ai_search(query=query_for_function)
        elif function_name == "search_bing":
            function_response = search_bing(query=query_for_function)
        else:
            function_response = "Function not found"
        # Second call: send function response back for synthesis
        second_response = openai_client.chat.completions.create(
            model=AZURE_OPENAI_CHAT_COMPLETION_DEPLOYED_MODEL_NAME,
            messages=messages + [
                response_message,
                {"role": "function", "name": function_name, "content": function_response},
            ],
        )
        final_answer = second_response.choices[0].message.content
        return f"Function Called: {function_name}\nFinal Answer: {final_answer}"
    else:
        return response_message.content

# ----------------------------
# Chainlit event handlers
# ----------------------------
@cl.on_chat_start
async def start_chat():
    await cl.Message(
        content="Hello Farzad, welcome to the Agentic RAG demo. Please ask your query about FIFA regulations or recent football events."
    ).send()

@cl.on_message
async def main(message: cl.Message):
    answer = await run_agent(message.content)
    await cl.Message(content=answer, author="Agent").send()
