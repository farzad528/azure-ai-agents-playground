# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

"""
DESCRIPTION:
    This app demonstrates how to use Azure AI Search as a 'MemoryTool' with 
    Azure Agent Service, leveraging the Tool Function Calling lifecycle with
    structured output via Pydantic models, presented in a Streamlit UI.

USAGE:
    streamlit run app.py

    Before running the sample:

    pip install azure-ai-projects azure-identity azure-search-documents pydantic streamlit

    Set these environment variables with your own values:
    1) AZURE_CONNECTION_STRING - The project connection string
    2) AZURE_SEARCH_SERVICE_ENDPOINT - The endpoint of your Azure Search service
    3) AZURE_SEARCH_ADMIN_KEY - The admin key for your Azure Search service
"""

import os
import json
import time
import uuid
import re
import streamlit as st
from datetime import datetime, UTC
from typing import List, Dict, Any, Optional, Union, Set, Callable
from enum import Enum
from pydantic import BaseModel, Field
import threading

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    FunctionTool,
    ToolSet,
    RequiredFunctionToolCall,
    SubmitToolOutputsAction,
    ToolOutput,
    RunStatus,
    ResponseFormatJsonSchema,
    ResponseFormatJsonSchemaType,
)
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
)
from azure.core.credentials import AzureKeyCredential

# Configuration
def get_config():
    return {
        "AZURE_CONNECTION_STRING": os.getenv("AZURE_CONNECTION_STRING"),
        "AZURE_SEARCH_ENDPOINT": os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT"),
        "AZURE_SEARCH_ADMIN_KEY": os.getenv("AZURE_SEARCH_ADMIN_KEY"),
        "MEMORY_INDEX_NAME": "fact-memory-index",
    }

# Initialize session state
def init_session_state():
    """Initialize session state variables"""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "memory_ops" not in st.session_state:
        st.session_state.memory_ops = []
        
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = None
        
    if "agent_id" not in st.session_state:
        st.session_state.agent_id = None
        
    if "debug_mode" not in st.session_state:
        st.session_state.debug_mode = True
        
    if "initialized" not in st.session_state:
        st.session_state.initialized = False
        
    if "run_active" not in st.session_state:
        st.session_state.run_active = False
        
    if "show_facts" not in st.session_state:
        st.session_state.show_facts = False
        
    if "show_retrievals" not in st.session_state:
        st.session_state.show_retrievals = False
        
    if "inline_ops_toggle" not in st.session_state:
        st.session_state.inline_ops_toggle = True

# Initialize clients
@st.cache_resource
def initialize_clients():
    config = get_config()
    
    search_client = SearchClient(
        endpoint=config["AZURE_SEARCH_ENDPOINT"],
        index_name=config["MEMORY_INDEX_NAME"],
        credential=AzureKeyCredential(config["AZURE_SEARCH_ADMIN_KEY"]),
    )

    projects_client = AIProjectClient.from_connection_string(
        credential=DefaultAzureCredential(),
        conn_str=config["AZURE_CONNECTION_STRING"],
    )
    
    return search_client, projects_client

# Define Pydantic models for structured outputs
class FactType(str, Enum):
    PERSONAL = "personal"
    PREFERENCE = "preference"
    PLAN = "plan"
    CONTACT = "contact"
    WORK = "work"
    OTHER = "other"

class Fact(BaseModel):
    content: str = Field(..., description="The fact content")
    fact_type: FactType = Field(..., description="The type of fact")
    confidence: float = Field(
        ..., description="Confidence score for this fact (0.0-1.0)", ge=0.0, le=1.0
    )

class FactExtraction(BaseModel):
    facts: List[Fact] = Field(..., description="List of extracted facts")

# Helper function to properly extract text from messages
def extract_text(content):
    """
    Extract clean text from various message formats.
    Handles all observed formats in the console output.
    """
    # Handle string content
    if isinstance(content, str):
        return content

    # Handle dict with nested structure - most common format from output
    if isinstance(content, dict):
        # Check for the structure {'type': 'text', 'text': {'value': "..."}}
        if content.get("type") == "text" and isinstance(content.get("text"), dict):
            return content["text"].get("value", "")

        # Check for other nested structures
        if "text" in content:
            if isinstance(content["text"], dict) and "value" in content["text"]:
                return content["text"]["value"]
            return str(content["text"])
        elif "value" in content:
            return str(content["value"])

    # Handle list content
    if isinstance(content, list) and len(content) > 0:
        # Recursively extract from first item if it's a list
        return extract_text(content[0])

    # Default fallback
    return str(content)

