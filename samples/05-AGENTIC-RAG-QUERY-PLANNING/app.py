import os
import json
import requests
import pandas as pd
import pyodbc
import openai
from dotenv import load_dotenv
import sqlalchemy
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.models import VectorizableTextQuery
from openai import AzureOpenAI
import chainlit as cl

load_dotenv()

# ----------------------------
# Configuration
# ----------------------------
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "your-azure-openai-api-key")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://your-azure-openai-endpoint.openai.azure.com/")
AZURE_OPENAI_CHAT_COMPLETION_DEPLOYED_MODEL_NAME = os.getenv(
    "AZURE_OPENAI_CHAT_COMPLETION_DEPLOYED_MODEL_NAME", "gpt-4o-mini"
)  # update as needed

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT", "https://your-search-service.search.windows.net")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_ADMIN_KEY", "your-azure-search-key")
SEARCH_INDEX_NAME = "acc-guidelines-index"

BING_SEARCH_API_KEY = os.getenv("BING_SEARCH_API_KEY", "<YOUR-BING-SEARCH-KEY>")
BING_SEARCH_ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"

server = os.getenv("AZURE_SQL_SERVER_NAME")
database = os.getenv("AZURE_SQL_DATABASE_NAME")
username = os.getenv("AZURE_SQL_USER_NAME")
password = os.getenv("AZURE_SQL_PASSWORD")
driver = '{ODBC Driver 17 for SQL Server}'

AZURE_SQL_CONNECTION_STRING = f"DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}"

# ----------------------------
# Initialize Azure OpenAI client
# ----------------------------
openai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
)

# ----------------------------
# Define Tool Functions
# ----------------------------
def search_acc_guidelines(query: str) -> str:
    """
    Searches the Azure AI Search index 'acc-guidelines-index'
    for relevant American College of Cardiology (ACC) guidelines.
    """
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
                text=query,
                k_nearest_neighbors=10,  # Adjust as needed
                fields="embedding"       # Adjust based on your index schema
            )
        ],
        query_type="semantic",
        semantic_configuration_name="default",
        search_fields=["chunk"],
        top=10,
        include_total_count=True
    )
    retrieved_texts = [result.get("chunk", "") for result in results]
    context_str = "\n".join(retrieved_texts) if retrieved_texts else "No relevant guidelines found."
    return context_str

def search_bing(query: str) -> str:
    """
    Searches the public web using the Bing Search API.
    """
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
    return result_text

def lookup_patient_data(query: str) -> str:
    """
    Queries the 'PatientMedicalData' table in Azure SQL and returns the results as a string.
    'query' should be a valid SQL statement.
    """
    try:
        connection_uri = (
            f"mssql+pyodbc://{username}:{password}@{server}/{database}"
            "?driver=ODBC+Driver+17+for+SQL+Server"
        )
        engine = sqlalchemy.create_engine(connection_uri)
        df = pd.read_sql(query, engine)
        if df.empty:
            return "No rows found."
        return df.to_string(index=False)
    except Exception as e:
        return f"Database error: {str(e)}"

