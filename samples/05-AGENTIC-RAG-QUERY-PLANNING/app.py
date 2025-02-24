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
from chainlit import Step, Starter

load_dotenv()

# ----------------------------
# Configuration
# ----------------------------
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "your-azure-openai-api-key")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
AZURE_OPENAI_ENDPOINT = os.getenv(
    "AZURE_OPENAI_ENDPOINT", "https://your-azure-openai-endpoint.openai.azure.com/"
)
AZURE_OPENAI_CHAT_COMPLETION_DEPLOYED_MODEL_NAME = os.getenv("gpt-4o", "gpt-4o-mini")

AZURE_SEARCH_ENDPOINT = os.getenv(
    "AZURE_SEARCH_SERVICE_ENDPOINT", "https://your-search-service.search.windows.net"
)
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_ADMIN_KEY", "your-azure-search-key")
SEARCH_INDEX_NAME = "acc-guidelines-index"

BING_SEARCH_API_KEY = os.getenv("BING_SEARCH_API_KEY", "<YOUR-BING-SEARCH-KEY>")
BING_SEARCH_ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"

server = os.getenv("AZURE_SQL_SERVER_NAME")
database = os.getenv("AZURE_SQL_DATABASE_NAME")
username = os.getenv("AZURE_SQL_USER_NAME")
password = os.getenv("AZURE_SQL_PASSWORD")
driver = "{ODBC Driver 17 for SQL Server}"

AZURE_SQL_CONNECTION_STRING = (
    f"DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}"
)

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
                fields="embedding",  # Adjust based on your index schema
            )
        ],
        query_type="semantic",
        semantic_configuration_name="default",
        search_fields=["chunk"],
        top=10,
        include_total_count=True,
    )
    retrieved_texts = [result.get("chunk", "") for result in results]
    context_str = (
        "\n".join(retrieved_texts)
        if retrieved_texts
        else "No relevant guidelines found."
    )
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
                        "description": "A valid SQL query to run against the PatientMedicalData table.",
                    }
                },
                "required": ["query"],
            },
        },
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
                        "description": "The cardiology-related question or keywords.",
                    }
                },
                "required": ["query"],
            },
        },
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
                        "description": "General query to retrieve public data.",
                    }
                },
                "required": ["query"],
            },
        },
    },
]
tool_implementations = {
    "lookup_patient_data": lookup_patient_data,
    "search_acc_guidelines": search_acc_guidelines,
    "search_bing": search_bing,
}


# ----------------------------
# Chainlit Step for Tool Execution
# ----------------------------
# Replace the existing execute_tool step with three separate steps.
@cl.step(name="NL2SQL Tool", type="tool")
async def lookup_patient_data_step(function_args: dict):
    """
    Execute the lookup_patient_data tool as a Chainlit step.
    """
    return lookup_patient_data(**function_args)


@cl.step(name="Azure AI Search Knowledge Retrieval Tool", type="tool")
async def search_acc_guidelines_step(function_args: dict):
    """
    Execute the search_acc_guidelines tool as a Chainlit step.
    """
    return search_acc_guidelines(**function_args)


@cl.step(name="Bing Web Search Tool", type="tool")
async def search_bing_step(function_args: dict):
    """
    Execute the search_bing tool as a Chainlit step.
    """
    return search_bing(**function_args)


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
# The Multi-Step Agent using Steps
# ----------------------------
async def run_multi_step_agent(user_query: str, max_steps: int = 5):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_query},
    ]

    for step_num in range(max_steps):
        response = openai_client.chat.completions.create(
            model=AZURE_OPENAI_CHAT_COMPLETION_DEPLOYED_MODEL_NAME,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        response_message = response.choices[0].message

        # Add the assistant response to the conversation so that a tool response can follow
        messages.append(response_message)

        if response_message.tool_calls:
            # We might have multiple tool calls in one message
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                raw_args = tool_call.function.arguments

                try:
                    function_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    function_args = {"query": user_query}

                # Call the appropriate Chainlit step depending on the tool function name.
                if function_name == "lookup_patient_data":
                    tool_output = await lookup_patient_data_step(
                        function_args=function_args
                    )
                elif function_name == "search_acc_guidelines":
                    tool_output = await search_acc_guidelines_step(
                        function_args=function_args
                    )
                elif function_name == "search_bing":
                    tool_output = await search_bing_step(function_args=function_args)
                else:
                    tool_output = (
                        f"[Error] No implementation for function '{function_name}'."
                    )

                # Now add the tool's response to the conversation using the function name.
                messages.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": tool_output,
                    }
                )

        else:
            # The model returned a final answer
            final_answer = response_message.content
            await cl.Message(content=final_answer, author="Agent").send()
            return

    # If we reach here, we never got a final answer
    await cl.Message(
        content="Max steps reached without a final answer. Stopping.", author="Agent"
    ).send()


# ----------------------------
# Chainlit Starters
# ----------------------------
@cl.set_starters
async def set_starters():
    return [
        Starter(
            label="💊 How many patients have Hypertension and are prescribed Lisinopril? (NL2SQL)",
            message=(
                "How many patients have Hypertension and are prescribed Lisinopril?"
            ),
        ),
        Starter(
            label="❓ As of Feb 2025, new anticoagulant therapies from the FDA? (BING SEARCH)",
            message="Are there any recent updates in 2025 on new anticoagulant therapies from the FDA?",
        ),
        Starter(
            label="❤️ American College of Cardiology guidelines for hypertension (AZURE AI SEARCH)",
            message="What does the ACC recommend as first-line therapy for hypertension in elderly patients?",
        ),
        Starter(
            label="👵 Mega Query for 79-Year-Old Gloria Paul with hyperlipidemia (AGENTIC SEARCH)",
            message="I have a 79-year-old patient named Gloria Paul with hyperlipidemia. She's on Atorvastatin. Can you confirm her medical details from the database, check the ACC guidelines for hyperlipidemia, and see if there are any new medication updates from the FDA as of Feb 2025? Then give me a summary.",
        ),
    ]


# ----------------------------
# Chainlit Event Handlers
# ----------------------------
# @cl.on_chat_start
# async def start_chat():
#     await cl.Message(content="Hello! I am a cardiology-focused AI assistant. Ask me anything about cardiology guidelines or patient data.").send()


@cl.on_message
async def main(message: cl.Message):
    await run_multi_step_agent(message.content)
