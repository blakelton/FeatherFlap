# FeatherFlap Agent Handbook

Welcome to FeatherFlap’s collaborative workspace. This guide gives Codex, Claude, and other automation agents the shared context they need to work productively inside this repository. Treat it as your project briefing before taking on any task.

## Project Mission
- Deliver a resilient hardware diagnostics and monitoring stack for the FeatherFlap smart bird house running on a Raspberry Pi Zero 2 W.
- Validate connected peripherals (UPS, environmental sensors, cameras, PIR, RGB LED) through a FastAPI web UI and JSON API.
- Provide a Typer-powered CLI so the diagnostics server can be launched locally or on-device with minimal configuration.

## Stack At A Glance
- **Language**: Python 3.10+ (project uses PEP 660 editable installs via `pyproject.toml`).
- **Frameworks**: FastAPI for the web API, Typer for CLI, Pydantic v2 + `pydantic-settings` for configuration.
- **Runtime**: Uvicorn (standard extras) orchestrated by the CLI entry point.
- **Hardware Integrations (optional extras)**: `smbus2`, `RPi.GPIO`, `opencv-python`, `picamera2`.
- **Testing**: Pytest-based unit tests (`pytest -q`) with dependency-skipping logic for optional hardware libraries.

## Repository Layout
| Path | Description |
| --- | --- |
| `src/featherflap/` | Python package with configuration, hardware abstractions, and FastAPI server. |
| `src/featherflap/config.py` | Centralised settings object sourced from environment variables (prefix `FEATHERFLAP_`). |
| `src/featherflap/hardware/` | Hardware diagnostics framework (base classes, registry, concrete tests, device drivers). |
| `src/featherflap/server/` | FastAPI application factory, routes, and CLI glue. |
| `tests/` | Pytest suite validating app creation and dependency-guard behaviour. |
| `pyproject.toml` | Project metadata, dependency constraints, optional hardware extras, console script. |
| `README.md` | End-user setup instructions, hardware wiring overview, and operational guidance. |
| `test-output.xml` | JUnit-style artifact from the most recent test run (kept for reference). |

## Runtime Architecture Overview
1. **Configuration**: `AppSettings` (`config.py`) reads environment variables (with `.env` support) and caches settings via `get_settings()`.
2. **Application Factory**: `server/app.py:create_application()` builds the FastAPI instance, attaches CORS middleware, instantiates a `HardwareTestRegistry`, loads `default_tests()`, and wires API routes.
3. **Hardware Layer**:
   - `hardware/base.py` defines `HardwareTest` and `HardwareTestResult`.
   - `hardware/tests.py` implements diagnostic classes for system info, I²C bus, UPS, environment sensors, cameras, PIR, and RGB LED.
   - `hardware/power.py` & `hardware/sensors.py` provide low-level driver logic for the PiZ-UpTime HAT and AHT20/BMP280 combo.
   - Optional hardware-dependent modules guard imports and downgrade failures to `SKIPPED` results when dependencies are absent.
4. **Web/API Surface**: `server/routes.py` exposes HTML dashboard, JSON diagnostics endpoints, streaming camera routes, and async wrappers around the registry.
5. **CLI**: `server/cli.py` surfaces `featherflap serve` via Typer and dispatches to Uvicorn’s factory mode.

## Configuration & Environment Variables
All external configuration flows through `AppSettings` (env prefix `FEATHERFLAP_`). Common overrides:
- `FEATHERFLAP_HOST` / `FEATHERFLAP_PORT`: server binding.
- `FEATHERFLAP_RELOAD`, `FEATHERFLAP_LOG_LEVEL`: development toggles passed to Uvicorn.
- `FEATHERFLAP_ALLOWED_ORIGINS`: JSON list controlling CORS.
- `FEATHERFLAP_CAMERA_DEVICE`: default USB camera index.
- `FEATHERFLAP_PIR_PINS`, `FEATHERFLAP_RGB_LED_PINS`: GPIO pin configuration (BCM numbering).
- `FEATHERFLAP_I2C_BUS_ID`: Raspberry Pi I²C bus to probe (default `1`).
- `FEATHERFLAP_UPTIME_I2C_ADDRESSES`: JSON list of PiZ-UpTime addresses (defaults to `[0x48, 0x49, 0x4B]` unless `UPTIME_I2C_ADDR` env var overrides).
- `FEATHERFLAP_AHT20_I2C_ADDRESS`, `FEATHERFLAP_BMP280_I2C_ADDRESS`: sensor addresses.

