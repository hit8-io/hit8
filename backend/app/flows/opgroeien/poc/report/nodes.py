"""
Nodes for the Report Engine Map-Reduce Graph.
"""
import json
from datetime import datetime
from typing import List, Dict, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents import create_agent
from langgraph.types import Send

from app.flows.opgroeien.poc.report.state import ReportState
from app.flows.opgroeien.poc.report.tools.chat import consult_general_knowledge
from app.flows.opgroeien.poc.chat.tools.get_procedure import get_procedure
from app.flows.opgroeien.poc.chat.tools.get_regelgeving import get_regelgeving
from app.flows.common import get_agent_model
from app.prompts.loader import load_prompt
from app.flows.opgroeien.poc.constants import MAX_PARALLEL_WORKERS

# --- Input Schema for Worker Node ---
class ClusterInput(TypedDict):
    procedures: List[Dict]
    meta: Dict

# --- Node 1: Splitter (Map) ---
def get_metadata(proc: Dict) -> Dict[str, str]:
    """
    Returns metadata (department, topic, safe_key) based on procedure ID.
    """
    # Extract procedure ID - prefer 'id' field, fallback to 'doc'
    proc_id = (proc.get("id") or proc.get("doc") or "").upper()
    
    # Map procedure prefixes to metadata
    if proc_id.startswith("PR-AV"):
        return {
            "dept": "Preventieve Gezinsondersteuning (PGJO)",
            "topic": "Aanbodsvormen",
            "safe_key": "PGJO_Aanbodsvormen"
        }
    if proc_id.startswith("PR-CA"):
        return {
            "dept": "Preventieve Gezinsondersteuning (PGJO)",
            "topic": "Consultatiebureauarts",
            "safe_key": "PGJO_CB_Arts"
        }
    if proc_id.startswith("PR-CB"):
        return {
            "dept": "Preventieve Gezinsondersteuning (PGJO)",
            "topic": "Consultatiebureau",
            "safe_key": "PGJO_CB_Algemeen"
        }
    if proc_id.startswith("PR-HK"):
        return {
            "dept": "Preventieve Gezinsondersteuning (PGJO)",
            "topic": "Huizen van het Kind",
            "safe_key": "PGJO_Huizen_vh_Kind"
        }
    if proc_id.startswith("PR-OH"):
        return {
            "dept": "Preventieve Gezinsondersteuning (PGJO)",
            "topic": "OverKop",
            "safe_key": "PGJO_OverKop"
        }
    if proc_id.startswith("PR-VE"):
        return {
            "dept": "Opvang Baby's en Peuters",
            "topic": "Vergunnen",
            "safe_key": "Kinderopvang_Vergunnen"
        }
    if proc_id.startswith("PR-HA"):
        return {
            "dept": "Opvang Baby's en Peuters",
            "topic": "Handhaving",
            "safe_key": "Kinderopvang_Handhaving"
        }
    if proc_id.startswith("PR-SU"):
        return {
            "dept": "Opvang Baby's en Peuters",
            "topic": "Subsidiëren",
            "safe_key": "Kinderopvang_Subsidies"
        }
    if proc_id.startswith("PR-OV"):
        return {
            "dept": "Opvang Baby's en Peuters",
            "topic": "Overkoepelend",
            "safe_key": "Kinderopvang_Overkoepelend"
        }
    if proc_id.startswith("PR-JH"):
        return {
            "dept": "Jeugdhulp",
            "topic": "Algemeen",
            "safe_key": "Jeugdhulp_Algemeen"
        }
    if proc_id.startswith("PR-LL"):
        return {
            "dept": "Lokale Loketten",
            "topic": "Algemeen",
            "safe_key": "Lokale_Loketten"
        }
    
    # Default fallback
    return {
        "dept": "Overige Procedures",
        "topic": "Algemeen",
        "safe_key": "Overige_Procedures"
    }