# Ensure memory index exists
def ensure_memory_index_exists():
    """Create or update the memory index if it doesn't exist"""
    try:
        config = get_config()
        # Initialize the search index client
        index_client = SearchIndexClient(
            endpoint=config["AZURE_SEARCH_ENDPOINT"],
            credential=AzureKeyCredential(config["AZURE_SEARCH_ADMIN_KEY"]),
        )

        # Check if index exists
        index_exists = False
        try:
            index_info = index_client.get_index(name=config["MEMORY_INDEX_NAME"])
            index_exists = True
            add_log(f"✅ Memory index '{config['MEMORY_INDEX_NAME']}' already exists", "system")
        except:
            add_log(f"🔧 Creating memory index '{config['MEMORY_INDEX_NAME']}'...", "system")

        # If index doesn't exist, create it
        if not index_exists:
            # Define the index fields
            fields = [
                SimpleField(name="id", type=SearchFieldDataType.String, key=True),
                SearchableField(name="content", type=SearchFieldDataType.String),
                SimpleField(
                    name="thread_id", type=SearchFieldDataType.String, filterable=True
                ),
                SimpleField(
                    name="fact_type", type=SearchFieldDataType.String, filterable=True
                ),
                SimpleField(
                    name="confidence", type=SearchFieldDataType.Double, filterable=True
                ),
                SimpleField(
                    name="timestamp",
                    type=SearchFieldDataType.DateTimeOffset,
                    filterable=True,
                    sortable=True,
                ),
            ]

            # Create the index definition
            index = SearchIndex(name=config["MEMORY_INDEX_NAME"], fields=fields)

            # Create the index
            index_client.create_or_update_index(index)

            add_log(f"✅ Created memory index '{config['MEMORY_INDEX_NAME']}'", "system")

        # Test search client connection
        search_client, _ = initialize_clients()
        add_log(f"✅ Testing search client connection...", "system")
        try:
            test_result = search_client.search(search_text="*", top=1)
            list(test_result)  # Force evaluation
            add_log(f"✅ Search client connection verified", "system")
        except Exception as e:
            add_log(f"❌ ERROR with search client: {e}", "error")

        return True
    except Exception as e:
        add_log(f"❌ ERROR creating memory index: {e}", "error")
        return False

# Add log message to the UI
def add_log(message, log_type="info", additional_data=None):
    timestamp = datetime.now()
    formatted_time = timestamp.strftime("%H:%M:%S")
    log_entry = {
        "message": message, 
        "type": log_type, 
        "timestamp": timestamp,
        "formatted_time": formatted_time
    }
    
    # Add any additional data (like retrieved memories)
    if additional_data:
        log_entry["additional_data"] = additional_data
        
    st.session_state.memory_ops.append(log_entry)

