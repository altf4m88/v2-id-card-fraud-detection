import os
import logging
import json
from uuid import uuid4
from typing import TypedDict, Annotated, List, Dict, Any

from flask import Flask, request, render_template, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

# --- Import Agent Tools ---
from tools.analyze_id_card import analyze_id_card_tool
from tools.database_tools import check_duplicate_nik_tool, insert_id_card_tool
from tools.notify_fraud import notify_fraud_tool
import ast

# --- Load Environment Variables & Configure App ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Agent State Definition ---
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    analysis_result: Dict[str, Any] | None

# --- LLM & Tool Initialization ---
try:
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", convert_system_message_to_human=True)
    tools = [analyze_id_card_tool, check_duplicate_nik_tool, insert_id_card_tool, notify_fraud_tool]
    llm_with_tools = llm.bind_tools(tools)
except Exception as e:
    logger.critical(f"Could not initialize Google Generative AI. Check API Key. Error: {e}")
    llm_with_tools = None

# --- Agent Workflow Definition ---

# 1. Agent Node: The primary thinking loop of the agent
def agent_node(state: AgentState):
    logger.info("Agent node executing...")
    response = llm_with_tools.invoke(state['messages'])
    return {"messages": [response]}

# 2. Tool Node: Executes the tools called by the agent
def tool_node(state: AgentState) -> dict:
    logger.info("Tool node executing...")
    tool_calls = state["messages"][-1].tool_calls
    tool_outputs = []
    
    for call in tool_calls:
        tool_name = call['name']
        tool_args = call.get('args', {})

        # --- FINAL FIX STARTS HERE ---
        # Before invoking the tool, we check if the 'data' argument needs to be parsed from a string.
        if tool_name == 'insert_id_card_tool' and isinstance(tool_args.get('data'), str):
            try:
                # ast.literal_eval safely parses a string representation of a Python literal.
                logger.info("Found 'data' argument as a string. Parsing back to dictionary.")
                tool_args['data'] = ast.literal_eval(tool_args['data'])
            except (ValueError, SyntaxError) as e:
                # If parsing fails, return an error message to the agent.
                logger.error(f"Fatal: Failed to parse 'data' argument string: {e}")
                tool_outputs.append(
                    ToolMessage(content=f"Error: The 'data' argument was a malformed string and could not be parsed.", tool_call_id=call['id'])
                )
                continue # Move to the next tool call
        # --- FINAL FIX ENDS HERE ---

        logger.info(f"Invoking tool: {tool_name} with args: {tool_args}")
        
        selected_tool = next((t for t in tools if t.name == tool_name), None)
        if not selected_tool:
            raise ValueError(f"Tool '{tool_name}' not found.")
            
        output = selected_tool.invoke(tool_args)
        
        # If this was the analysis tool, store its result in the state for the router
        if tool_name == 'analyze_id_card_tool':
            state['analysis_result'] = output
        
        tool_outputs.append(ToolMessage(content=str(output), tool_call_id=call['id']))
        
    return {"messages": tool_outputs}

# 3. Router: Decides the next step based on the analysis result
def router(state: AgentState) -> str:
    logger.info("Router node executing...")
    analysis_status = state.get('analysis_result', {}).get('status')
    logger.info(f"Analysis status for routing: {analysis_status}")

    if analysis_status == 'success':
        # If analysis is successful, the next step is to check for duplicates
        return "check_duplicate_nik_tool"
    elif analysis_status in ['potential_fraud', 'image_quality_failure']:
        # If fraud is detected early or quality is bad, go straight to reporting
        return "notify_fraud_tool"
    
    # Default case is to continue the agent loop
    return "agent"

# --- Graph Construction (Corrected) ---
graph_builder = StateGraph(AgentState)

# Define the nodes
graph_builder.add_node("agent", agent_node)
graph_builder.add_node("tools", tool_node)

# Define the edges
graph_builder.set_entry_point("agent")

# This conditional edge decides whether to run a tool or end the process.
graph_builder.add_conditional_edges(
    "agent",
    # This function checks if the agent decided to call a tool
    lambda state: "tools" if state["messages"][-1].tool_calls else END,
    {
        # If the agent called a tool, go to the 'tools' node
        "tools": "tools",
        # Otherwise, the process is finished
        END: END
    }
)

# After any tool is run, the workflow always loops back to the agent
# to process the tool's output.
graph_builder.add_edge("tools", "agent")

# Compile the graph
graph = graph_builder.compile()

# --- Flask Routes ---
@app.route('/', methods=['GET'])
def index():
    """Renders the main upload page."""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handles file upload and triggers the fraud detection agent."""
    if 'file' not in request.files or not llm_with_tools:
        return jsonify({"error": "Invalid request or LLM not initialized"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid4()}_{filename}")
    file.save(filepath)

    # This is the initial prompt that starts the entire process
    system_prompt = """
    You are an ID fraud detection agent. Your task is to process an ID card image by following a strict workflow. You must provide your final response in Bahasa Indonesia.

    1.  **Analyze the Image**: You will be given a file path. Your first and only initial action is to call the `analyze_id_card_tool` with this path.

    2.  **Handle Image Quality Failure**: If the analysis result status is 'image_quality_failure', your job is finished. Do NOT call any other tools. Simply report the specific reason for the failure (e.g., "Gambar buram", "Ada pantulan cahaya") directly to the user as your final answer.

    3.  **Handle Potential Fraud**: If the analysis result status is 'potential_fraud' (due to failed data or positional checks), you MUST call the `notify_fraud_tool` with the provided reason. This is your only action. After calling the tool, provide a summary of the action taken.

    4.  **Handle Success & Check for Duplicates**: If the analysis result status is 'success', your next step is to use the extracted 'nik' to call the `check_duplicate_nik_tool`.
        - If the NIK is a **duplicate**, call `notify_fraud_tool` with "Duplicate NIK found" as the reason.
        - If the NIK is **not a duplicate**, call `insert_id_card_tool` with the data from the analysis.

    5.  **Final Report**: After completing your tasks, provide a final, concise summary to the user explaining the outcome.
    """
    initial_message = HumanMessage(content=f"{system_prompt}\n\nFile Path: {filepath}")
    
    final_response = "Agent did not produce a final response."
    try:
        events = graph.stream(
            {"messages": [initial_message]},
            # Limit the number of steps to prevent infinite loops
            {"recursion_limit": 15}
        )
        for event in events:
            if "agent" in event:
                message = event["agent"]["messages"][-1]
                if not message.tool_calls and message.content:
                    final_response = message.content
    except Exception as e:
        logger.error(f"Error during graph execution: {e}")
        final_response = f"An error occurred: {e}"
    # finally:
    #     os.remove(filepath)
    
    return jsonify({"response": final_response})


if __name__ == '__main__':
    if not os.getenv("GOOGLE_API_KEY"):
        print("CRITICAL: GOOGLE_API_KEY environment variable not set.")
    else:
        # Before running, ensure the database is set up
        from database_setup import setup_database
        setup_database()
        app.run(host='0.0.0.0', port=3000, debug=True)