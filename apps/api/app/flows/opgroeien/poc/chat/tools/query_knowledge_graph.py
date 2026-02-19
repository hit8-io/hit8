"""
Tool for querying a knowledge graph.
"""
from __future__ import annotations

import json

import structlog
from langchain_core.tools import tool
from psycopg import sql as psql

from app.flows.opgroeien.poc.db import _get_db_connection

logger = structlog.get_logger(__name__)


@tool
def query_knowledge_graph(entities: str) -> str:
    """
    Query an internal knowledge graph with as input a list of entities, returning a list of connected entities
    
    Args:
        entities: JSON string with list of entities
        
    Returns:
        JSON string with connected entities: {"entities": ["entity1", "entity2", ...]}
    """
    try:
        # Parse entities
        entity_list = json.loads(entities) if isinstance(entities, str) else entities
        
        # Validate input
        if not entity_list or not isinstance(entity_list, list):
            logger.warning(
                "query_knowledge_graph_invalid_input",
                entities=entities,
            )
            return json.dumps({"entities": []})
        
        # Collect all related entity names
        related_entities = set()
        
        # Query database for each entity
        with _get_db_connection() as conn:
            with conn.cursor() as cursor:
                for entity in entity_list:
                    if not entity or not isinstance(entity, str) or not entity.strip():
                        continue
                    
                    entity_name = entity.strip()
                    
                    # SQL query to find matching entities and their relationships
                    # Replicates Cypher: MATCH (n) WHERE toLower(n.name) = toLower($entity) WITH n LIMIT 3
                    # MATCH (n)-[r]-(connected) RETURN n, r, connected LIMIT 10
                    query_sql = psql.SQL("""
                        WITH matched_entities AS (
                          SELECT name, doc, chunk, doc_type
                          FROM entities
                          WHERE LOWER(name) = LOWER(%s)
                          LIMIT 3
                        ),
                        entity_relationships AS (
                          SELECT 
                            me.name as matched_entity_name,
                            CASE 
                              WHEN r.source_name = me.name AND r.source_doc = me.doc 
                                   AND r.source_chunk = me.chunk AND r.source_doc_type = me.doc_type
                              THEN r.target_name
                              ELSE r.source_name
                            END as connected_entity_name
                          FROM matched_entities me
                          INNER JOIN relationships r ON (
                            (r.source_name = me.name AND r.source_doc = me.doc 
                             AND r.source_chunk = me.chunk AND r.source_doc_type = me.doc_type)
                            OR
                            (r.target_name = me.name AND r.target_doc = me.doc 
                             AND r.target_chunk = me.chunk AND r.target_doc_type = me.doc_type)
                          )
                          LIMIT 10
                        )
                        SELECT DISTINCT matched_entity_name as entity_name FROM entity_relationships
                        UNION
                        SELECT DISTINCT connected_entity_name as entity_name FROM entity_relationships
                        WHERE connected_entity_name IS NOT NULL
                    """)
                    
                    cursor.execute(query_sql, (entity_name,))
                    
                    # Collect entity names from results
                    for row in cursor.fetchall():
                        entity_name_result = row[0]
                        if entity_name_result:
                            related_entities.add(entity_name_result)
        
        # Return sorted list of unique entity names
        result = {
            "entities": sorted(list(related_entities))
        }
        
        logger.info(
            "query_knowledge_graph_success",
            input_entity_count=len(entity_list),
            output_entity_count=len(related_entities),
        )
        
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        logger.error(
            "query_knowledge_graph_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        return json.dumps({"error": f"Failed to query knowledge graph: {str(e)}"})