# Define memory management functions for agent
def create_memory_functions():
    """Define memory management functions"""
    search_client, _ = initialize_clients()

    # CREATE memory function
    def store_memory_func(thread_id, content, fact_type="other", confidence=1.0):
        """Store a new fact in memory"""
        try:
            if st.session_state.debug_mode:
                add_log(f"🛠️ Tool called: store_memory_func", "debug")
                add_log(f"  - Thread ID: {thread_id}", "debug")
                add_log(
                    f"  - Content: {content[:50]}..."
                    if len(content) > 50
                    else f"  - Content: {content}",
                    "debug"
                )
                add_log(f"  - Fact type: {fact_type}", "debug")
                add_log(f"  - Confidence: {confidence}", "debug")

            # Always use the correct thread_id
            if st.session_state.thread_id and thread_id != st.session_state.thread_id:
                if st.session_state.debug_mode:
                    add_log(
                        f"⚠️ Thread ID mismatch! Using {st.session_state.thread_id} instead of {thread_id}",
                        "warning"
                    )
                thread_id = st.session_state.thread_id

            doc_id = str(uuid.uuid4())
            doc = {
                "id": doc_id,
                "thread_id": thread_id,
                "content": content,
                "fact_type": fact_type,
                "confidence": confidence,
                "timestamp": datetime.now(UTC),
            }

            result = search_client.upload_documents([doc])

            if st.session_state.debug_mode:
                add_log(
                    f"💾 STORED: [fact] {content[:50]}..."
                    if len(content) > 50
                    else f"💾 STORED: [fact] {content}",
                    "memory"
                )

            return json.dumps({"id": doc_id, "status": "success"})
        except Exception as e:
            if st.session_state.debug_mode:
                add_log(f"❌ ERROR storing fact: {e}", "error")
            return json.dumps({"error": str(e)})

    # READ memory function
    def retrieve_memories_func(
        thread_id, query="", limit=3, min_confidence=0.0
    ):
        """Retrieve relevant facts from memory"""
        try:
            if st.session_state.debug_mode:
                add_log(f"🛠️ Tool called: retrieve_memories_func", "debug")
                add_log(f"  - Thread ID: {thread_id}", "debug")
                add_log(f"  - Query: '{query}'", "debug")
                add_log(f"  - Limit: {limit}", "debug")
                add_log(f"  - Min confidence: {min_confidence}", "debug")

            # Always use the correct thread_id
            if st.session_state.thread_id and thread_id != st.session_state.thread_id:
                if st.session_state.debug_mode:
                    add_log(
                        f"⚠️ Thread ID mismatch! Using {st.session_state.thread_id} instead of {thread_id}",
                        "warning"
                    )
                thread_id = st.session_state.thread_id

            filter_expr = f"thread_id eq '{thread_id}' and confidence ge {min_confidence}"

            if query:
                # Semantic search with filter
                results = search_client.search(
                    search_text=query,
                    filter=filter_expr,
                    top=limit,
                    select="id,content,fact_type,confidence,timestamp",
                )
                if st.session_state.debug_mode:
                    add_log(f"🔍 Retrieving memories for query: '{query}'", "memory")
            else:
                # Get most recent facts
                results = search_client.search(
                    search_text="*",
                    filter=filter_expr,
                    top=limit,
                    order_by="timestamp desc",
                    select="id,content,fact_type,confidence,timestamp",
                )
                if st.session_state.debug_mode:
                    add_log(f"🔍 Retrieving {limit} most recent memories", "memory")

            memories = []
            for r in results:
                memories.append(
                    {
                        "id": r.get("id", ""),
                        "content": r.get("content", ""),
                        "fact_type": r.get("fact_type", "other"),
                        "confidence": r.get("confidence", 1.0),
                    }
                )

            if st.session_state.debug_mode and memories:
                add_log(f"🔍 Retrieved {len(memories)} memories", "memory")

            return json.dumps({"memories": memories, "count": len(memories)})
        except Exception as e:
            if st.session_state.debug_mode:
                add_log(f"❌ ERROR retrieving memories: {e}", "error")
            return json.dumps({"error": str(e)})

    # UPDATE memory function
    def update_memory_func(
        thread_id, memory_id, new_content, fact_type=None, confidence=None
    ):
        """Update an existing fact in memory"""
        try:
            if st.session_state.debug_mode:
                add_log(f"🛠️ Tool called: update_memory_func", "debug")
                add_log(f"  - Thread ID: {thread_id}", "debug")
                add_log(f"  - Memory ID: {memory_id}", "debug")
                add_log(
                    f"  - New content: {new_content[:50]}..."
                    if len(new_content) > 50
                    else f"  - New content: {new_content}",
                    "debug"
                )

            # Always use the correct thread_id
            if st.session_state.thread_id and thread_id != st.session_state.thread_id:
                if st.session_state.debug_mode:
                    add_log(
                        f"⚠️ Thread ID mismatch! Using {st.session_state.thread_id} instead of {thread_id}",
                        "warning"
                    )
                thread_id = st.session_state.thread_id

            # First retrieve the existing document
            try:
                existing_doc = search_client.get_document(key=memory_id)
            except Exception as e:
                if st.session_state.debug_mode:
                    add_log(f"❌ ERROR retrieving document for update: {e}", "error")
                return json.dumps({"error": f"Document with ID {memory_id} not found"})

            # Prepare the updated document
            doc = {
                "id": memory_id,
                "thread_id": thread_id,
                "content": new_content,
                "fact_type": fact_type or existing_doc.get("fact_type", "other"),
                "confidence": confidence or existing_doc.get("confidence", 1.0),
                "timestamp": datetime.now(UTC),
            }

            # Update the document
            result = search_client.merge_documents([doc])

            if st.session_state.debug_mode:
                add_log(
                    f"✏️ UPDATED: [fact] {new_content[:50]}..."
                    if len(new_content) > 50
                    else f"✏️ UPDATED: [fact] {new_content}",
                    "memory"
                )

            return json.dumps({"id": memory_id, "status": "updated"})
        except Exception as e:
            if st.session_state.debug_mode:
                add_log(f"❌ ERROR updating memory: {e}", "error")
            return json.dumps({"error": str(e)})

    # DELETE memory function
    def delete_memory_func(memory_id):
        """Delete a fact from memory"""
        try:
            if st.session_state.debug_mode:
                add_log(f"🛠️ Tool called: delete_memory_func", "debug")
                add_log(f"  - Memory ID: {memory_id}", "debug")

            # Delete the document
            search_client.delete_documents([{"id": memory_id}])

            if st.session_state.debug_mode:
                add_log(f"🗑️ DELETED: [fact] {memory_id}", "memory")

            return json.dumps({"id": memory_id, "status": "deleted"})
        except Exception as e:
            if st.session_state.debug_mode:
                add_log(f"❌ ERROR deleting memory: {e}", "error")
            return json.dumps({"error": str(e)})

    return {
        store_memory_func,
        retrieve_memories_func,
        update_memory_func,
        delete_memory_func,
    }

