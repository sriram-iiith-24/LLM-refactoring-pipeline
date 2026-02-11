# Automated Code Refactoring Pipeline: Technical Documentation


## 1. System Architecture

### 1.1 High-Level Overview

The pipeline follows a modular, event-driven architecture:

```
[File Scanner] → [Smell Detector] → [Refactorer] → [Git Handler] → [Pull Request]
                        ↓                                  ↓
                 [State Manager] ←→ [Feedback Loop]
```

**Key Architectural Principles**:

1. **Modularity**: Each component has a single responsibility and well-defined interfaces
2. **Stateful Execution**: Progress persists across runs, enabling resumability and retry logic
3. **Rate Limit Awareness**: Built-in throttling and key rotation prevent API quota exhaustion
4. **Fail-Safe Design**: Errors in individual files do not halt pipeline execution
5. **Human-in-the-Loop**: All changes require PR approval before merging

### 1.2 Data Flow

**Phase 1: File Discovery**
- Scan repository based on configured mode (all, large, changed, package, manual)
- Apply filters (minimum line count, excluded directories)
- Respect MAX_FILES_PER_RUN limit to prevent resource exhaustion

**Phase 2: Smell Detection**
- Load file content and optional contextual files (imports, dependencies)
- Send to Gemini Flash for rapid smell detection
- Parse structured JSON response containing smell types, severity, locations

**Phase 3: Refactoring Decision**
- Analyze smell complexity and multi-file impact
- **Path A (Simple)**: Single-file refactoring with code generation
- **Path B (Complex)**: Multi-file refactoring with suggestion-only mode

**Phase 4: Artifact Creation**
- Generate refactored code or markdown suggestions
- Save original, refactored, and metadata files
- Update state manager with completion status

**Phase 5: Integration**
- Create Git branch for each refactored file
- Commit changes with descriptive messages
- Generate pull request with smell summary and impact analysis
- Different PR templates for code changes vs. suggestions

---

## 2. Core Components

### 2.1 File Scanner

**Purpose**: Intelligent file discovery based on configurable strategies

**Scan Modes**:

- **all**: Process every Java file in the repository
- **large**: Target files exceeding SCAN_MIN_LINES threshold (typically 300+ lines)
- **changed**: Analyze files modified within SCAN_CHANGED_HOURS window
- **package**: Focus on specific Java package patterns
- **manual**: Process explicitly specified file list

**Technical Implementation**:

The scanner uses recursive directory traversal with early termination for excluded paths (test directories, build artifacts, node_modules). File filtering occurs at discovery time to minimize memory overhead. The scanner yields files lazily to support streaming processing of large repositories.

**Configuration**:

Scan behavior is controlled via environment variables, allowing runtime adjustment without code changes. This enables different scanning strategies for development (manual, changed) vs. production (large, all) environments.

### 2.2 Smell Detector

**Purpose**: Identify refactoring opportunities using LLM-augmented pattern matching

**Detection Strategy**:

The detector employs a hybrid approach:

1. **Static Heuristics**: Line count, method count, cyclomatic complexity indicators
2. **LLM Reasoning**: Gemini Flash analyzes semantic relationships, naming patterns, responsibility violations

**Detected Smell Types**:

- God Class / Brain Class
- Long Method
- Feature Envy
- Data Clumps
- Shotgun Surgery
- Primitive Obsession
- Refused Bequest

**Response Format**:

The detector requests structured JSON from Gemini containing:

