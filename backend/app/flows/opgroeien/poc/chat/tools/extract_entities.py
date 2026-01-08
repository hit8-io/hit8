"""
Tool for extracting entities from text using LLM.
"""
from __future__ import annotations

import json
from datetime import datetime
from enum import Enum

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.flows.common import get_entity_extraction_model
from app.flows.opgroeien.poc import constants as flow_constants
from app.prompts.opgroeien.poc.extract_system_prompt import EXTRACT_SYSTEM_INSTRUCTION

logger = structlog.get_logger(__name__)


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


def _extract_entities_impl(chatInput: str) -> str:
    """
    Extract entities from text using LLM with function calling.
    
    Args:
        chatInput: The text to extract entities from
        
    Returns:
        JSON string with extracted entities and metadata
    """
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
        model = get_entity_extraction_model(
            thinking_level=flow_constants.ENTITY_EXTRACTION_THINKING_LEVEL,
            temperature=flow_constants.ENTITY_EXTRACTION_TEMPERATURE,
        )
        model_with_tools = model.bind_tools(
            [ExtractKnowledgeInput],
            tool_choice="any"  # Force function call (equivalent to "ANY" in JSON spec)
        )
        
        # Create messages
        messages = [
            SystemMessage(content=EXTRACT_SYSTEM_INSTRUCTION),
            HumanMessage(content=chatInput)
        ]
        
        logger.debug(
            "extract_entities_invoking_llm",
            input_length=len(chatInput),
        )
        
        # Invoke model
        response = model_with_tools.invoke(messages)
        
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