# Log memory operations (always visible regardless of debug_mode)
def log_memory_operation(operation, details=None, additional_data=None):
    """Log memory operations with prominent visibility"""
    if operation == "store":
        add_log(f"📝 MEMORY STORED: {details}", "memory_highlight")
    elif operation == "retrieve":
        if isinstance(details, int):
            add_log(f"🔍 MEMORIES RETRIEVED: {details} fact(s)", "memory_highlight", additional_data)
        else:
            add_log(f"🔍 MEMORIES RETRIEVED: {details}", "memory_highlight", additional_data)
    elif operation == "update":
        add_log(f"✏️ MEMORY UPDATED: {details}", "memory_highlight")
    elif operation == "delete":
        add_log(f"🗑️ MEMORY DELETED: ID {details}", "memory_highlight")
    else:
        add_log(f"📊 MEMORY OPERATION [{operation}]: {details}", "memory_highlight")

# Process function calls from the agent
def process_function_calls(thread_id, run_id, tool_calls):
    """Process function calls from the agent and submit tool outputs"""
    try:
        memory_functions = create_memory_functions()
        function_tool = FunctionTool(memory_functions)
        _, projects_client = initialize_clients()

        tool_outputs = []
        memory_ops_summary = []
        
        for tool_call in tool_calls:
            if isinstance(tool_call, RequiredFunctionToolCall):
                try:
                    function_name = tool_call.function.name
                    arguments = tool_call.function.arguments
                    
                    # Always show when memory functions are called (regardless of debug_mode)
                    if function_name == "store_memory_func":
                        args = json.loads(arguments)
                        content = args.get("content", "")
                        fact_type = args.get("fact_type", "other")
                        log_memory_operation("store", f"[{fact_type}] {content[:100]}" + ("..." if len(content) > 100 else ""))
                        memory_ops_summary.append("stored new fact")
                    
                    elif function_name == "retrieve_memories_func":
                        args = json.loads(arguments)
                        query = args.get("query", "")
                        if query:
                            log_memory_operation("retrieve", f"Query: '{query}'")
                        else:
                            log_memory_operation("retrieve", "Recent facts")
                        memory_ops_summary.append("retrieved facts")
                    
                    elif function_name == "update_memory_func":
                        args = json.loads(arguments)
                        memory_id = args.get("memory_id", "")
                        new_content = args.get("new_content", "")
                        log_memory_operation("update", f"ID {memory_id[:8]}... - {new_content[:100]}" + ("..." if len(new_content) > 100 else ""))
                        memory_ops_summary.append("updated fact")
                    
                    elif function_name == "delete_memory_func":
                        args = json.loads(arguments)
                        memory_id = args.get("memory_id", "")
                        log_memory_operation("delete", memory_id)
                        memory_ops_summary.append("deleted fact")
                    
                    if st.session_state.debug_mode:
                        add_log(f"🛠️ Processing tool call: {function_name}", "debug")
                        add_log(f"  - Arguments: {arguments}", "debug")

                    # Execute the function
                    output = function_tool.execute(tool_call)
                    
                    # For retrieve_memories_func, show how many memories were retrieved
                    if function_name == "retrieve_memories_func":
                        try:
                            result = json.loads(output)
                            args = json.loads(arguments)
                            query = args.get("query", "")
                            
                            if "memories" in result and "count" in result:
                                memories = result["memories"]
                                count = result["count"]
                                
                                # Create a structured representation of retrieved memories
                                retrieved_memories = {
                                    "query": query if query else "recent facts",
                                    "count": count,
                                    "memories": memories
                                }
                                
                                # Log the retrieval operation with the full memory data
                                if query:
                                    log_message = f"{count} fact(s) returned for query: '{query}'"
                                else:
                                    log_message = f"{count} recent fact(s) returned"
                                    
                                log_memory_operation("retrieve", log_message, retrieved_memories)
                                
                                # Also log individual memories for debug view
                                if count > 0:
                                    for i, memory in enumerate(memories):
                                        add_log(f"  {i+1}. [{memory.get('fact_type', 'other')}] {memory.get('content', '')}", "fact")
                        except Exception as e:
                            add_log(f"Error processing retrieved memories: {e}", "error")

                    tool_outputs.append(
                        ToolOutput(tool_call_id=tool_call.id, output=output)
                    )
                except Exception as e:
                    add_log(f"❌ Error executing tool call {tool_call.id}: {e}", "error")

        if tool_outputs:
            if st.session_state.debug_mode:
                add_log(f"📤 Submitting {len(tool_outputs)} tool outputs", "debug")

            projects_client.agents.submit_tool_outputs_to_run(
                thread_id=thread_id, run_id=run_id, tool_outputs=tool_outputs
            )
            
            if memory_ops_summary:
                add_log(f"📊 MEMORY OPERATIONS SUMMARY: {', '.join(memory_ops_summary)}", "summary")

        return len(tool_outputs)
    except Exception as e:
        add_log(f"❌ Error processing function calls: {e}", "error")
        return 0

