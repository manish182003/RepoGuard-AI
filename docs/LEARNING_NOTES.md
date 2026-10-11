# RepoGuard AI — Interview & Technical Learning Notes

These educational notes summarize key design decisions, backend engineering concepts, and agentic AI patterns implemented in RepoGuard AI for technical interview preparation.

---

## 1. LLM Abstraction & Token Budgeting (`app/llm/`)

### Key Concept: Why abstract the LLM provider?
Hardcoding LLM SDKs (like `AsyncOpenAI` or `Groq`) directly inside agent logic tightly couples business logic to provider implementation details.
By creating `BaseLLMProvider`, we achieve:
1. **Testability**: We can substitute `GroqProvider` with `FakeLLMProvider` during pytest runs without making live network calls or requiring API keys.
2. **Error Normalization**: HTTP 429 / TPM limits are translated into domain exceptions (`LLMRateLimitError`), allowing API routes to respond with appropriate HTTP status codes (e.g. 429 Too Many Requests).
3. **Token Budget Defense**: Token estimation (`estimate_tokens`) caps character counts before sending prompts, preventing context window overflow and TPM budget exhaustion.

---

## 2. Controlled Tool Execution & Safety (`app/tools/registry.py`)

### Key Concept: Why not give an LLM agent arbitrary shell or code execution?
Giving LLMs unrestricted access to shell execution (`eval()`, `exec()`, raw bash) exposes the host system to security vulnerabilities and prompt injection attacks.

### How `ToolRegistry` enforces safety:
- **Allowlist of typed functions**: Only explicitly registered tool functions can be called.
- **Schema Validation**: Arguments provided by the LLM are checked against parameter schemas.
- **Output Bounding**: Tool outputs are truncated to `max_output_chars` (4,000 chars) to prevent prompt bloat.

---

## 3. Autonomous Multi-Turn Agent Loop (`app/agents/loop.py`)

### Key Concept: How does tool calling work under the hood?
1. **Initial Prompt**: The system prompt describes registered tools as JSON schemas and instructs the model to return JSON action calls (`call_tool` or `final_result`).
2. **Execution**: If `action == "call_tool"`, Python code validates the parameters, executes the registered function, and formats the output into a user message for the next turn.
3. **Termination**: The loop runs until `action == "final_result"` or `max_iterations` (default: 5) is reached.

---

## 4. False-Positive Rejection & Complete File Syntax Validation (`app/tools/hypothesis_validator.py`)

### Key Concept: The "Truncated Excerpt Hallucination" Problem
When LLMs receive truncated code excerpts (e.g., first 50 lines of a file), they often falsely report syntax defects because they cannot see closing parentheses or braces later in the file.

### Solution:
Before accepting a syntax defect hypothesis, `HypothesisValidator` parses the **complete, untruncated source file** using Python's `ast.parse()`. If `ast.parse()` succeeds without a `SyntaxError`, the claimed syntax defect is marked **`rejected`**.

---

## 5. Finding Lifecycle & State Machines (`app/tools/finding_manager.py`)

### State Machine Transitions:
- `candidate`: Raw hypothesis proposed by rule engine or LLM.
- `investigating`: Agent actively gathering evidence.
- `supported`: Verified against line bounds, syntax, and issue deduplication.
- `fixed`: Minimal patch generated and verified with AST syntax check.
- `validated`: Verified through test suite execution.
- `rejected`: Proven false or invalid.

Deterministic deduplication keys (`sha256(path:line:rule)`) prevent duplicate findings.

---

## 6. Security & Policy Enforcement (`app/core/policy.py` & `app/tools/github_pr.py`)

### Security Rules:
1. **Human Approval Requirement**: High-risk actions (`open_pr`, `create_branch`) return `allowed=False` unless `human_approved=True` is provided in the request payload.
2. **Secret Redaction**: Regex patterns strip API keys (`ghp_`, `gsk_`, `sk-`) from all text outputs.
