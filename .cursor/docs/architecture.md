# Architecture Overview

## System Overview

Hit8 is an AI-powered conversational application built with LangGraph orchestration, providing multi-tenant chat capabilities with real-time streaming, graph visualization, and observability.

**Core Components:**

- React TypeScript frontend (Cloudflare Pages)
- FastAPI Python backend (GCP Cloud Run)
- LangGraph state machine for agent orchestration
- PostgreSQL (Supabase) for persistence
- Google Vertex AI for LLM inference

## High-Level Architecture

### Component Diagram

```mermaid
graph TB
    User[User Browser]
    Frontend[React Frontend<br/>Cloudflare Pages]
    Backend[FastAPI Backend<br/>GCP Cloud Run]
    VertexAI[Vertex AI<br/>LLM Inference]
    Supabase[Supabase<br/>PostgreSQL]
    Langfuse[Langfuse<br/>Observability]
    
    User -->|HTTPS| Frontend
    Frontend -->|HTTPS + Bearer Token| Backend
    Backend -->|API Calls| VertexAI
    Backend -->|Database Queries| Supabase
    Backend -->|Tracing| Langfuse
    
    subgraph FrontendComponents["Frontend Components"]
        ChatInterface[ChatInterface]
        GraphView[GraphView - React Flow]
        ObservabilityWindow[ObservabilityWindow]
        SSEClient[SSE Client]
    end
    
    subgraph BackendComponents["Backend Components"]
        LangGraph[LangGraph Orchestration]
        Checkpointer[AsyncPostgresSaver]
        Streaming[SSE Streaming]
        GraphAPI[Graph Structure API]
    end
    
    Frontend -.-> FrontendComponents
    Backend -.-> BackendComponents
```

### Request Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Backend
    participant Firebase
    participant LangGraph
    participant VertexAI
    participant Supabase
    
    User->>Frontend: Send message
    Frontend->>Backend: POST /chat (FormData + Bearer Token)
    Backend->>Firebase: Verify ID Token
    Firebase-->>Backend: User info (uid, email)
    Backend->>Backend: Process files, create initial state
    Backend->>LangGraph: Execute graph with state
    LangGraph->>VertexAI: Invoke LLM model
    VertexAI-->>LangGraph: Stream response chunks
    LangGraph->>Supabase: Save checkpoint
    LangGraph-->>Backend: Stream events (SSE)
    Backend-->>Frontend: SSE events (content_chunk, state_update, etc.)
    Frontend-->>User: Update UI (chat, graph visualization)
    Backend->>Supabase: Final checkpoint
    Backend-->>Frontend: graph_end event
```

## Key Design Decisions

### 1. Multi-Tenant Architecture

```mermaid
graph TB
    Request[HTTP Request<br/>X-Org: opgroeien<br/>X-Project: poc] --> Auth[Verify User Access]
    Auth -->|Authorized| GraphManager[Graph Manager]
    Auth -->|Unauthorized| Reject[403 Forbidden]
    
    GraphManager --> CheckCache{Graph Cached?}
    CheckCache -->|Yes| ReturnGraph[Return Cached Graph]
    CheckCache -->|No| LoadModule[Dynamic Import<br/>app.flows.opgroeien.poc.chat.graph]
    
    LoadModule --> CreateGraph[Create Graph Instance]
    CreateGraph --> CacheGraph[Cache per org/project]
    CacheGraph --> ReturnGraph
    
    ReturnGraph --> Execute[Execute Graph]
    
    subgraph GraphCache["Graph Cache"]
        Cache1[org: opgroeien<br/>project: poc]
        Cache2[org: hit8<br/>project: hit8]
        CacheN[org: ...<br/>project: ...]
    end
    
    CacheGraph -.-> Cache1
