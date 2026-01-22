# Basic MCP Server Structure

An MCP server typically includes:

- **Server Configuration**: Setup port, authentication, and other settings
- **Resources**: Data and context made available to LLMs
- **Tools**: Functionality that models can invoke
- **Prompts**: Templates for generating or structuring text


# Instructions

## -0- Create a virtual environment

```bash
python -m venv venv
```

## -1- Activate the virtual environment

```bash
venv\Scripts\activate
```

## -2- Install the dependencies

```bash
pip install "mcp[cli]"
pip install requirements.txt
```

## -3- Run the sample

```bash
mcp run server.py
```