def splitter_node(state: ReportState):
    """
    Analyzes input procedures and generates parallel tasks.
    Groups procedures by department/topic using safe_key for file storage.
    Processes first batch and stores remaining clusters for batching.
    """
    raw_data = state.get("raw_procedures", [])
    clusters: Dict[str, Dict] = {}
    
    # Group procedures by safe_key
    for proc in raw_data:
        if not proc:
            continue
        
        # Skip if no ID found
        proc_id = proc.get("id") or proc.get("doc")
        if not proc_id:
            continue
        
        meta = get_metadata(proc)
        safe_key = meta["safe_key"]
        
        # Initialize cluster if it doesn't exist
        if safe_key not in clusters:
            clusters[safe_key] = {
                "file_id": safe_key,  # Used for file storage
                "department_name": meta["dept"],
                "topic_name": meta["topic"],
                "procedures": []
            }
        
        clusters[safe_key]["procedures"].append(proc)
    
    # Convert to list for batching
    cluster_list = list(clusters.values())
    
    # Process first batch
    first_batch = cluster_list[:MAX_PARALLEL_WORKERS]
    remaining_clusters = cluster_list[MAX_PARALLEL_WORKERS:]
    
    # Store remaining clusters and log in state
    state_update = {
        "pending_clusters": remaining_clusters,
        "logs": [f"Splitter: Processing {len(first_batch)} clusters in first batch, {len(remaining_clusters)} remaining"]
    }
    
    # Return state update dict with Send objects for routing
    # The conditional edge will extract the Send objects
    if not first_batch:
        return state_update
    
    # Attach Send objects to state update for conditional edge extraction
    # We'll use a special key that the conditional edge can extract
    send_objects = [
        Send("analyst_node", {"procedures": c["procedures"], "meta": c}) 
        for c in first_batch
    ]
    
    # Return dict with both state updates and routing information
    # The conditional edge function will extract the "__sends__" key
    return {
        **state_update,
        "__sends__": send_objects
    }

# --- Node 2: Analyst (Worker) ---
async def analyst_node(input_data: ClusterInput):
    """
    Analyzes a SINGLE cluster using the Chat Tool and direct lookup tools.
    """
    llm = get_agent_model()
    
    # GIVE TOOLS TO THE ANALYST
    # 1. Bridge to general chat knowledge
    # 2. Direct access to procedure/regulation content
    tools = [consult_general_knowledge, get_procedure, get_regelgeving]
    
    meta = input_data["meta"]
    procs = input_data["procedures"]
    topic = meta.get("topic_name", "General")
    department = meta.get("department_name", "Unknown Department")
    file_id = meta.get("file_id", "unknown")
    
    # Load system prompt from YAML file
    prompt_obj = load_prompt("opgroeien/poc/analyst_system_prompt")
    system_prompt = prompt_obj.render(
        department_name=department,
        topic_name=topic,
    )
    
    # Pass procedures directly as human message
    human_message_content = json.dumps(procs, ensure_ascii=False)
    
    # Create the ReAct agent for this specific slice
    # We use a simple prebuilt agent here
    agent_executor = create_agent(llm, tools, system_prompt=system_prompt)
    
    # Invoke
    result = await agent_executor.ainvoke({
        "messages": [HumanMessage(content=human_message_content)]
    })
    
    chapter_text = result["messages"][-1].content
    
    # Append to state.chapters via operator.add
    # Also append a log entry
    log_entry = f"Analyst finished chapter: {topic} (Department: {department}, File ID: {file_id})"
    
    return {
        "chapters": [chapter_text], 
        "logs": [log_entry]
    }

# --- Node 2.5: Batch Processor (Handles subsequent batches) ---
def batch_processor_node(state: ReportState):
    """
    Processes the next batch of clusters if any remain.
    Returns Send objects for the next batch, or routes to editor if done.
    """
    pending = state.get("pending_clusters", [])
    
    if not pending:
        # No more clusters, route to editor
        return {
            "logs": ["Batch processor: All clusters processed, routing to editor"]
        }
    
    # Process next batch
    next_batch = pending[:MAX_PARALLEL_WORKERS]
    remaining = pending[MAX_PARALLEL_WORKERS:]
    
    # Update state with remaining clusters
    state_update = {
        "pending_clusters": remaining,
        "logs": [f"Batch processor: Processing {len(next_batch)} clusters, {len(remaining)} remaining"]
    }
    
    # Return Send objects for next batch
    send_objects = [
        Send("analyst_node", {"procedures": c["procedures"], "meta": c}) 
        for c in next_batch
    ]
    
    return {
        **state_update,
        "__sends__": send_objects
    }

# --- Node 3: Editor (Reducer) ---
async def editor_node(state: ReportState):
    """
    Aggregates all chapters into the final report.
    """
    llm = get_agent_model()
    
    chapters = state.get("chapters", [])
    full_text = "\n\n---\n\n".join(chapters)
    
    # Format date
    formatted_date = datetime.now().strftime("%d %B %Y")
    
    # Load system prompt from YAML file
    prompt_obj = load_prompt("opgroeien/poc/editor_system_prompt")
    system_prompt = prompt_obj.render(
        date=formatted_date,
        full_report_body=full_text,
    )
    
    # Human message contains the full report body
    human_message = full_text
    
    response = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_message)
    ])
    
    return {
        "final_report": response.content,
        "logs": ["Editor finished final report."]
    }