```

**Key Features:**

- **Org/Project routing**: Headers (`X-Org`, `X-Project`) determine which graph implementation to use
- **Dynamic graph loading**: Graphs loaded from `app.flows.{org}.{project}.{flow}.graph` module path
- **Thread-safe caching**: Graphs cached per org/project combination with lazy initialization
- **User access control**: Validates user access to org/project via `user_config.json`

### 2. LangGraph State Machine

- **State-based orchestration**: TypedDict state with message history
- **Conditional routing**: Agent node routes to tool nodes based on tool calls
- **Tool execution**: Each tool has dedicated node; tools execute sequentially
- **Checkpointing**: AsyncPostgresSaver persists state after each node execution
- **Thread continuity**: State restored from checkpoints using `thread_id` in config

### 3. Pure Async Streaming

- **Event loop native**: Uses `astream_events()` directly in FastAPI event loop (no threads)
- **SSE protocol**: Server-Sent Events for real-time updates to frontend
- **Event types**: `graph_start`, `content_chunk`, `node_start/end`, `state_update`, `tool_start/end`, `llm_start/end`, `graph_end`
- **Accumulated content**: Tracks incremental content chunks for streaming display

### 4. Graph Visualization

- **Structure API**: `/graph/structure` endpoint returns nodes/edges as JSON
- **React Flow**: Frontend renders graph structure with React Flow library
- **Real-time highlighting**: Execution state updates highlight active/visited nodes
- **State API**: `/graph/state` endpoint retrieves checkpointed state for thread restoration

### 5. Observability

- **In-memory metrics**: Tracks LLM calls, embeddings, Bright Data usage per execution
- **TTFT tracking**: Time-to-first-token measured via stream event hooks
- **Polling API**: Frontend polls `/observability/metrics` for real-time metrics display
- **Langfuse integration**: Optional tracing via Langfuse callback handlers

### 6. Cloud Run Deployment

- **VPC egress**: All traffic routed through VPC with static NAT IP
- **Connection pooling**: Shared asyncpg connection pool for PostgreSQL
- **Lifespan management**: FastAPI lifespan initializes pool/checkpointer at startup
- **Secrets injection**: Doppler secrets loaded from GCP Secret Manager
- **Auto-scaling**: Min 0, max 10 instances with container concurrency 160

## LangGraph Usage and Viewer

### Graph Structure

```mermaid
stateDiagram-v2
    [*] --> START
    START --> AgentNode: Initial message
    
    AgentNode: Agent Node<br/>Processes messages<br/>Decides tool calls
    
    AgentNode --> RouteDecision: Message processed
    RouteDecision: Route to tool?
    
    RouteDecision --> ToolNode1: Tool call 1
    RouteDecision --> ToolNode2: Tool call 2
    RouteDecision --> ToolNodeN: Tool call N
    RouteDecision --> END: No tool calls
    
    ToolNode1: Tool Node 1<br/>Vector Search
    ToolNode2: Tool Node 2<br/>Knowledge Graph
    ToolNodeN: Tool Node N<br/>Document Gen
    
    ToolNode1 --> AgentNode: Tool result
    ToolNode2 --> AgentNode: Tool result
    ToolNodeN --> AgentNode: Tool result
    
    AgentNode --> RouteDecision: Process tool results
    
    END --> [*]
    
    note right of AgentNode
        State: AgentState
        - messages: List[BaseMessage]
        Checkpointed after each node
    end note
```

**Node Types:**

- **Agent Node**: Processes messages, decides tool calls, routes to tools
- **Tool Nodes**: Execute specific tools (vector search, knowledge graph, document generation, etc.)
- **Routing Logic**: Conditional edges from agent to tool nodes based on pending tool calls

**State Management:**

- **TypedDict State**: `AgentState` with `messages` list (annotated with `operator.add` for merging)
- **Checkpointing**: AsyncPostgresSaver stores state after each node execution
- **Thread ID**: Unique identifier per conversation thread, used for state restoration

**Graph Compilation:**

- Graphs compiled with checkpointer at application startup
- Checkpointer initialized once via FastAPI lifespan
- Graph instances cached per org/project combination

### Graph Viewer Integration

**Frontend Components:**

- **GraphView**: React Flow visualization of graph structure
- **StatusWindow**: Shows execution state (visited nodes, active node, message count)
- **Real-time Updates**: Execution state pushed via SSE `state_update` events

**Backend APIs:**

- **GET /graph/structure**: Returns graph nodes/edges as JSON
- **GET /graph/state**: Retrieves checkpointed state for thread_id
- **Streaming events**: `state_update` events include `next`, `visited_nodes`, `message_count`

## Frontend-Backend Integration

### Authentication Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Firebase
    participant Backend
    
    User->>Frontend: Access application
    Frontend->>Firebase: Sign in (Google OAuth/Email)
    Firebase-->>Frontend: ID Token
    Frontend->>Frontend: Store token in memory
    
    User->>Frontend: Send request
    Frontend->>Backend: Request with Bearer Token
    Backend->>Firebase: Verify ID Token
    Firebase-->>Backend: User info (uid, email)
    Backend->>Backend: Extract user_id and email
    Backend-->>Frontend: Response
```