- `has_smells` (boolean): Whether any issues were detected
- [smells](file:///home/sriram/Documents/Spring-2026/SE/Project/agentic-pipeline/models/gemini_client.py#151-218) (array): List of smell objects with type, severity, location, description

**Contextual Awareness**:

Optionally loads related files (imports, parent classes, interfaces) to provide Gemini with broader context for more accurate detection. This feature can be toggled based on API quota availability.

### 2.3 Code Refactorer

**Purpose**: Generate semantically correct refactorings or provide expert guidance

**Dual-Mode Operation**:

**Mode A: Direct Code Generation**

- For single-file refactorings with no external dependencies
- Gemini Pro generates complete, compilable replacement code
- Maintains all existing functionality and method signatures
- Preserves comments, licensing headers, package declarations

**Mode B: Suggestion-Only (Comment-Only)**

- Triggered when multi-file changes are required
- Detects cross-file dependencies that would break if modified in isolation
- Returns markdown document with step-by-step refactoring guidance
- Prevents generation of incomplete or breaking code

**Multi-File Impact Detection**:

The refactorer prompts Gemini to first analyze whether refactoring requires changes to:

- Callers of modified methods
- Subclasses or implementing classes
- Configuration files or dependency injection setups
- Test files

If multi-file impact is detected, the system automatically switches to suggestion mode.

**Quality Assurance**:

Generated code undergoes validation:

- Syntax completeness check (balanced braces, proper class structure)
- Comparison of public API surface (method signatures preserved)
- Length sanity check (refactored code should not be drastically shorter, indicating truncation)

### 2.4 Git Handler

**Purpose**: Integrate refactorings into version control workflow

**Branch Strategy**:

Creates isolated branches per refactoring:

- Naming pattern: `refactor/{filename}-{smell-type}-{timestamp}`
- Enables parallel review of multiple refactorings
- Allows selective merging or rejection without conflicts

**Pull Request Generation**:

**For Code Changes**:

- Title: "Automated Refactoring: Fix [Smell Types]"
- Body: Markdown summary of detected smells with severity levels
- Labels: "refactoring", "automated", smell-specific tags
- Reviewers: Assigned based on CODEOWNERS or configuration

**For Suggestions**:

- Title: "[Suggestions] Refactoring Guidance for [Filename]"
- Body: Complete suggestion document with reasoning
- Marked as draft PR to prevent accidental merging
- Labels: "needs-manual-implementation", "guidance"

**Conflict Handling**:

Before creating PR, checks for existing open refactoring PRs for the same file to prevent duplicates. Stale branches are automatically cleaned up after configurable timeout.

### 2.5 State Manager

**Purpose**: Provide resilience, progress tracking, and analytics

**State Persistence**:

Maintains JSON state file with:

- Per-file processing status (pending, in-progress, completed, failed)
- Retry counts and error histories
- Timestamps for rate limiting and scheduling
- Cumulative statistics

**Key Features**:

**Resumability**:

If pipeline execution is interrupted (API quota exhausted, system restart, timeout), the next run resumes from the last successful checkpoint. Files already processed are skipped unless explicitly reset.

**Retry Logic**:

Failed files are automatically retried up to MAX_RETRIES times with exponential backoff. Persistent failures (e.g., unparseable code, API errors) are marked as permanently failed after retry exhaustion.

**Progress Tracking**:

Provides real-time visibility into:

- Total files scanned vs. processed
- Success/failure rates
- Average processing time per file
- API quota consumption estimates

**Analytics**:

Tracks refactoring patterns:

- Smell type breakdown (which smells are most common)
- Code vs. suggestion mode split
- PR merge rates (requires manual webhook integration)
- Cost metrics (API calls, tokens consumed)

**Configuration**:

State management can be disabled for stateless execution modes (testing, one-off runs). State file location is configurable for multi-environment deployments.

---

## 3. Configuration Management

### 3.1 Configuration File

The [config.py](file:///home/sriram/Documents/Spring-2026/SE/Project/agentic-pipeline/config.py) module centralizes all configurable parameters, loaded from environment variables for deployment flexibility.

**API Configuration**:

- `GEMINI_KEYS`: List of API keys for rotation and failover
- `GEMINI_RPM`: Rate limit threshold (requests per minute)
- `GITHUB_TOKEN`: Personal Access Token for repository operations
- `GITHUB_REPO`: Target repository in owner/repo format

**File Discovery**:

- `SCAN_MODE`: Discovery strategy (all, large, changed, package, manual)
- `SCAN_MIN_LINES`: Minimum file size for large mode
- `SCAN_CHANGED_HOURS`: Time window for changed mode
- `SCAN_PACKAGE`: Package pattern for package mode
- `MANUAL_FILES`: Comma-separated file list for manual mode
- `MAX_FILES_PER_RUN`: Batch size limit
- `EXCLUDE_DIRS`: Directories to skip during scanning

**State Management**:

- `STATE_FILE`: Path to persistent state JSON
- `MAX_RETRIES`: Retry attempts for failed files
- `ENABLE_STATE_MANAGEMENT`: Toggle for stateless mode

**Path Configuration**:

- `LOCAL_REPO_PATH`: File system path to cloned repository
- `OUTPUT_DIR`: Directory for refactoring reports and artifacts

### 3.2 Runtime Customization

**Development vs. Production**:

Development environments typically use:

- `SCAN_MODE=manual` with specific test files
- `MAX_FILES_PER_RUN=3` for quick iteration
- `ENABLE_STATE_MANAGEMENT=false` for clean slate testing

Production GitHub Actions use:

- `SCAN_MODE=large` for broad coverage
- `MAX_FILES_PER_RUN=20` for meaningful progress per run
- `ENABLE_STATE_MANAGEMENT=true` for incremental processing

**Deployment Flexibility**:

All configuration comes from environment variables, enabling:

- Different strategies per branch or repository
- A/B testing of detection prompts
- Gradual rollout (start with manual, expand to large)
- Emergency throttling by reducing MAX_FILES_PER_RUN

---

## 4. Intelligent Refactoring: Suggestions vs. Fixes

### 4.1 Decision Criteria

The pipeline employs a decision tree to determine refactoring mode:

**Automated Code Generation (Fixes)**:

Conditions:

- Refactoring is confined to a single file
- No changes to public method signatures required
- No impact on external callers or subclasses
- Estimated output token count under 6000 (prevents truncation)

Benefits:

- Immediate, actionable improvements
- Fully automated workflow
- Guaranteed syntactic correctness

**Suggestion-Only Mode**:

Conditions:

- Refactoring requires multi-file coordination
- Public API changes affect unknown number of callers
- High complexity with multiple alternative approaches
- File size exceeds safe token limit

Benefits:

- Prevents generation of incomplete or breaking changes
- Provides expert guidance without risk
- Enables informed human decision-making

### 4.2 Multi-File Impact Detection

**Prompt Engineering**:

The Gemini prompt explicitly instructs the model to analyze dependencies:

```
FIRST, analyze if this refactoring requires changes to:
- Other files that call methods in this class
- Subclasses or implementations
- Configuration or test files

If multi-file changes are needed, return SUGGESTIONS.
Otherwise, return REFACTORED CODE.
```

**Detection Heuristics**:

The system looks for indicators of external dependencies:

- Public methods with broad visibility
- Classes implementing interfaces or extending parents
- Heavy use of static methods (suggests utility classes)
- Presence of annotations (@Inject, @Autowired, @Override)

**Response Parsing**:

The refactorer checks for a sentinel marker:

- `=== REFACTORING SUGGESTIONS ===` indicates suggestion mode
- `=== REFACTORED CODE ===` indicates code generation mode

This explicit signaling ensures deterministic mode detection.

### 4.3 Suggestion Format

Suggestion-mode outputs are structured markdown documents containing:

**Problem Analysis**:

- Identified smells with specific examples from the code
- Root cause explanation (why these smells emerged)
- Impact assessment (how smells affect maintainability)

**Proposed Solution**:

- High-level refactoring strategy (e.g., Extract Class, Extract Method)
- Step-by-step implementation guide
- Affected files and components

**Implementation Notes**:

- Potential gotchas and edge cases
- Testing recommendations
- Performance considerations

**Alternative Approaches**:

- Multiple refactoring paths when applicable
- Trade-offs between different solutions

---

## 5. Pull Request Management

### 6.1 PR Structure

**Code Change PRs**:

- Single commit per PR for clean history
- Commit message format: `refactor: Fix [SmellType] in [FileName]`
- PR body includes:
  - Detected smell summary table
  - Lines affected
  - Refactoring strategy applied
  - Estimated impact (reduced complexity metrics)

**Suggestion PRs**:

- Commit contains markdown guidance document
- PR marked as draft to prevent accidental merge
- Body contains condensed summary with link to full guidance
- Labeled for easy filtering

### 6.2 Review Workflow

**Automated Checks**:

Future integration points for pre-merge validation:

- Compile check (ensure code builds)
- Unit test execution (regression detection)
- Static analysis re-run (verify smell elimination)
- Code coverage comparison

**Human Review**:

Reviewers assess:

- Semantic correctness (logic preservation)
- Code style adherence
- Naming appropriateness
- Integration impact

---

## 6. GitHub Actions Integration

### 6.1 Workflow Design

The pipeline runs as a scheduled GitHub Action with the following job architecture:

**Trigger Mechanisms**:

1. **Scheduled Execution**: Cron schedule (e.g., daily at midnight UTC)
2. **Manual Dispatch**: Workflow run button for on-demand execution
3. **Webhook Trigger** (future): On push to main branch or PR creation

**Job Steps**:

1. **Checkout Pipeline Code**: Fetch the latest pipeline scripts
2. **Checkout Target Repository**: Clone the Java codebase to analyze
3. **Setup Python**: Install Python 3.10 with required dependencies
4. **Configure Environment**: Inject secrets into .env file
5. **Execute Pipeline**: Run main.py with configured parameters
6. **Upload Artifacts**: Persist refactoring reports and state file
7. **Error Notification**: Create GitHub issue on failure

### 6.2 Secret Management

**Required Secrets**:

- `GEMINI_KEY_1`, `GEMINI_KEY_2`: API keys for LLM access
- `GH_PAT`: Personal Access Token with repo and workflow scopes


---

## 7. Extensibility and Future Enhancements

### 7.1 Multi-LLM Architecture

The pipeline currently uses a single LLM provider (Gemini), but the architecture can be extended to support multiple LLM providers simultaneously. This enhancement would enable ensemble smell detection where multiple models like Gemini, Claude, and GPT-4 analyze the same code and their results are aggregated using consensus voting. When models disagree on detected smells, these cases can be flagged for human review, improving overall detection accuracy by combining the strengths of different models. Additionally, specialized models could be assigned to specific tasks: Gemini for Java and Spring-specific refactorings, Claude for documentation improvements, and GPT-4 for complex architectural refactorings.

### 7.2 Pre-Merge Testing

Currently, pull requests are created without running automated tests on the refactored code. A valuable enhancement would integrate test execution directly into the pipeline workflow. After generating refactored code, the system would apply changes to a temporary branch and execute the project's test suite using build tools like Maven or Gradle. Pull requests would only be created if all tests pass, ensuring that refactorings don't introduce regressions. For efficiency, the system could implement test impact analysis to identify and run only the subset of tests that exercise the refactored code. This approach provides faster feedback while maintaining quality assurance. As an additional benefit, the pipeline could leverage LLMs to generate test cases for methods lacking coverage, including these tests in the refactoring pull request to improve overall codebase reliability.

### 7.3 Static Analyzer Integration

The detection phase can be enhanced by incorporating established static analysis tools like SonarQube, PMD, and Checkstyle. These tools excel at identifying specific issues such as high cyclomatic complexity, code duplication, unused variables, and security vulnerabilities through rapid, deterministic analysis. The pipeline would first run static analysis to flag problematic files, then pass these findings to the LLM for deeper semantic analysis and refactoring strategy recommendation. This hybrid approach offers several advantages: static analysis is near-instantaneous compared to LLM calls, API costs are reduced since only flagged files require LLM processing, and the combination provides both precise technical metrics and intelligent remediation guidance. This separation of detection and remediation concerns allows each tool to operate in its area of strength.

### 7.4 Incremental Refactoring

For exceptionally large classes exceeding 1000 lines, the pipeline faces token limit constraints that prevent processing the entire file at once. A solution to this challenge involves implementing method-level refactoring capability, where individual long methods are extracted and refactored independently across multiple pull requests. The system would track refactoring progress for each class, systematically working through problematic methods. For God Classes, the pipeline could identify natural seams or responsibility boundaries within the class and propose Extract Class refactorings with detailed migration guides. This incremental approach breaks down overwhelming refactoring tasks into manageable, reviewable chunks that can be safely merged over time.

### 7.5 Custom Smell Definitions

While the pipeline includes a core set of well-known design smells, different organizations often have domain-specific code quality standards. The architecture can be extended to support custom smell definitions through configuration files where teams define organization-specific issues such as missing null checks, lack of input validation, or violation of internal architectural patterns. These custom definitions would include the smell name, description, severity level, and tailored detection prompts. The pipeline would load these definitions at runtime and incorporate them into the smell detection phase, enabling enforcement of company-specific coding standards alongside universal design principles.

---

## 8. Vector Database Approach for Large Codebases

### 8.1 Challenge: Cross-File Context

**Current Limitation**:

The pipeline processes files in isolation, missing dependencies:

- Refactoring a method may break callers in other files
- Extracting a class requires updating all references
- Interface changes ripple through implementations

**Root Cause**:

LLM context windows, while large, cannot accommodate entire codebases (10,000+ files). Loading every related file is infeasible.

### 8.2 Solution: Semantic Code Search

**Vector Database Integration**:

Use ChromaDB or Pinecone to create semantic embeddings of code:

**Indexing Phase**:

1. Parse entire codebase into code chunks (methods, classes)
2. Generate embeddings using code-specialized models (CodeBERT, StarCoder)
3. Store in vector database with metadata (file path, class name, method signature)

**Query Phase**:

When refactoring a file:

1. Generate embedding of the file/method being refactored
2. Perform similarity search in vector DB
3. Retrieve top-k most semantically related code chunks
4. Include these in LLM context as "related files"

**Benefits**:

- Discovers dependencies not captured by static imports
- Finds similar patterns across codebase for consistent refactoring
- Enables whole-codebase analysis within token budgets

### 8.3 Architecture with Vector DB

**Enhanced Pipeline Flow**:

```
[File Scanner] → [Embedder] → [Vector DB]
                                    ↓
[Smell Detector] ← [Context Retriever] ← [Vector DB]
       ↓
[Refactorer] ← [Impact Analyzer] ← [Vector DB]
```

**New Components**:

**Code Embedder**:

- Runs during initial setup or on codebase changes
- Chunks code into logical units (method, class, file)
- Generates embeddings using CodeBERT or similar
- Updates vector DB with new/changed code

**Context Retriever**:

- Given a file to refactor, queries vector DB for similar code
- Filters by distance threshold (only highly related code)
- Ranks by relevance (recent changes weighted higher)
- Returns compact summary of related files

**Impact Analyzer**:

- After generating refactored code, searches for potential impacts
- Queries vector DB for code calling the refactored methods
- Estimates blast radius of changes
- Switches to suggestion mode if impact is large

### 8.4 Embedding Strategy

**Granularity Options**:

**Method-Level**:

- Fine-grained similarity detection
- Large index size (high storage cost)
- Best for identifying duplicate logic

**Class-Level**:

- Balanced granularity
- Moderate index size
- Good for dependency discovery

**File-Level**:

- Coarse similarity
- Small index size
- Fast queries, less precise

**Recommended**: Hybrid approach with class-level primary index and method-level secondary index for God Classes.

### 8.5 Implementation Details

**Vector DB Selection**:

**ChromaDB** (Recommended):

- Lightweight, embeddable Python library
- No external service required
- Persistent storage on disk
- Ideal for small to medium codebases (up to 50k files)

**Pinecone**:

- Managed cloud service
- Highly scalable (millions of vectors)
- Low-latency queries
- Best for enterprise-scale codebases

**Embedding Model**:

**CodeBERT**:

- Microsoft model specifically trained on code
- Understands code semantics, not just syntax
- 768-dimensional embeddings

**StarCoder**:

- Larger model with better code understanding
- Higher-dimensional embeddings (4096)
- Slower but more accurate

**Query Performance**:

- Similarity search: 10-50ms per query
- Top-10 retrieval: <100ms
- Negligible impact on pipeline execution time

### 8.6 Retrieval-Augmented Refactoring

**Workflow**:

1. **Detect Smells**: Run standard smell detection on target file
2. **Retrieve Context**: Query vector DB for top-10 similar code chunks
3. **Analyze Patterns**: LLM analyzes if similar code has been refactored before
4. **Apply Consistent Strategy**: Refactor using same approach as similar code
5. **Validate Impact**: Search for calling code, warn if changes break callers

**Example Scenario**:

Refactoring `UserService.java`:

1. Vector search finds `OrderService.java`, `ProductService.java` (similar patterns)
2. LLM sees that `OrderService` was previously refactored to extract a Manager class
3. LLM applies same Extract Class pattern to `UserService`
4. Vector search finds 15 classes calling `UserService` methods
5. Pipeline switches to suggestion mode, listing all 15 affected classes

**Benefits**:

- Consistent refactoring patterns across codebase
- Discovery of hidden dependencies
- Reduced false positives (similar code vetted by vector similarity)

### 8.7 Scalability Analysis

**Codebase Size vs. Approach**:

| Codebase Size | Recommended Approach | Rationale |
|---------------|----------------------|-----------|
| < 1,000 files | File-by-file (current) | Full context fits in memory |
| 1,000 - 10,000 files | Vector DB (class-level) | Balance of accuracy and cost |
| 10,000 - 100,000 files | Vector DB (method-level) | Fine-grained context required |
| > 100,000 files | Pinecone + Distributed Processing | Managed scaling needed |


---



## 9. Conclusion

This automated refactoring pipeline represents a system for continuous code quality improvement. By combining LLM capabilities with robust engineering practices (state management, rate limiting, intelligent decision-making), it achieves autonomous operation while maintaining safety through human-in-the-loop PR reviews.

The architecture is intentionally modular and extensible, supporting future enhancements such as multi-LLM ensembles, pre-merge testing, static analyzer integration, and vector database context retrieval. These extensions enable the pipeline to scale from small projects to enterprise codebases while maintaining accuracy and efficiency.