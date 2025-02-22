# FIFA Rules Assistant – Basic Agentic RAG Router

This professional assistant demonstrates a robust agentic RAG pattern. The system intelligently routes queries between:
- The FIFA Legal Handbook (private knowledge base via Azure AI Search)
- Current events (public web search via Bing Search)

The agent workflow:
1. Receive a user query.
2. Determine the appropriate data source based on the query context.
3. Fetch data from the private knowledge base or public web.
4. Synthesize and respond with a comprehensive final answer.

## Example Questions:
1. "What are FIFA's rules on match-fixing?"
2. "What are the most recent controversies involving FIFA's Football Agent Regulations?"
3. "How have FIFA's recent rule changes been received?"