### Chat Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Backend
    participant LangGraph
    participant Supabase
    
    User->>Frontend: Send message + files
    Frontend->>Backend: POST /chat (FormData: message, thread_id, files)
    Backend->>Backend: Process files, extract text
    Backend->>Backend: Create initial state (SystemMessage + HumanMessage)
    Backend->>LangGraph: Execute graph with state
    LangGraph->>Supabase: Restore checkpoint (if thread_id exists)
    Supabase-->>LangGraph: Previous state
    LangGraph->>LangGraph: Process through agent state machine
    loop Streaming Events
        LangGraph-->>Backend: SSE event (content_chunk, state_update, etc.)
        Backend-->>Frontend: SSE event
        Frontend->>Frontend: Update UI (chat, graph visualization)
    end
    LangGraph->>Supabase: Save final checkpoint
    Backend-->>Frontend: graph_end event
    Frontend-->>User: Display final response
```

### Event Types

```mermaid
sequenceDiagram
    participant LangGraph
    participant Backend
    participant Frontend
    participant UI
    
    LangGraph->>Backend: graph_start
    Backend-->>Frontend: SSE: graph_start
    
    loop LLM Streaming
        LangGraph->>Backend: content_chunk
        Backend-->>Frontend: SSE: content_chunk
        Frontend->>UI: Update streaming text
    end
    
    LangGraph->>Backend: node_start (agent)
    Backend-->>Frontend: SSE: node_start
    Frontend->>UI: Highlight node
    
    LangGraph->>Backend: llm_start
    Backend-->>Frontend: SSE: llm_start
    
    LangGraph->>Backend: llm_end
    Backend-->>Frontend: SSE: llm_end
    
    LangGraph->>Backend: state_update (next: tool_node)
    Backend-->>Frontend: SSE: state_update
    Frontend->>UI: Update graph visualization
    
    LangGraph->>Backend: node_start (tool)
    Backend-->>Frontend: SSE: node_start
    
    LangGraph->>Backend: tool_start
    Backend-->>Frontend: SSE: tool_start
    
    LangGraph->>Backend: tool_end
    Backend-->>Frontend: SSE: tool_end
    
    LangGraph->>Backend: node_end (tool)
    Backend-->>Frontend: SSE: node_end
    
    LangGraph->>Backend: graph_end (final response)
    Backend-->>Frontend: SSE: graph_end
    Frontend->>UI: Display final response
```

**Event Types:**

- `graph_start`: Execution begins
- `content_chunk`: Incremental AI response text
- `node_start/end`: Graph node execution lifecycle
- `state_update`: Current execution state (next nodes, visited nodes, message count)
- `tool_start/end`: Tool execution events
- `llm_start/end`: LLM call lifecycle
- `graph_end`: Execution complete with final response
- `error`: Error event with details

### State Synchronization

- **Thread-based**: Each conversation uses unique `thread_id` (UUID)
- **Checkpointing**: State persisted after each node execution
- **Restoration**: Frontend fetches state on thread_id change to restore conversation history
- **Real-time**: SSE events provide live execution updates

## GCP Cloud Run Usage

### Infrastructure Components

```mermaid
graph TB
    subgraph GCP["Google Cloud Platform"]
        subgraph VPC["VPC Network"]
            Subnet[Subnet<br/>10.0.0.0/24]
            Router[Cloud Router]
            NAT[NAT Gateway<br/>Static Egress IP]
        end
        
        subgraph CloudRun["Cloud Run"]
            Service[Cloud Run Service]
            Container[FastAPI Container<br/>2 CPU, 2Gi Memory<br/>Concurrency: 160]
        end
        
        subgraph ArtifactRegistry["Artifact Registry"]
            DockerImage[Docker Image]
        end
        
        subgraph SecretManager["Secret Manager"]
            DopplerSecrets[Doppler Secrets JSON]
        end
    end
    
    subgraph External["External Services"]
        Supabase[Supabase PostgreSQL]
        VertexAI[Vertex AI]
    end
    
    GitHub[GitHub Actions] -->|Build & Push| DockerImage
    DockerImage -->|Deploy| Service
    Service --> Container
    Container -->|VPC Egress| NAT
    NAT -->|Outbound Traffic| VertexAI
    NAT -->|Outbound Traffic| Supabase
    Container -->|Read Secrets| DopplerSecrets
    Router --> NAT
    Subnet --> Router
    Service -.->|VPC Connector| VPC
