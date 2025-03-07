import os
import json
import pandas as pd
import pyodbc
import sqlalchemy
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import BingGroundingTool
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery
from dotenv import load_dotenv
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
AZURE_OPENAI_CHAT_COMPLETION_DEPLOYED_MODEL_NAME = os.getenv(
    "AZURE_OPENAI_CHAT_COMPLETION_DEPLOYED_MODEL_NAME", "gpt-4o"
)

AZURE_SEARCH_ENDPOINT = os.getenv(
    "AZURE_SEARCH_SERVICE_ENDPOINT", "https://your-search-service.search.windows.net"
)
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_ADMIN_KEY", "your-azure-search-key")
SEARCH_INDEX_NAME = "acc-guidelines-index"

# Azure AI Project configuration
AZURE_CONNECTION_STRING = os.getenv(
    "AZURE_CONNECTION_STRING", "your-azure-connection-string"
)
BING_CONNECTION_NAME = os.getenv("BING_CONNECTION_NAME", "fsunavalabinggrounding")

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


def search_bing_grounding(query: str) -> str:
    """
    Searches the public web using the Bing Web Grounding Tool via Azure AI Agent Service.
    Returns information about recent updates from the web.
    """
    # Create an Azure AI Client
    project_client = AIProjectClient.from_connection_string(
        credential=DefaultAzureCredential(),
        conn_str=AZURE_CONNECTION_STRING,
    )

    try:
        with project_client:
            # Get the Bing connection
            bing_connection = project_client.connections.get(
                connection_name=BING_CONNECTION_NAME
            )
            conn_id = bing_connection.id

            # Initialize agent bing tool
            bing = BingGroundingTool(connection_id=conn_id)

            # Create agent with the bing tool
            agent = project_client.agents.create_agent(
                model="gpt-4o",  # NOTE, GPT-4o-mini cannot be used with Bing Grounding Tool
                name="bing-search-agent",
                instructions=f"Search the web for information about: {query}. Provide a concise but comprehensive summary.",
                tools=bing.definitions,
                headers={"x-ms-enable-preview": "true"},
            )

            # Create thread for communication
            thread = project_client.agents.create_thread()

            # Create message to thread
            project_client.agents.create_message(
                thread_id=thread.id,
                role="user",
                content=query,
            )

            # Create and process agent run
            run = project_client.agents.create_and_process_run(
                thread_id=thread.id, assistant_id=agent.id
            )

            if run.status == "failed":
                result_text = f"Bing search failed: {run.last_error}"
            else:
                # Fetch messages to get the response
                messages = project_client.agents.list_messages(thread_id=thread.id)

                # Extract the actual message text - FIXED EXTRACTION LOGIC
                for msg in messages.data:  # Use .data to access the list of messages
                    if msg.role == "assistant" and msg.content:
                        # Extract the text value from the content
                        for content_item in msg.content:
                            if content_item.type == "text":
                                return content_item.text.value  # Return the actual text

                result_text = "No specific information found."

            # Clean up resources
            project_client.agents.delete_agent(agent.id)

    except Exception as e:
        result_text = f"Bing search failed with error: {str(e)}"

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
            "name": "search_bing_grounding",
            "description": "Perform a public web search for real-time or external information using Bing Grounding.",
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
    "search_bing_grounding": search_bing_grounding,
}


# ----------------------------
# Chainlit Step for Tool Execution
# ----------------------------
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


@cl.step(name="Bing Web Grounding Tool", type="tool")
async def search_bing_grounding_step(function_args: dict):
    """
    Execute the search_bing_grounding tool as a Chainlit step.
    """
    return search_bing_grounding(**function_args)


# ----------------------------
# System Prompt for the Agent
# ----------------------------
SYSTEM_PROMPT = (
    "You are a cardiology-focused AI assistant with access to three tools:\n"
    "1) 'lookup_patient_data' for querying patient records from Azure SQL.\n"
    "2) 'search_acc_guidelines' for official ACC guidelines.\n"
    "3) 'search_bing_grounding' for real-time public information using Bing Grounding.\n\n"
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

        # FIXED: Properly format the assistant message with tool calls
        if response_message.tool_calls:
            # Add the assistant message with proper structure for tool calls
            messages.append(
                {
                    "role": "assistant",
                    "content": response_message.content,  # This might be None when tool_calls are present
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                        for tool_call in response_message.tool_calls
                    ],
                }
            )

            # We might have multiple tool calls in one message
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                tool_call_id = tool_call.id  # Extract the exact tool_call_id
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
                elif function_name == "search_bing_grounding":
                    tool_output = await search_bing_grounding_step(
                        function_args=function_args
                    )
                else:
                    tool_output = (
                        f"[Error] No implementation for function '{function_name}'."
                    )

                # Now add the tool's response to the conversation as a string
                # FIXED: Use the exact tool_call_id
                messages.append(
                    {
                        "tool_call_id": tool_call_id,
                        "role": "tool",
                        "name": function_name,
                        "content": str(tool_output),
                    }
                )
        else:
            # The model returned a final answer - no tool calls
            messages.append({"role": "assistant", "content": response_message.content})

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
            label="❓ As of Feb 2025, new anticoagulant therapies from the FDA? (BING GROUNDING)",
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
#     await cl.Message(
#         content="Hello! I am a cardiology-focused AI assistant with access to patient data, ACC guidelines, and real-time web information through Bing Grounding. How can I help you today?"
#     ).send()


@cl.on_message
async def main(message: cl.Message):
    await run_multi_step_agent(message.content)