Additional runtime inputs:
- `UPTIME_I2C_ADDR`: Optional single-address override (evaluated before configured list).

## CLI & Server Operations
- Launch diagnostics locally: `featherflap serve --host 0.0.0.0 --port 8000`.
- Direct Uvicorn invocation (factory mode): `uvicorn featherflap.server.app:create_application --factory`.
- The HTML dashboard renders buttons to invoke each hardware test via fetch calls to the REST API.
- JSON endpoints under `/api/tests` and `/api/status/*` are async wrappers calling the hardware suite in thread pools to keep the event loop non-blocking.

## Hardware Diagnostics Suite
`hardware.tests.default_tests()` returns the canonical sequence loaded into the registry:
- `SystemInfoTest`: platform summary and Python version.
- `I2CBusTest`: verifies `smbus` availability and bus accessibility.
- `PiZUpTimeTest`: probes configured UPS addresses, returning voltages and board temperature.
- `EnvironmentalSensorTest`: reads AHT20 (temp/humidity) and BMP280 (temp/pressure) with partial-success support.
- `PicameraTest`: initialises Picamera2 (skips when the module is missing).
- `UsbCameraTest`: captures a JPEG frame via OpenCV; skips cleanly if cv2/device unavailable.
- `PIRSensorTest`: reads configured GPIO inputs via `RPi.GPIO`.
- `RGBLedTest`: toggles LED pins sequentially to validate outputs.

### Implementing New Diagnostics
1. Subclass `HardwareTest`, populate `id`, `name`, `description`, `category`, and implement `run()` returning `HardwareTestResult`.
2. Use `HardwareStatus.OK/WARNING/ERROR/SKIPPED` consistently; provide structured `details` to aid the dashboard JSON view.
3. Register via `default_tests()` (or add selective registration elsewhere) and ensure asynchronous callers treat long-running work carefully (execute blocking I/O in threads).
4. Add targeted tests (mocks for hardware dependencies and failure modes) under `tests/`.

## API Surface Summary
- `GET /`: HTML dashboard.
- `GET /api/tests`: Metadata for all registered diagnostics.
- `POST /api/tests/{test_id}`: Execute a single test, returns JSON `result`.
- `POST /api/tests/run-all`: Execute entire suite, returns array plus aggregated status.
- `GET /api/status/environment`: Snapshot of sensor readings with status classification.
- `GET /api/status/ups`: Latest UPS telemetry.
- `GET /api/camera/frame`: Single JPEG frame (binary response).
- `GET /api/camera/stream`: MJPEG streaming response using `StreamingResponse`.

## Development Workflow for Agents
1. **Environment Setup**: `python -m venv .venv && source .venv/bin/activate && pip install -e .` (append `.[hardware]` on a Raspberry Pi with peripherals).
2. **Testing**: Run `python -m pytest` (defaults to `-q`). Tests respect optional-dependency availability by skipping.
3. **Linting/Formatting**: No enforced tooling yet—follow PEP 8, keep imports sorted, and add type hints consistent with existing code.
4. **Local Debugging**: Use the `/api/tests` routes or printed results to verify new diagnostics. For camera/streaming, rely on fallback SKIPPED paths when cv2 or hardware is missing.
5. **Documentation Updates**: Update `README.md` for user-facing changes; use this `AGENTS.md` for agent-facing conventions.
6. **Versioning**: Update `pyproject.toml` version when preparing releases; ensure `__init__.__version__` reflects the installed package.

## Working Without Hardware Access
- Diagnostics degrade gracefully—most tests return `SKIPPED` when optional modules are unavailable.
- Unit tests in CI should ensure defensive paths continue working without mocking the entire hardware stack.
- When stubbing new functionality, raise `CameraUnavailable`/`SMBusNotAvailable`-style errors to stay consistent with the UI expectations.

## Known Constraints & Gotchas
- Blocking hardware reads should run in worker threads (see `asyncio.to_thread` usage) to protect FastAPI’s event loop.
- Always clean up GPIO states after use (`GPIO.cleanup(pin)` pattern already established).
- UPS channel scaling relies on constants in `power.py`; be careful when changing conversion factors.
- Keep MJPEG streaming efficient: do not increase frame sizes/fps without considering Pi Zero resource limits.
- Ensure new dependencies respect the minimal footprint expected on Raspberry Pi OS.

---

# PR and Release Documentation Standards