```

**VPC Configuration:**

- Custom VPC with subnet (10.0.0.0/24)
- Cloud Router with NAT Gateway
- Static egress IP for outbound traffic
- VPC connector for Cloud Run service

**Cloud Run Service:**

- **Image**: Docker image from Artifact Registry
- **Resources**: 2 CPU, 2Gi memory
- **Scaling**: Min 0, max 10 instances
- **Concurrency**: 160 requests per instance
- **Timeout**: 300 seconds
- **Network**: VPC egress for all traffic

**Secrets Management:**

- Doppler secrets stored in GCP Secret Manager
- Secrets injected as `DOPPLER_SECRETS_JSON` environment variable
- Backend parses JSON and loads into environment at startup

**Database:**

- Supabase PostgreSQL (cloud-hosted)
- Connection pooling via asyncpg
- SSL connection with root certificate
- AsyncPostgresSaver uses shared connection pool

### Deployment Flow

```mermaid
sequenceDiagram
    participant Developer
    participant GitHub
    participant ArtifactRegistry
    participant Terraform
    participant CloudRun
    participant FastAPI
    
    Developer->>GitHub: Push to main branch
    GitHub->>GitHub: GitHub Actions workflow
    GitHub->>ArtifactRegistry: Build Docker image
    ArtifactRegistry-->>GitHub: Image pushed
    GitHub->>Terraform: Apply infrastructure changes
    Terraform->>CloudRun: Deploy new revision
    CloudRun->>FastAPI: Start container
    FastAPI->>FastAPI: Initialize connection pool
    FastAPI->>FastAPI: Initialize checkpointer
    FastAPI-->>CloudRun: Ready (health check)
    CloudRun-->>Developer: Deployment complete
```

### Key Cloud Run Features

- **Cold starts**: Startup CPU boost enabled for faster initialization
- **Auto-scaling**: Scales to zero when idle, up to 3 instances under load
- **VPC egress**: All outbound traffic (Vertex AI, Supabase) routes through VPC
- **IAM**: Unauthenticated access allowed (auth handled at application level)

## Data Flow

### Chat Execution Flow

```mermaid
flowchart TD
    UserMessage[User Message] --> FrontendPOST[Frontend: POST /chat FormData]
    FrontendPOST --> BackendAuth[Backend: Verify token, process files]
    BackendAuth --> CreateState[Backend: Create initial state<br/>SystemMessage + HumanMessage]
    CreateState --> AgentNode[LangGraph: Agent node processes message]
    AgentNode --> HasToolCalls{Has tool calls?}
    HasToolCalls -->|Yes| RouteToTool[LangGraph: Route to tool nodes]
    HasToolCalls -->|No| GenerateResponse[LangGraph: Generate final response]
    RouteToTool --> ToolExecute[LangGraph: Tool nodes execute]
    ToolExecute --> ToolResults[LangGraph: Return tool results]
    ToolResults --> AgentNode
    GenerateResponse --> StreamEvents[Backend: Stream SSE events<br/>content_chunk, state_update, etc.]
    StreamEvents --> FrontendUpdate[Frontend: Update UI<br/>chat messages, graph visualization]
    StreamEvents --> Checkpoint[Backend: Checkpoint final state to PostgreSQL]
    FrontendUpdate --> GraphEnd[Frontend: Receive graph_end event]
    Checkpoint --> GraphEnd
```

### State Persistence Flow

```mermaid
sequenceDiagram
    participant LangGraph
    participant Checkpointer
    participant Supabase
    participant FutureRequest
    
    LangGraph->>LangGraph: Node execution
    LangGraph->>LangGraph: State update<br/>messages, visited nodes
    LangGraph->>Checkpointer: Save checkpoint
    Checkpointer->>Supabase: Store state with thread_id
    Supabase-->>Checkpointer: Confirmation
    
    Note over FutureRequest,Supabase: Future request with same thread_id
    
    FutureRequest->>Checkpointer: Restore state for thread_id
    Checkpointer->>Supabase: Query checkpoint
    Supabase-->>Checkpointer: State data
    Checkpointer-->>LangGraph: Restored state
    LangGraph->>LangGraph: Continue from checkpointed state
