import os
import asyncio
import chainlit as cl
from dotenv import load_dotenv
from azure.identity import AzureCliCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import AzureAISearchTool

# Load environment variables from .env file (if available)
load_dotenv()

# Retrieve configuration from environment variables
CONNECTION_STRING = os.getenv("AZURE_CONNECTION_STRING")
SEARCH_CONNECTION_NAME = os.getenv("AI_SEARCH_CONNECTION_NAME")
SEARCH_INDEX_NAME = os.getenv("AI_SEARCH_INDEX_NAME", "azure-search-docs")

if CONNECTION_STRING is None:
    raise ValueError("AZURE_CONNECTION_STRING is not set. Please set this environment variable.")

# Create the Azure AI Projects client
client = AIProjectClient.from_connection_string(
    credential=AzureCliCredential(),
    conn_str=CONNECTION_STRING,
)

def initialize_agent_and_thread():
    """
    Initializes the search tool, creates an agent, and a new conversation thread.
    Stores the agent and thread IDs in the Chainlit session.
    """
    # Enumerate connections and find the one matching SEARCH_CONNECTION_NAME
    connections = client.connections.list()
    conn_id = next(c.id for c in connections if c.name == SEARCH_CONNECTION_NAME)

    # Initialize the Azure AI Search tool with the selected connection and index name.
    search_tool = AzureAISearchTool(
        index_connection_id=conn_id,
        index_name=SEARCH_INDEX_NAME,
    )

    # Create the agent using the specified model and instructions.
    agent = client.agents.create_agent(
        model="gpt-4o-mini",  # Adjust if necessary.
        name="my-assistant",
        instructions="You are a helpful assistant.",
        tools=search_tool.definitions,
        tool_resources=search_tool.resources,
    )

    # Create a new conversation thread.
    thread = client.agents.create_thread()

    # Store agent and thread IDs for later use in the session.
    cl.user_session.set("agent_id", agent.id)
    cl.user_session.set("thread_id", thread.id)

    return agent, thread

def process_query(query: str) -> str:
    """
    Sends the user query to the agent and retrieves the assistant's reply.
    """
    thread_id = cl.user_session.get("thread_id")
    agent_id = cl.user_session.get("agent_id")

    # Create a message with the user's query.
    client.agents.create_message(
        thread_id=thread_id,
        role="user",
        content=query,
    )

    # Process the conversation run (synchronously).
    client.agents.create_and_process_run(
        thread_id=thread_id,
        assistant_id=agent_id,
    )

    # Retrieve all messages from the conversation thread.
    messages = client.agents.list_messages(thread_id=thread_id)
    assistant_replies = [m for m in messages.data if m.role == "assistant"]

    if assistant_replies:
        # Return the text content of the latest assistant reply.
        return assistant_replies[-1].content[0].text.value
    return "I'm sorry, I didn't receive a response."

@cl.on_chat_start
async def on_chat_start():
    """
    Chainlit hook that initializes the agent and thread when the chat starts.
    """
    # Run the synchronous initialization in a separate thread.
    await asyncio.to_thread(initialize_agent_and_thread)
    await cl.Message(content="Welcome! Ask your question about Azure Search.").send()

@cl.on_message
async def on_message(message: cl.Message):
    """
    Chainlit hook to process each user message:
      - Runs the synchronous query processing in a separate thread.
      - Streams the assistant's reply back to the UI.
    """
    query = message.content
    response_text = await asyncio.to_thread(lambda: process_query(query))
    await cl.Message(content=response_text).send()