# Create memory agent with function calling
def create_memory_agent():
    """Create agent with memory management functions"""
    _, projects_client = initialize_clients()

    # Initialize the memory functions
    memory_functions = create_memory_functions()

    # Create a function tool with the memory functions
    function_tool = FunctionTool(memory_functions)

    # Create agent with complete memory management instructions
    agent = projects_client.agents.create_agent(
        model="gpt-4o-mini",
        name=f"memory-agent-{uuid.uuid4().hex[:6]}",
        instructions="""You are an assistant with memory management capabilities.

IMPORTANT: At the start of each conversation, ALWAYS use retrieve_memories_func to check what you know about the user.

You have access to four memory management functions:
1. store_memory_func(thread_id, content, fact_type, confidence) - Store a new fact about the user
2. retrieve_memories_func(thread_id, query, limit, min_confidence) - Retrieve relevant facts
3. update_memory_func(thread_id, memory_id, new_content, fact_type, confidence) - Update an existing fact
4. delete_memory_func(memory_id) - Delete a fact that is no longer relevant

When interacting with users:
1. ALWAYS begin by retrieving and reviewing relevant memories using retrieve_memories_func
2. When users share important information about themselves, IMMEDIATELY store it using store_memory_func
3. If information needs updating, use update_memory_func to keep facts current
4. Use the fact_type parameter to categorize facts (personal, preference, plan, contact, work, other)
5. Use the confidence parameter (0.0-1.0) to indicate how certain you are about a fact

CRITICAL: The thread_id must ALWAYS be the EXACT thread_id that was provided to you. 
Never modify, shorten, or create your own thread_id. Always use the full thread_id exactly as given.

Examples of facts to store:
- Personal facts: "User's name is Alex", "User is 32 years old"
- Preferences: "User prefers vegetarian food", "User enjoys hiking"
- Plans: "User is planning a trip to Japan in June", "User has a meeting tomorrow"
- Work: "User works as a software engineer", "User is working on a data analysis project"

Be proactive in memory management - don't wait for explicit instructions to store facts.
NEVER mention the memory system to users - just naturally incorporate what you know.""",
        tools=function_tool.definitions,
    )

    add_log(f"🤖 Memory agent created with ID: {agent.id}", "system")
    return agent

# Start conversation with memory agent
def initialize_agent():
    """Initialize the memory agent and start a new conversation"""
    # Ensure memory index exists before proceeding
    if not ensure_memory_index_exists():
        add_log("❌ Failed to create or verify memory index. Exiting.", "error")
        return False
        
    # Create memory agent
    memory_agent = create_memory_agent()
    st.session_state.agent_id = memory_agent.id

    # Create a new thread
    _, projects_client = initialize_clients()
    thread = projects_client.agents.create_thread()
    st.session_state.thread_id = thread.id
    add_log(f"🆕 Started new conversation (Thread ID: {thread.id})", "system")
    
    st.session_state.initialized = True
    st.session_state.messages = []
    return True

# List all facts in memory
def list_all_facts():
    """List all facts stored for the current thread"""
    search_client, _ = initialize_clients()
    try:
        # Get all facts for this thread
        results = search_client.search(
            search_text="*",
            filter=f"thread_id eq '{st.session_state.thread_id}'",
            top=100,
            order_by="timestamp desc",
            select="id,content,fact_type,confidence,timestamp",
        )

        facts = list(results)

        if not facts:
            st.warning(f"No facts found for thread ID: {st.session_state.thread_id}")
            return []
        
        return facts
    except Exception as e:
        add_log(f"❌ ERROR listing facts: {e}", "error")
        return []