```

## Component Structure

### Backend Module Dependencies

```mermaid
graph TD
    Main["app/main.py<br/>Entrypoint"] --> API["app/api/__init__.py<br/>FastAPI App"]
    API --> Routes["app/api/routes/"]
    Routes --> ChatRoute["chat.py<br/>Chat Endpoint"]
    Routes --> GraphRoute["graph.py<br/>Graph API"]
    
    ChatRoute --> GraphManager["graph_manager.py<br/>Graph Factory"]
    ChatRoute --> Streaming["streaming/async_events.py<br/>SSE Processing"]
    ChatRoute --> Checkpointer["checkpointer.py<br/>State Persistence"]
    
    GraphManager --> FlowGraph["flows/org/project/flow/graph.py<br/>LangGraph Definition"]
    FlowGraph --> Tools["flows/org/project/flow/chat/tools/<br/>Tool Implementations"]
    
    Checkpointer --> Database["database.py<br/>Connection Pool"]
    Streaming --> Observability["observability.py<br/>Metrics Tracking"]
    
    API --> Config["config.py<br/>Settings"]
    API --> Auth["auth.py<br/>Token Verification"]
```

### Frontend Module Dependencies

```mermaid
graph TD
    App[App.tsx<br/>Root Component] --> ChatInterface[ChatInterface.tsx<br/>Chat UI]
    App --> GraphView[GraphView.tsx<br/>Graph Visualization]
    App --> StatusWindow[StatusWindow.tsx<br/>Execution State]
    App --> ObservabilityWindow[ObservabilityWindow.tsx<br/>Metrics Display]
    App --> Sidebar[Sidebar.tsx<br/>Navigation]
    
    ChatInterface --> APIClient[utils/api.ts<br/>API Client]
    GraphView --> APIClient
    ObservabilityWindow --> APIClient
    
    ChatInterface --> Hooks[hooks/]
    Hooks --> UseAuth[useAuth.ts]
    Hooks --> UseObservabilityPolling[useObservabilityPolling.ts]
    
    GraphView --> GraphLayout[utils/graphLayout.ts<br/>Layout Algorithm]
    ChatInterface --> ErrorHandling[utils/errorHandling.ts]
```

### Backend Modules

- **`app/main.py`**: Application entrypoint, FastAPI app creation
- **`app/api/__init__.py`**: FastAPI app with lifespan, middleware, routes
- **`app/api/routes/chat.py`**: Chat endpoint with streaming
- **`app/api/routes/graph.py`**: Graph structure/state endpoints
- **`app/api/graph_manager.py`**: Thread-safe graph initialization/caching
- **`app/api/checkpointer.py`**: AsyncPostgresSaver management
- **`app/api/streaming/async_events.py`**: SSE event processing
- **`app/flows/{org}/{project}/{flow}/graph.py`**: LangGraph definition
- **`app/flows/{org}/{project}/{flow}/chat/tools/`**: Tool implementations

### Frontend Modules

- **`App.tsx`**: Root component with routing, auth, layout
- **`ChatInterface.tsx`**: Chat UI with SSE consumption
- **`GraphView.tsx`**: React Flow graph visualization
- **`StatusWindow.tsx`**: Execution state display
- **`ObservabilityWindow.tsx`**: Metrics polling and display
- **`utils/api.ts`**: API client with auth headers

## Additional Topics

### Error Handling

- Structured error responses with error types
- SSE error events for streaming failures
- Error boundary in React frontend
- Sentry integration for error tracking

### File Processing

- Supports multiple formats (docx, xlsx, pdf, etc.)
- Text extraction via document processing utilities
- Content appended to message before graph execution

### Thread Management

- Thread titles generated from first message
- Thread tracking in database (upsert on access)
- Thread history restoration from checkpoints

### Observability Metrics

- LLM usage (tokens, duration, TTFT)
- Embedding usage
- Bright Data usage (cost tracking)
- Per-execution and aggregated metrics
