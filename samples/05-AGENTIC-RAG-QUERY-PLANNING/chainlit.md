# Cardiology-Focused AI Assistant with Azure AI Services 🫀💻

Welcome to the Cardiology AI Assistant! This application is designed to help cardiologists and healthcare professionals access relevant information from multiple sources to make informed decisions about patient care.

## Features and Tools 🛠️

This assistant has access to multiple knowledge sources through powerful Azure AI services:

### 1. Patient Data Access (NL2SQL)
- Query a patient database using natural language
- Access patient medical history, medications, and vital stats
- Secure, controlled access to patient information

### 2. ACC Guidelines Search (Azure AI Search)
- Access official American College of Cardiology (ACC) guidelines
- Evidence-based recommendations for cardiology practices
- Semantic search capabilities for accurate information retrieval

### 3. Real-Time Web Information (Azure AI Agent Service + Bing Web Grounding)
- Access the latest medical research and news via Bing Web Grounding
- Get up-to-date information about new treatments, FDA approvals, and more
- Powered by Azure AI Agent Service for comprehensive web search

## How to Use 🚀

1. **Ask a question or make a request** related to cardiology, patient data, or medical information
2. The AI will **automatically choose which tools to use** based on your query
3. You'll see each step as the AI retrieves information and builds a response
4. The final answer will combine information from all relevant sources

## Example Queries 💬

- "How many patients have Hypertension and are prescribed Lisinopril?"
- "What does the ACC recommend as first-line therapy for hypertension in elderly patients?"
- "Are there any recent updates in 2025 on new anticoagulant therapies from the FDA?"
- "I have a 79-year-old patient named Gloria Paul with hyperlipidemia. She's on Atorvastatin. Can you confirm her medical details from the database, check the ACC guidelines for hyperlipidemia, and see if there are any new medication updates from the FDA as of Feb 2025? Then give me a summary."

## Required Environment Variables ⚙️

To run this application, you need to set up the following environment variables:

```
AZURE_OPENAI_API_KEY=your-azure-openai-api-key
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_ENDPOINT=https://your-azure-openai-endpoint.openai.azure.com/
AZURE_OPENAI_CHAT_COMPLETION_DEPLOYED_MODEL_NAME=gpt-4o

AZURE_SEARCH_SERVICE_ENDPOINT=https://your-search-service.search.windows.net
AZURE_SEARCH_ADMIN_KEY=your-azure-search-key

AZURE_CONNECTION_STRING=your-azure-connection-string
BING_CONNECTION_NAME=fsunavalabinggrounding

AZURE_SQL_SERVER_NAME=your-sql-server
AZURE_SQL_DATABASE_NAME=your-database-name
AZURE_SQL_USER_NAME=your-username
AZURE_SQL_PASSWORD=your-password
```

## Technical Implementation 🧠

This app leverages several advanced Azure AI services:

- **Azure OpenAI Service**: Powers the language model capabilities
- **Azure AI Search**: Provides semantic search over ACC guidelines
- **Azure AI Agent Service**: Orchestrates the Bing Web Grounding tool
- **Azure SQL Database**: Stores patient information
- **Chainlit**: Provides the interactive chat interface with step visualization

Developed by the @farzad528 Happy exploring! 🚀