# Process user message and get response
def process_message(user_input):
    """Process user message and get assistant's response"""
    if not st.session_state.initialized:
        st.error("Agent not initialized. Please restart the application.")
        return
        
    if not user_input:
        st.warning("Input cannot be empty. Please try again.")
        return
        
    # Record the time this message was added
    current_time = datetime.now()
        
    # Special commands
    if user_input.lower() == "exit":
        st.session_state.initialized = False
        add_log("👋 Conversation ended", "system")
        return
        
    if user_input.lower() in ["facts", "list facts", "show facts"]:
        st.session_state.show_facts = True
        return
        
    if user_input.lower() == "memory on":
        st.session_state.debug_mode = True
        add_log("🔔 Memory operations will now be shown", "system")
        return
        
    if user_input.lower() == "memory off":
        st.session_state.debug_mode = False
        add_log("🔕 Memory operations will be hidden", "system")
        return

    # Mark that we have an active run
    st.session_state.run_active = True
        
    # Add user message to the UI with timestamp
    st.session_state.messages.append({"role": "user", "content": user_input, "timestamp": current_time})
    
    try:
        # Add message to thread
        _, projects_client = initialize_clients()
        projects_client.agents.create_message(
            thread_id=st.session_state.thread_id, role="user", content=user_input
        )

        add_log("⏳ Processing...", "system")

        # Create a run
        run = projects_client.agents.create_run(
            thread_id=st.session_state.thread_id, assistant_id=st.session_state.agent_id
        )

        # Process the run and handle any function calls
        while run.status in ["queued", "in_progress", "requires_action"]:
            time.sleep(0.5)
            run = projects_client.agents.get_run(thread_id=st.session_state.thread_id, run_id=run.id)

            add_log(f"🔄 Run status: {run.status}", "debug")

            if run.status == "requires_action" and isinstance(run.required_action, SubmitToolOutputsAction):
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                if tool_calls:
                    process_function_calls(st.session_state.thread_id, run.id, tool_calls)

        if run.status != RunStatus.COMPLETED:
            add_log(f"❌ Run completed with non-success status: {run.status}", "error")

        # Get assistant response
        messages = projects_client.agents.list_messages(thread_id=st.session_state.thread_id)
        latest = None

        for msg in messages.data:
            if msg.role == "assistant" and (
                not latest or msg.created_at > latest.created_at
            ):
                latest = msg

        if latest:
            # Extract and display clean text
            response_text = extract_text(latest.content)
            
            # Check if response_text itself is a string representation of a dict
            if isinstance(response_text, str) and response_text.startswith("{") and "'value':" in response_text:
                try:
                    # Try to parse it as a dictionary-like string
                    import ast
                    parsed = ast.literal_eval(response_text)
                    if isinstance(parsed, dict) and 'text' in parsed and 'value' in parsed['text']:
                        response_text = parsed['text']['value']
                except:
                    # If parsing fails, keep the original text
                    pass
                    
            # Add message with timestamp
            current_time = datetime.now()
            st.session_state.messages.append({
                "role": "assistant", 
                "content": response_text,
                "timestamp": current_time
            })
            
            # Show summary of memory usage for this turn
            if run.required_action and isinstance(run.required_action, SubmitToolOutputsAction):
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                memory_ops = {
                    "retrieve": 0,
                    "store": 0,
                    "update": 0,
                    "delete": 0
                }
                
                for tool_call in tool_calls:
                    if isinstance(tool_call, RequiredFunctionToolCall):
                        if tool_call.function.name == "retrieve_memories_func":
                            memory_ops["retrieve"] += 1
                        elif tool_call.function.name == "store_memory_func":
                            memory_ops["store"] += 1
                        elif tool_call.function.name == "update_memory_func":
                            memory_ops["update"] += 1
                        elif tool_call.function.name == "delete_memory_func":
                            memory_ops["delete"] += 1
                
                # Show summary only if there were memory operations
                if sum(memory_ops.values()) > 0:
                    summary = []
                    if memory_ops["retrieve"] > 0:
                        summary.append(f"Retrieved facts: {memory_ops['retrieve']} time(s)")
                    if memory_ops["store"] > 0:
                        summary.append(f"Stored new facts: {memory_ops['store']} time(s)")
                    if memory_ops["update"] > 0:
                        summary.append(f"Updated facts: {memory_ops['update']} time(s)")
                    if memory_ops["delete"] > 0:
                        summary.append(f"Deleted facts: {memory_ops['delete']} time(s)")
                    
                    add_log(f"📊 MEMORY USAGE SUMMARY: {', '.join(summary)}", "summary")
        else:
            add_log("❌ No response received.", "error")

    except Exception as e:
        add_log(f"❌ Error: {e}", "error")
        import traceback
        add_log(traceback.format_exc(), "error")
    
    # Mark that the run is complete
    st.session_state.run_active = False

