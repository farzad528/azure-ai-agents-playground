# Azure AI Agents Playground 🧪

## Table of Contents
1. [Overview](#overview)
2. [Key Features & Examples](#key-features--examples)
3. [Quick Start](#quick-start)
4. [Usage](#usage)
5. [Contributing](#contributing)
6. [License](#license)

## 🌟 Overview

Welcome to the Azure AI Agents Playground! 👋 This repository is designed to be your hands-on learning space for diving into the exciting world of Azure AI Agents.

Here, you'll find a collection of practical examples, from quick start guides to more advanced implementations, all focused on helping you understand and utilize Azure AI Agents effectively. Whether you're a seasoned developer or just starting your AI journey, this playground offers a friendly environment to experiment and build amazing things.

This repository serves as a personal playground for me to explore and showcase the capabilities of Azure AI Agents. It's also open to the community for learning and inspiration. Feel free to explore, adapt, and use these examples as a starting point for your own projects!

NOTE, all of these use cases are real-world customer problems where AI can make the world a more efficient place.

## ✨ Key Features & Examples

This playground is organized into different sample folders, each focusing on a specific aspect or use case of Azure AI Agents. Dive into these examples to get started:

### [samples/01-QUICKSTART](./samples/01-QUICKSTART)
**⚡ Use this repo for:** Quickly setting up and running your first Azure AI Agent connected to Azure AI Search. Perfect for beginners!

- Explore a basic agent that answers questions using documents indexed in Azure AI Search.
- Check out the agent-quickstart.ipynb notebook for a step-by-step walkthrough.

### [samples/02-AGENT-MEMORY-MEM0](./samples/02-AGENT-MEMORY-MEM0)
**🧠 Use this repo for:** Implementing agent memory using Mem0 to create more conversational and context-aware agents.

- Discover how to equip your agents with memory to maintain context across conversations.
- See how Mem0 enhances agent interactions in the provided examples.

### [samples/03-SEMANTIC-KERNEL-AZURE-AGENTS](./samples/03-SEMANTIC-KERNEL-AZURE-AGENTS)
**⚛️ Use this repo for:** Integrating Azure AI Agents with Semantic Kernel for building more complex and modular AI applications.

- Learn how to leverage the power of Semantic Kernel alongside Azure AI Agents.
- Explore the sk.ipynb notebook to see Semantic Kernel in action with agents.

### [samples/04-AGENTIC-RAG-ROUTERS](./samples/04-AGENTIC-RAG-ROUTERS)
**🗺️ Use this repo for:** Building advanced Agentic Retrieval-Augmented Generation (RAG) systems with intelligent routing between different knowledge sources (Azure AI Search & Bing Search).

- Delve into creating sophisticated agents that can route queries to the most relevant information source.
- Run the app.py Chainlit application and explore the chainlit.md documentation for details.

### [samples/05-AGENTIC-RAG-QUERY-PLANNING](./samples/05-AGENTIC-RAG-QUERY-PLANNING)
**🔍 Use this repo for:** Creating multi-step agentic RAG systems that can orchestrate queries across multiple data sources with advanced planning capabilities.

- Build a cardiology-focused AI assistant that integrates three distinct data sources:
  - **Structured Data**: Patient records from Azure SQL Database
  - **Unstructured Data**: Medical guidelines from Azure AI Search
  - **Web Data**: Real-time information using Azure AI Agent Service with Bing Grounding Tool
- Experience how the agent dynamically decides which tools to use and in what order
- See how complex medical queries can be broken down into multiple steps for comprehensive answers
- Explore the Jupyter notebook for a detailed walkthrough or run the Chainlit app for an interactive demo

## 🚀 Quick Start

Ready to jump in? Here's how to get started:

1. Clone the repository:
```bash
git clone https://github.com/Farzad528/azure-ai-agents-playground.git
cd azure-ai-agents-playground
```

2. Navigate to a sample folder (e.g., samples/01-QUICKSTART):
```bash
cd samples/01-QUICKSTART
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
   - Make sure you have the necessary Azure and OpenAI API keys and connection strings set as environment variables.
   - Refer to the specific sample's README or code comments for required environment variables.

5. Run the sample:
   - For Jupyter Notebook examples, open the .ipynb file and run the cells.
   - For Python script examples, run the .py file from your terminal: `python your_script_name.py`

## 🧑‍💻 Usage

Feel free to explore and modify the code in this repository. Here are some ideas:

- **Run the provided Jupyter Notebooks:** Step through the notebooks to understand the code and experiment with different parameters.
- **Adapt the examples:** Modify the code to fit your own use cases and explore different Azure AI Agents functionalities.
- **Create new agents:** Build your own agents from scratch, leveraging the samples as a guide.
- **Experiment with different tools:** Integrate various Azure AI services and external tools with your agents.

## 🙌 Contributing

While this is primarily a personal learning playground, your input is highly valued! Check out the [CONTRIBUTING.md](./CONTRIBUTING.md) file for guidelines on how you can contribute:

- Report bugs 🐛 and suggest new features 💡 by opening issues.
- Share your feedback and ideas to make this playground more valuable for everyone.
- Engage in discussions and help others in the community.

## 📜 License

This project is licensed under the MIT License. Feel free to use and adapt the code for your own projects.