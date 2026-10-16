# Thought2Code

**From an idea to working code.**

Thought2Code is an AI-powered platform designed to turn ideas expressed in natural language into working applications. The goal is to make software creation more accessible by allowing users to describe what they want to build instead of writing every line of code themselves.

## The Vision

Imagine describing an application in plain English and watching it take shape. Thought2Code aims to make that possible through an AI-powered development workflow that plans, builds, and generates application files.

## How It Works

Thought2Code uses a multi-agent workflow to coordinate the application-building process:

- **Planning:** Understands the user's request and creates a structured project plan.
- **Architecture:** Breaks the plan into implementation tasks and identifies the files needed.
- **Code Generation:** Implements tasks and writes the resulting source files.

The backend workflow is orchestrated using LangGraph.

## Technology Stack

- Python
- LangGraph
- LangChain
- Groq API
- Pydantic
- `uv` for dependency management

## Getting Started

### Prerequisites

- Python 3.11 or compatible version
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- A Groq API key from the [Groq Console](https://console.groq.com/keys)

### Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/Sohail-19/Thought2Code.git
   cd Thought2Code
   ```

2. Install dependencies:

   ```bash
   uv sync
   ```

3. Create a `.env` file using `.sample_env` as a reference and add your Groq API key. Never commit your secrets.

4. Start the backend:

   ```bash
   uv run python main.py
   ```

## Example Ideas

Try describing applications such as:

- A modern to-do list with task management.
- A responsive calculator.
- A blog API with a database.

## Roadmap

- [x] Multi-agent planning and code-generation workflow
- [ ] Build a modern React + Vite frontend
- [ ] Connect the frontend to the Python backend
- [ ] Add generated-code validation and error recovery
- [ ] Improve the application-building experience

## Project Status

Thought2Code is under active development. The current focus is evolving the backend into a complete application-generation platform and building an intuitive user interface.