# Main function for Streamlit UI
def main():
    st.set_page_config(
        page_title="Memory Agent Demo",
        page_icon="🧠",
        layout="wide",
    )
    
    # Initialize session state
    init_session_state()
    
    # Page header
    st.title("🧠 Azure AI Memory Agent Demo")
    st.markdown("""
    This demo showcases how to use Azure AI Search as a memory store for AI agents.
    The agent will automatically remember information about you during the conversation.
    """)
    
    # Main interface with two columns
    if not st.session_state.initialized:
        # Show initialization button centered
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.write("## Initialize the Memory Agent to begin")
            if st.button("Initialize Memory Agent", use_container_width=True):
                with st.spinner("Initializing agent..."):
                    initialize_agent()
                    st.rerun()
    else:
        # Only render the conversation UI once initialization is complete
        col1, col2 = st.columns([3, 1])
        
        with col1:
            # Chat messages display
            st.subheader("Conversation")
            
            # Display chat messages with inline memory operations
            chat_container = st.container()
            with chat_container:
                for i, message in enumerate(st.session_state.messages):
                    # Display the message
                    with st.chat_message(message["role"]):
                        st.write(message["content"])
                    
                    # After assistant messages, show memory operations if they exist
                    if message["role"] == "assistant" and i > 0 and st.session_state.inline_ops_toggle:
                        # Get memory operations that occurred between this message and the previous one
                        if "timestamp" in message:
                            msg_time = message["timestamp"]
                            # Filter operations that happened just before this response
                            relevant_ops = [
                                op for op in st.session_state.memory_ops 
                                if "timestamp" in op and op["timestamp"] <= msg_time and 
                                (i == len(st.session_state.messages)-1 or 
                                 op["timestamp"] > st.session_state.messages[i-1].get("timestamp", ""))
                            ]
                            
                            if relevant_ops:
                                # Count operation types
                                op_counts = {"store": 0, "retrieve": 0, "update": 0, "delete": 0}
                                for op in relevant_ops:
                                    if "memory_highlight" in op.get("type", ""):
                                        op_type = op["message"].split()[1].lower() if len(op["message"].split()) > 1 else "other"
                                        if "stored" in op_type:
                                            op_counts["store"] += 1
                                        elif "retrieved" in op_type:
                                            op_counts["retrieve"] += 1
                                        elif "updated" in op_type:
                                            op_counts["update"] += 1
                                        elif "deleted" in op_type:
                                            op_counts["delete"] += 1
                                
                                # Show expandable memory operations
                                ops_summary = []
                                if op_counts["store"] > 0:
                                    ops_summary.append(f"Stored {op_counts['store']} fact(s)")
                                if op_counts["retrieve"] > 0:
                                    ops_summary.append(f"Retrieved {op_counts['retrieve']} fact(s)")
                                if op_counts["update"] > 0:
                                    ops_summary.append(f"Updated {op_counts['update']} fact(s)")
                                if op_counts["delete"] > 0:
                                    ops_summary.append(f"Deleted {op_counts['delete']} fact(s)")
                                
                                if ops_summary:
                                    # Determine if there are any retrievals to highlight
                                    has_retrievals = any("MEMORIES RETRIEVED" in op.get("message", "") for op in relevant_ops if "memory_highlight" in op.get("type", ""))
                                    
                                    with st.expander(f"🧠 Memory operations: {', '.join(ops_summary)}", expanded=has_retrievals):
                                        # First show retrieval operations with extra detail
                                        for op in relevant_ops:
                                            if "memory_highlight" in op.get("type", "") and "MEMORIES RETRIEVED" in op.get("message", ""):
                                                st.info(op["message"])
                                                
                                                # If this was a retrieval operation with memories, show them in detail
                                                if "additional_data" in op and "memories" in op["additional_data"]:
                                                    retrieval_data = op["additional_data"]
                                                    query = retrieval_data.get("query", "")
                                                    memories = retrieval_data.get("memories", [])
                                                    
                                                    # Show query used
                                                    if query:
                                                        st.caption(f"📊 Query: '{query}'")
                                                    else:
                                                        st.caption("📊 Retrieved most recent facts")
                                                    
                                                    # Display the actual memories that were retrieved
                                                    if memories:
                                                        st.markdown("##### Retrieved Memories:")
                                                        for i, memory in enumerate(memories):
                                                            fact_type = memory.get("fact_type", "other")
                                                            content = memory.get("content", "")
                                                            confidence = memory.get("confidence", 1.0)
                                                            st.markdown(f"**{i+1}. [{fact_type}]** {content} *(confidence: {confidence:.2f})*")
                                        
                                        # Then show other memory operations
                                        for op in relevant_ops:
                                            if "memory_highlight" in op.get("type", "") and "MEMORIES RETRIEVED" not in op.get("message", ""):
                                                st.info(op["message"])
                                            elif "memory" in op.get("type", ""):
                                                st.text(op["message"])
                                            elif "debug" in op.get("type", "") and st.session_state.debug_mode:
                                                st.text(op["message"])
            
            # Input box (disabled during active runs)
            if st.session_state.run_active:
                st.text_input("Your message", "Processing...", disabled=True, key="disabled_input")
            else:
                prompt = st.chat_input("Your message (type 'facts' to see all stored facts)")
                if prompt:
                    process_message(prompt)
                    st.rerun()
                    
            # Display command help
            with st.expander("Command Help"):
                st.markdown("""
                - `facts`: Show all stored facts about you
                - `memory on`: Show detailed memory operations
                - `memory off`: Hide detailed memory operations
                - `exit`: End the conversation
                """)
        
        with col2:
            # Memory operations and facts panel
            st.subheader("Memory Management")
            
            # Toggle for memory operations display
            st.toggle("Show inline memory operations", value=st.session_state.inline_ops_toggle, key="inline_ops_toggle", 
                      help="Show memory operations directly in the conversation flow")
            
            st.toggle("Show detailed debug info", value=st.session_state.debug_mode, key="debug_toggle", 
                      on_change=lambda: setattr(st.session_state, 'debug_mode', st.session_state.debug_toggle),
                      help="Show detailed technical information about memory operations")
            
            # Memory function controls
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Show All Facts", use_container_width=True):
                    st.session_state.show_facts = True
                    st.rerun()
            with col2:
                if st.button("Show All Retrievals", use_container_width=True):
                    st.session_state.show_retrievals = True
                    st.rerun()
            
            # Summary of recent memory operations
            st.subheader("Recent Memory Changes")
            recent_ops = [op for op in st.session_state.memory_ops if "memory_highlight" in op.get("type", "")]
            if recent_ops:
                for op in reversed(recent_ops[-5:]):  # Show last 5 memory highlights
                    memory_type = ""
                    if "STORED" in op["message"]:
                        memory_type = "stored"
                    elif "RETRIEVED" in op["message"]:
                        memory_type = "retrieved"
                    elif "UPDATED" in op["message"]:
                        memory_type = "updated"
                    elif "DELETED" in op["message"]:
                        memory_type = "deleted"
                        
                    if memory_type:
                        st.info(op["message"])
            else:
                st.caption("No memory operations yet")
            
            # Show all facts if requested
            if st.session_state.get("show_facts", False):
                st.subheader("All Stored Facts")
                facts = list_all_facts()
                
                if facts:
                    for i, fact in enumerate(facts):
                        fact_type = fact.get("fact_type", "other")
                        confidence = fact.get("confidence", 1.0)
                        content = fact.get("content", "")
                        fact_id = fact.get("id", "unknown")
                        
                        st.markdown(f"**{i+1}. [{fact_type} - {confidence:.2f}]** {content}")
                        with st.expander("Fact Details"):
                            st.code(f"ID: {fact_id}")
                            
                # Button to hide facts
                if st.button("Hide Facts"):
                    st.session_state.show_facts = False
                    st.rerun()
                    
            # Show all retrievals if requested
            if st.session_state.get("show_retrievals", False):
                st.subheader("All Memory Retrievals")
                
                # Filter for retrieval operations
                retrieval_ops = [op for op in st.session_state.memory_ops 
                                if "memory_highlight" in op.get("type", "") and "MEMORIES RETRIEVED" in op.get("message", "")]
                
                if retrieval_ops:
                    for i, op in enumerate(reversed(retrieval_ops)):
                        # Show the retrieval summary
                        st.info(f"{i+1}. {op['message']}")
                        
                        # If additional data is available, show the details
                        if "additional_data" in op:
                            retrieval_data = op["additional_data"]
                            query = retrieval_data.get("query", "")
                            memories = retrieval_data.get("memories", [])
                            
                            with st.expander("Retrieval Details", expanded=False):
                                # Show query used
                                if query:
                                    st.caption(f"Query: '{query}'")
                                else:
                                    st.caption("Retrieved most recent facts")
                                
                                # Display the memories that were retrieved
                                if memories:
                                    for j, memory in enumerate(memories):
                                        fact_type = memory.get("fact_type", "other")
                                        content = memory.get("content", "")
                                        confidence = memory.get("confidence", 1.0)
                                        st.markdown(f"**{j+1}. [{fact_type}]** {content} *(confidence: {confidence:.2f})*")
                                else:
                                    st.caption("No memories were retrieved")
                else:
                    st.caption("No memory retrievals found")
                    
                # Button to hide retrievals
                if st.button("Hide Retrievals"):
                    st.session_state.show_retrievals = False
                    st.rerun()

if __name__ == "__main__":
    main()