# ----------------------------
# Define Tools for the Agent
# ----------------------------
tools = [
    {
        "type": "function",
        "function": {
            "name": "lookup_patient_data",
            "description": (
                "Query the PatientMedicalData table in Azure SQL. "
                "The table schema is as follows:\n\n"
                "PatientID: INT PRIMARY KEY IDENTITY,\n"
                "FirstName: VARCHAR(100),\n"
                "LastName: VARCHAR(100),\n"
                "DateOfBirth: DATE,\n"
                "Gender: VARCHAR(20),\n"
                "ContactNumber: VARCHAR(100),\n"
                "EmailAddress: VARCHAR(100),\n"
                "Address: VARCHAR(255),\n"
                "City: VARCHAR(100),\n"
                "PostalCode: VARCHAR(20),\n"
                "Country: VARCHAR(100),\n"
                "MedicalCondition: VARCHAR(255),\n"
                "Medications: VARCHAR(255),\n"
                "Allergies: VARCHAR(255),\n"
                "BloodType: VARCHAR(10),\n"
                "LastVisitDate: DATE,\n"
                "SmokingStatus: VARCHAR(50),\n"
                "AlcoholConsumption: VARCHAR(50),\n"
                "ExerciseFrequency: VARCHAR(50),\n"
                "Occupation: VARCHAR(100),\n"
                "Height_cm: DECIMAL(5,2),\n"
                "Weight_kg: DECIMAL(5,2),\n"
                "BloodPressure: VARCHAR(20),\n"
                "HeartRate_bpm: INT,\n"
                "Temperature_C: DECIMAL(3,1),\n"
                "Notes: VARCHAR(MAX)\n\n"
                "Generate and execute a safe SQL query based on the user's natural language request."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A valid SQL query to run against the PatientMedicalData table."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_acc_guidelines",
            "description": "Query the ACC guidelines for official cardiology recommendations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The cardiology-related question or keywords."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_bing",
            "description": "Perform a public web search for real-time or external information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "General query to retrieve public data."
                    }
                },
                "required": ["query"]
            }
        }
    }
]

# ----------------------------
# System Prompt for the Agent
# ----------------------------
SYSTEM_PROMPT = (
    "You are a cardiology-focused AI assistant with access to three tools:\n"
    "1) 'lookup_patient_data' for querying patient records from Azure SQL.\n"
    "2) 'search_acc_guidelines' for official ACC guidelines.\n"
    "3) 'search_bing' for real-time public information.\n\n"
    "You can call these tools in any order, multiple times if needed, to gather all the context.\n"
    "Stop calling tools only when you have enough information to provide a final, cohesive answer.\n"
    "Then output your final answer to the user."
)

# ----------------------------
# Agent Logic (Multi-Step)
# ----------------------------
async def run_multi_step_agent(user_query: str, max_steps: int = 10):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_query}
    ]
    
    for step in range(max_steps):
        response = openai_client.chat.completions.create(
            model=AZURE_OPENAI_CHAT_COMPLETION_DEPLOYED_MODEL_NAME,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        response_message = response.choices[0].message

        # IMPORTANT: Append the assistant's message (which includes tool_calls) to the conversation.
        messages.append(response_message)
        
        if response_message.tool_calls:
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                try:
                    function_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    await cl.Message(
                        content=f"Warning: Could not decode tool call arguments; error: {e}. Using fallback value.",
                        author="Agent",
                    ).send()
                    function_args = {"query": user_query}
                
                await cl.Message(
                    content=f"Step {step+1}: Tool call: {function_name}\nArguments: {json.dumps(function_args, indent=2)}",
                    author="Agent",
                ).send()

                if function_name == "lookup_patient_data":
                    tool_output = lookup_patient_data(**function_args)
                elif function_name == "search_acc_guidelines":
                    tool_output = search_acc_guidelines(**function_args)
                elif function_name == "search_bing":
                    tool_output = search_bing(**function_args)
                else:
                    tool_output = f"[Error] No implementation for function '{function_name}'."
                
                # Append the tool's response with the required tool_call_id.
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": tool_output,
                })
        else:
            final_answer = response_message.content
            await cl.Message(
                content=final_answer,
                author="Agent",
            ).send()
            return

    await cl.Message(
        content="Max steps reached without a final answer. Stopping.",
        author="Agent",
    ).send()
    return

# ----------------------------
# Chainlit Event Handlers
# ----------------------------
@cl.on_chat_start
async def start_chat():
    await cl.Message(
        content="Hello! I am a cardiology-focused AI assistant. Ask me anything about cardiology guidelines or patient data."
    ).send()

@cl.on_message
async def main(message: cl.Message):
    await run_multi_step_agent(message.content)

if __name__ == "__main__":
    cl.run()