## Creating PR Descriptions (with Base SHA)

When asked to create a PR description with a base commit SHA, follow this process:

### Analysis Steps
1. **Get Change Statistics**: `git diff <base_sha>..HEAD --stat`
2. **Identify File Changes**: `git diff <base_sha>..HEAD --name-only`
3. **Review Commit History**: `git log --oneline <base_sha>..HEAD`
4. **Component Analysis**: Focus on major component additions/removals/modifications

### PR Description Format
```markdown
# feat(component): brief description

## Summary
Concise overview of changes with key architectural improvements.

## Key Changes
- **Removed**: Component names with line counts
- **Added**: New components with line counts and module breakdown
- **Architecture**: Major structural improvements

## Technical Improvements
- **Code Quality**: Specific metrics (complexity reduction, duplication elimination)
- **Performance**: Memory usage, optimization details
- **Reliability**: Safety mechanisms, error handling improvements

## Features/Integration
- Key functionality additions
- System integration points
- Configuration updates

---
**Stats**: +added/-removed lines | **Quality**: Rating | **Metrics**: Key measurements
```

### Guidelines
- **Length**: Keep concise but comprehensive
- **Focus**: Emphasize architectural improvements and technical benefits
- **Statistics**: Include concrete metrics (lines changed, complexity improvements)
- **Audience**: Technical reviewers who need implementation details

## Creating Release Notes

When creating release notes sections, follow this format:

### Analysis Approach
1. **Focus on User-Facing Features**: What new capabilities were added?
2. **Categorize by Impact**: Features > Fixes > Chores
3. **Avoid Internal Details**: Don't mention bugs users never experienced
4. **Balance Categories**: Adjust based on actual work done (features-heavy vs fixes-heavy)

### Release Notes Format
```
Features:
    * User-facing functionality additions
    * New capabilities and enhancements
    * Major system improvements
    * Integration with external systems

Fixes:
    * Bug corrections that users might have experienced
    * Performance improvements
    * Reliability enhancements

Chores:
    * Internal refactoring and cleanup
    * Dependency updates
    * Configuration changes
    * Code organization improvements
```

### Guidelines
- **Features First**: Lead with new capabilities users can benefit from
- **Proportional Sections**: If work was 80% features, reflect that in the breakdown
- **User Perspective**: Write from the standpoint of someone using the system
- **Concrete Benefits**: Focus on tangible improvements rather than technical implementation details
- **No Internal Bugs**: Don't mention fixes for issues that were never released or experienced by users

---

# Code Quality Evaluation Requirements

**MANDATORY FOR ALL CODE CHANGES**: Whenever Claude makes ANY code changes to this project, you MUST automatically evaluate the finalized code for:

## Automatic Code Quality Assessment

### 1. Error Analysis
- **Runtime Errors**: Check for potential null pointer dereferences, buffer overflows, resource leaks
- **Logic Errors**: Validate conditional logic, loop termination, edge cases
- **Memory Management**: Verify proper allocation/deallocation, resource cleanup
- **Thread Safety**: Check for race conditions, proper synchronization

### 2-6. DRY/SOLID/Complexity/Memory/Embedded Principles (MANDATORY ENFORCEMENT)
- **DRY Violations**: Identical code blocks >3 lines (CRITICAL), magic numbers (use constants), repeated patterns (extract functions)
- **SOLID Compliance**: Single responsibility per function, extensible design, HAL abstractions, focused interfaces
- **Complexity Limits**: CC >10 (CRITICAL), CC >8 (HIGH), CC >5 (MEDIUM), max 4 nesting levels (embedded constraint)
- **ESP32 Memory**: Stack analysis (>1KB locals = HIGH PRIORITY), heap leak checking, static memory optimization, buffer reuse
- **Embedded Best Practices**: Real-time constraints, timeouts on blocking ops, power efficiency, HAL usage, robust error handling

### 7. Code Quality Standards
- **Error Handling**: All error conditions must be handled appropriately
- **Resource Management**: Proper cleanup of files, memory, handles
- **Consistent Naming**: Follow established naming conventions
- **Documentation**: Critical functions should have clear comments
- **Performance**: Identify potential bottlenecks or inefficiencies

## Quality Assessment Process

1. **Immediate Evaluation**: After completing code changes, automatically analyze the modified code
2. **Issue Identification**: Report specific problems with file names and line numbers
3. **Severity Classification**: Categorize issues as Critical, High, Medium, or Low priority
4. **Improvement Recommendations**: Provide specific actionable suggestions
5. **Overall Rating**: Assign letter grade (A-F) for overall code quality

