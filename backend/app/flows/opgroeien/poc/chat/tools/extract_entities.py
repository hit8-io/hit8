"""
Tool for extracting entities from text using LLM.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.flows.common import get_tool_model
from app.flows.opgroeien.poc import constants as flow_constants
from app.prompts.loader import load_prompt

logger = structlog.get_logger(__name__)


def _extract_model_config(model: Any) -> dict[str, Any]:
    """Extract model configuration (temperature, thinking_level) from model object.
    
    Args:
        model: Model object with optional model_kwargs attribute
        
    Returns:
        Dictionary with config values, empty dict if none found
    """
    config = {}
    if hasattr(model, "model_kwargs") and model.model_kwargs:
        if "temperature" in model.model_kwargs:
            config["temperature"] = model.model_kwargs["temperature"]
        if "thinking_level" in model.model_kwargs:
            config["thinking_level"] = model.model_kwargs["thinking_level"]
    return config


class EntityType(str, Enum):
    """Entity type enumeration."""
    OVERHEIDSORGAAN = "Overheidsorgaan"
    PARTIJ = "Partij"
    POLITICUS = "Politicus"
    WET = "Wet"
    DOCUMENT = "Document"
    ANDERS = "Anders"


class Entity(BaseModel):
    """Represents a single extracted entity."""
    name: str = Field(..., description="The unique name of the entity.", min_length=1, max_length=255)
    type: EntityType = Field(..., description="The type of the entity.")
    description: str = Field(..., description="A brief description of the entity.", max_length=1000)
    confidence: float = Field(
        ...,
        description="Confidence score for the extraction (0.0 to 1.0)",
        ge=0.0,
        le=1.0
    )


class ExtractionMetadata(BaseModel):
    """Metadata about the extraction process."""
    extraction_timestamp: str = Field(
        ...,
        description="When the extraction was performed",
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z?$"
    )
    source_text_length: int = Field(..., description="Length of the source text in characters", ge=0)


class ExtractKnowledgeInput(BaseModel):
    """Input schema for the extract_knowledge function."""
    entities: list[Entity] = Field(..., description="A list of all extracted entities.")
    metadata: ExtractionMetadata | None = Field(
        default=None,
        description="Optional metadata about the extraction"
    )


def _extract_entities_impl(chatInput: str, thread_id: str | None = None, callbacks: list[Any] | None = None) -> str:
    """
    Extract entities from text using LLM with function calling.
    
    Args:
        chatInput: The text to extract entities from
        thread_id: Optional thread ID for observability tracking (can also be from context)
        callbacks: Optional list of callback handlers (e.g., Langfuse callback handler)
        
    Returns:
        JSON string with extracted entities and metadata
    """
    # Get thread_id from parameter or context variable
    if not thread_id:
        try:
            from app.api.observability import _current_thread_id
            thread_id = _current_thread_id.get()
        except Exception:
            pass
    try:
        if not chatInput or not chatInput.strip():
            logger.warning("extract_entities_empty_input")
            return json.dumps({
                "entities": [],
                "metadata": {
                    "extraction_timestamp": datetime.utcnow().isoformat() + "Z",
                    "source_text_length": 0
                },
                "error": "Empty input text"
            }, ensure_ascii=False)
        
        # Get model and bind the extraction function
        # Bind Pydantic model directly - LangChain will use the class name as function name
        # We'll check for both "ExtractKnowledgeInput" and "extract_knowledge" in the response
        model = get_tool_model(
            thinking_level=flow_constants.ENTITY_EXTRACTION_THINKING_LEVEL,
            temperature=flow_constants.ENTITY_EXTRACTION_TEMPERATURE,
        )
        # Get model name for observability tracking
        model_name = getattr(model, "model", None) or getattr(model, "model_name", "unknown")
        model_with_tools = model.bind_tools(
            [ExtractKnowledgeInput],
            tool_choice="any"  # Force function call (equivalent to "ANY" in JSON spec)
        )
        
        # Load system prompt from YAML
        prompt_obj = load_prompt("opgroeien/poc/extract_system_prompt")
        system_instruction = prompt_obj.template_text
        
        # Create messages
        messages = [
            SystemMessage(content=system_instruction),
            HumanMessage(content=chatInput)
        ]
        
        logger.debug(
            "extract_entities_invoking_llm",
            input_length=len(chatInput),
        )
        
        # Track LLM call for observability (if thread_id is available)
        call_id = None
        if thread_id:
            try:
                from app.api.observability import record_llm_start
                call_id = str(uuid.uuid4())
                config = _extract_model_config(model)
                record_llm_start(thread_id, call_id, model_name, config or None, None)
            except Exception as e:
                logger.warning(
                    "extract_entities_observability_start_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )
        
        # Invoke model with callbacks if provided (for Langfuse logging)
        invoke_config = None
        if callbacks:
            invoke_config = {"callbacks": callbacks}
        response = model_with_tools.invoke(messages, config=invoke_config)
        
        # Extract token usage from response
        input_tokens, output_tokens, thinking_tokens = (0, 0, None)
        try:
            from app.api.observability import extract_token_usage
            input_tokens, output_tokens, thinking_tokens = extract_token_usage(response)
        except Exception:
            pass
        
        # Record LLM usage for observability (if thread_id is available)
        if thread_id and call_id:
            try:
                from app.api.observability import record_llm_usage
                config = _extract_model_config(model)
                record_llm_usage(
                    thread_id=thread_id,
                    call_id=call_id,
                    model=model_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    thinking_tokens=thinking_tokens,
                    config=config or None,
                )
            except Exception as e:
                logger.warning(
                    "extract_entities_observability_usage_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )
        
        
        # Extract function call result
        if not hasattr(response, "tool_calls") or not response.tool_calls:
            logger.warning(
                "extract_entities_no_function_call",
                response_content=str(response.content) if hasattr(response, "content") else None,
            )
            return json.dumps({
                "entities": [],
                "metadata": {
                    "extraction_timestamp": datetime.utcnow().isoformat() + "Z",
                    "source_text_length": len(chatInput)
                },
                "error": "LLM did not return a function call"
            }, ensure_ascii=False)
        
        # Find extract_knowledge function call
        extraction_result = None
        for tool_call in response.tool_calls:
            # Handle both dict and object formats
            if isinstance(tool_call, dict):
                func_name = tool_call.get("name") or tool_call.get("function", {}).get("name")
                func_args = tool_call.get("args") or tool_call.get("function", {}).get("arguments")
                if isinstance(func_args, str):
                    func_args = json.loads(func_args)
            else:
                func_name = getattr(tool_call, "name", None) or getattr(
                    getattr(tool_call, "function", None), "name", None
                )
                func_args = getattr(tool_call, "args", None) or getattr(
                    getattr(tool_call, "function", None), "arguments", None
                )
                if isinstance(func_args, str):
                    func_args = json.loads(func_args)
            
            if func_name == "ExtractKnowledgeInput" or func_name == "extract_knowledge":
                extraction_result = func_args
                break
        
        if not extraction_result:
            logger.warning(
                "extract_entities_no_extract_knowledge_call",
                tool_calls_count=len(response.tool_calls),
                tool_call_names=[tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None) for tc in response.tool_calls],
            )
            return json.dumps({
                "entities": [],
                "metadata": {
                    "extraction_timestamp": datetime.utcnow().isoformat() + "Z",
                    "source_text_length": len(chatInput)
                },
                "error": "No extract_knowledge function call found in response"
            }, ensure_ascii=False)
        
        # Parse and validate using Pydantic model
        try:
            extraction_data = ExtractKnowledgeInput(**extraction_result)
        except Exception as e:
            logger.error(
                "extract_entities_validation_failed",
                error=str(e),
                error_type=type(e).__name__,
                extraction_result=extraction_result,
            )
            return json.dumps({
                "entities": [],
                "metadata": {
                    "extraction_timestamp": datetime.utcnow().isoformat() + "Z",
                    "source_text_length": len(chatInput)
                },
                "error": f"Failed to validate extraction result: {str(e)}"
            }, ensure_ascii=False)
        
        # Ensure metadata is present
        if extraction_data.metadata is None:
            extraction_data.metadata = ExtractionMetadata(
                extraction_timestamp=datetime.utcnow().isoformat() + "Z",
                source_text_length=len(chatInput)
            )
        else:
            # Update source_text_length if not set correctly
            if extraction_data.metadata.source_text_length != len(chatInput):
                extraction_data.metadata.source_text_length = len(chatInput)
        
        # Validate confidence scores
        for entity in extraction_data.entities:
            if not (0.0 <= entity.confidence <= 1.0):
                logger.warning(
                    "extract_entities_invalid_confidence",
                    entity_name=entity.name,
                    confidence=entity.confidence,
                )
                # Clamp confidence to valid range
                entity.confidence = max(0.0, min(1.0, entity.confidence))
        
        # Build result dictionary
        result = {
            "entities": [
                {
                    "name": entity.name,
                    "type": entity.type.value,
                    "description": entity.description,
                    "confidence": entity.confidence
                }
                for entity in extraction_data.entities
            ],
            "metadata": {
                "extraction_timestamp": extraction_data.metadata.extraction_timestamp,
                "source_text_length": extraction_data.metadata.source_text_length
            }
        }
        
        logger.info(
            "extract_entities_success",
            entities_count=len(extraction_data.entities),
            input_length=len(chatInput),
        )
        
        return json.dumps(result, ensure_ascii=False)
        
    except json.JSONDecodeError as e:
        logger.error(
            "extract_entities_json_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return json.dumps({
            "entities": [],
            "metadata": {
                "extraction_timestamp": datetime.utcnow().isoformat() + "Z",
                "source_text_length": len(chatInput) if chatInput else 0
            },
            "error": f"JSON parsing error: {str(e)}"
        }, ensure_ascii=False)
    except Exception as e:
        logger.exception(
            "extract_entities_failed",
            error=str(e),
            error_type=type(e).__name__,
            input_length=len(chatInput) if chatInput else 0,
        )
        return json.dumps({
            "entities": [],
            "metadata": {
                "extraction_timestamp": datetime.utcnow().isoformat() + "Z",
                "source_text_length": len(chatInput) if chatInput else 0
            },
            "error": f"Failed to extract entities: {str(e)}"
        }, ensure_ascii=False)


# Create tool with name "extract_entities"
extract_entities = StructuredTool.from_function(
    func=_extract_entities_impl,
    name="extract_entities",
    description=(
        "Extracts and determines key entities from text using an LLM. "
        "The tool identifies entities such as government organizations (e.g., Vlaamse Overheid, Opgroeien), "
        "parties (e.g., CD&V, Open Vld), politicians (e.g., minister Beke), laws, documents and other relevant entities. "
        "Each entity includes a name, type, description and a confidence score between 0.0 and 1.0. "
        "Use this tool autonomously to understand context, for example when you need to extract entities from text "
        "to query a knowledge graph or determine which organizations, people or documents are relevant."
    ),
)