## User-Requested Code Evaluation

**When the user asks for code to be "evaluated" or "assessed", perform comprehensive analysis using these specific criteria:**

### **PRIMARY EVALUATION CRITERIA (MANDATORY):**
1. **DRY Principles**: Identify code duplication, repeated patterns, magic numbers
   - Identical code blocks >3 lines: CRITICAL - extract to function immediately
   - Magic numbers: All numeric literals must be named constants (except 0, 1, -1)
   - Pattern abstraction: Similar initialization/validation/cleanup patterns → helper functions

2. **SOLID Principles**: Verify single responsibility, proper abstraction, interface design
   - Single Responsibility: Functions doing multiple things are CRITICAL violations
   - Dependency Inversion: MUST depend on abstractions (HAL layer), no direct hardware access
   - Interface Segregation: Large interfaces must be broken into focused, single-purpose interfaces

3. **Cyclomatic Complexity**: Calculate CC for all functions, flag >8 as HIGH, >10 as CRITICAL
   - **MANDATORY ANALYSIS**: For EVERY function, count all decision points (if, while, for, switch cases, &&, ||, ?:)
   - **Complexity Thresholds**: CC 1-5 (ACCEPTABLE), CC 6-8 (MEDIUM), CC 9-10 (HIGH), CC 11-15 (CRITICAL), CC >15 (EMERGENCY)
   - **Embedded Systems Limits**: Functions >10 CC are unacceptable for embedded systems
   - **Function Length Correlation**: Functions >50 lines likely exceed CC limits

4. **Embedded Memory Usage Analysis (CRITICAL FOR ESP32)**
   - **Stack Usage**: Large local arrays (>1KB) are CRITICAL - move to heap or static allocation
   - **Heap Usage**: Every malloc/calloc must have corresponding free, check for memory leaks in error paths
   - **Static Memory**: Large buffers should be justified, prefer const data in flash over RAM
   - **Buffer Management**: Reuse buffers when possible, avoid unnecessary copying

5. **Unused Code Detection**: Identify unused variables, functions, constants, includes, and dead code paths
   - **CRITICAL REQUIREMENT**: For EVERY declared function, verify actual usage beyond declaration/definition
   - **Verification Process**: Use grep/search tools to find ALL references to each function name across codebase
   - **Function Usage Criteria**: A function is "used" ONLY if it appears in actual function calls, not just headers/definitions
   - **Public API Verification**: Functions declared in public headers MUST be used somewhere in the codebase

6. **Function Return Type Design**: Analyze function signatures for meaningful return values
   - **CRITICAL REQUIREMENT**: For EVERY function returning bool, verify return value represents actual success/failure conditions
   - **Return Value Validation**: `return false` paths must be reachable and represent real failure conditions
   - **Design Principles**: Use `void` for operations that cannot fail, `bool` only for genuine success/failure conditions

7. **Function Length Analysis**: Systematic evaluation of function size and complexity correlation
   - **Length Thresholds**: 1-20 lines (ACCEPTABLE), 21-35 lines (MEDIUM), 36-50 lines (HIGH), 51-75 lines (CRITICAL), >75 lines (EMERGENCY)
   - **Embedded Systems Limits**: Functions >50 lines are problematic for embedded systems
   - **Complexity Correlation**: Functions >35 lines almost always exceed CC limits

8. **Cognitive Complexity**: Assess readability, mental load, nesting depth, boolean logic complexity
   - **MANDATORY NESTING ANALYSIS**: Count maximum nesting levels in each function
   - **Embedded Nesting Limits**: 1-2 levels (ACCEPTABLE), 3 levels (MEDIUM), 4 levels (HIGH), 5+ levels (CRITICAL)
   - **Mental Load Factors**: Complex boolean conditions, mixed abstraction levels
   - **Readability Test**: If function requires scrolling to understand, cognitive complexity is too high

9. **Embedded Best Practices**: Memory usage, real-time constraints, power efficiency, HAL usage
   - **Real-Time Constraints**: Avoid blocking operations in time-critical paths, use timeouts
   - **Power Efficiency**: Minimize CPU-intensive operations, use efficient algorithms
   - **Hardware Abstraction**: No direct register access outside HAL, platform-specific code isolated

10. **Code Quality Standards**: Problems/Issues, formatting, resource management
    - **Error Handling**: All error conditions must be handled appropriately
    - **Resource Management**: Proper cleanup of files, memory, handles
    - **Consistent Naming**: Follow established naming conventions

### **EVALUATION OUTPUT FORMAT:**
- Start with overall letter grade (A-F)
- Provide section for each primary criterion above
- List specific issues with file:line references
- Include severity classification (CRITICAL/HIGH/MEDIUM/LOW)
- Give actionable recommendations for improvements
- Include embedded-specific memory/performance analysis

### **UNIFIED EVALUATION STANDARD:**
**CRITICAL**: All evaluations and assessments use the SAME comprehensive criteria listed above. Whether triggered by:
- User requesting "evaluate [component]" or "assess [code]"
- Automatic evaluation after code changes
- Quality assessment during development

ALL must include the complete 10-point analysis (DRY, SOLID, complexity, memory, unused code, function design, length, cognitive complexity, embedded practices, quality standards) with the same output format and severity classification.

### **MANDATORY POST-CHANGE ASSESSMENT:**
After ANY code modifications, Claude MUST perform the full 10-point evaluation of the final changes before marking tasks complete. No exceptions - this ensures consistent quality standards across the entire project.

## Example Quality Report Format

```
## Code Quality Analysis - [Component Name]
Overall Rating: A- (Excellent with minor improvements)

### Embedded Memory Analysis:
- Stack Usage: 2.1KB worst-case (acceptable for ESP32)
- Heap Allocations: 3 malloc/free pairs (all properly paired)
- Static Memory: 1.5KB global buffers (justified for performance)
- Large Local Variables: 1 function with 800-byte array (recommend heap allocation)

### Complexity Metrics:
- Max Cyclomatic Complexity: 8 (acceptable, target <10)
- Max Cognitive Complexity: 12 (review recommended)
- Functions >50 lines: 2 (review recommended)
- Max Nesting Depth: 3 levels (within embedded limits)

### DRY/SOLID Analysis:
- Code Duplication: 8% (within target <10%)
- SRP Violations: 0 (excellent)
- Magic Numbers: 2 found (need constants)

### Unused Code Analysis:
- Unused Variables: 0 (clean)
- Unused Functions: 1 helper function (consider removal)
- Unused Constants: 2 defined but not referenced
- Dead Code Paths: 0 (all branches reachable)

### Issues Found:
**CRITICAL:**
- file.c:456 - Function exceeds complexity limit (CC=12, Cognitive=15)

**HIGH Priority:**
- file.c:123 - Code duplication in error handling (DRY violation)
- file.c:234 - Large stack array should use heap allocation

**Medium Priority:**
- file.c:345 - Missing timeout on blocking operation
- file.c:567 - Direct hardware access bypasses HAL

**Low Priority:**
- file.c:789 - Magic number should be constant

### Recommendations:
1. CRITICAL: Break down complex function into smaller components
2. Extract common error handling into helper function
3. Move large local array to heap with proper cleanup
4. Add timeout to blocking filesystem operation
5. Use HAL abstraction for hardware access
6. Define symbolic constants for threshold values

### ESP32 Embedded Considerations:
- Real-time constraints: Met (no blocking in critical paths)
- Power efficiency: Good (efficient algorithms used)
- Memory footprint: Acceptable (within ESP32 constraints)
- Hardware abstraction: 95% compliant (1 violation found)
```

## When to Apply - Universal Requirements

- **ALL code modifications**: Every time Claude creates, edits, or refactors ANY code in this project
- **ANY component**: Applies to all components (app_specific, internal, external, generated)
- **ANY language**: C/C++, Python, CMake, YAML, configuration files, etc.
- **Before task completion**: Quality analysis must occur before marking ANY coding task as complete
- **Multi-file changes**: Evaluate all modified files collectively across the entire project
- **Integration points**: Pay special attention to interfaces between ANY components
- **Build system changes**: Include CMake, configuration, and build script modifications
- **Documentation updates**: Apply quality standards to technical documentation

## Scope: Project-Wide Application

This quality evaluation requirement applies to:
- Core firmware components (WiFi module, MCU communication, cloud connectivity)
- Build system modifications (CMakeLists.txt, configuration files)
- Data model and shadow generation scripts
- Test code and BDD scenarios
- Configuration files (YAML, JSON, etc.)
- Documentation with code examples

**No Exceptions**: This ensures consistent, maintainable, and high-quality code throughout the ENTIRE project, regardless of the specific component or task being worked on.

