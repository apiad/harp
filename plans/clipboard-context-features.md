# Implementation Plan: Clipboard Context & Auto-Copy Features

## Objective
Extend Harp to include two new clipboard-based features:
1. **Command Mode with Clipboard Context**: When in command mode, securely read the user's clipboard and include the last `N` words (configurable, defaulting to 500) as context sent to the language model. When truncating, the system should attempt to cut at a sentence boundary or prepend `[...] ` if no boundary exists. This feature is enabled via a `--clipboard` flag.
2. **Copy Transcription to Clipboard**: After transcription is completed in any mode, copy the final transcribed text back to the system clipboard. This is enabled via a `--to-clipboard` flag.

## Architectural Impact
- **Dependencies**: Introduces `pyperclip` as a required dependency to handle cross-platform clipboard interactions.
- **Core Loop Performance**: Clipboard reads/writes using `pyperclip` are technically synchronous, but since they are instantaneous operations on small strings, they will not noticeably block the asyncio event loop.
- **Command Interfaces**: Adds three new optional parameters to the `start` CLI command (`--clipboard`, `--tokens`, `--to-clipboard`) and propagates them to the `HarpoDaemon` class.
- **LLM Integration**: Dynamically augments the `instruction` prompt sent to the LLM during command mode.

## File Operations
The following files require modifications:
- `pyproject.toml` (Dependency Update)
- `src/harp/__main__.py` (CLI Arguments Update)
- `src/harp/daemon.py` (Core Logic Update)

## Step-by-Step Execution

### Step 1: Add Dependency
1. Open `pyproject.toml`.
2. Locate the `dependencies` list under the `[project]` section.
3. Add `"pyperclip>=1.9.0"` to the list.

### Step 2: Update CLI Interface
1. Open `src/harp/__main__.py`.
2. Modify the `start` function definition to include the new arguments:
   ```python
   clipboard: bool = typer.Option(
       False, "--clipboard", "-c", help="Send clipboard content as context in command mode"
   ),
   tokens: int = typer.Option(
       500, "--tokens", "-n", help="Number of words to include from clipboard context"
   ),
   to_clipboard: bool = typer.Option(
       False, "--to-clipboard", "-C", help="Copy final transcription to clipboard"
   ),
   ```
3. Update the `HarpoDaemon` instantiation inside `start` to pass these new arguments.

### Step 3: Update Daemon State Initialization
1. Open `src/harp/daemon.py`.
2. Update the `HarpoDaemon.__init__` signature to accept `clipboard: bool = False`, `tokens: int = 500`, and `to_clipboard: bool = False`.
3. Save these values as instance variables (`self.clipboard = clipboard`, `self.tokens = tokens`, `self.to_clipboard = to_clipboard`).

### Step 4: Implement Clipboard Truncation Logic
1. Inside `src/harp/daemon.py`, add a new private helper method `_get_clipboard_context(self) -> str | None` to the `HarpoDaemon` class.
2. In this method:
   - Wrap the logic in a `try...except` block to gracefully handle missing `pyperclip` or clipboard read failures.
   - Call `pyperclip.paste()`. Return `None` if the clipboard is empty.
   - Tokenize the text while preserving whitespace using `import re` and `tokens = re.split(r'(\s+)', text)`.
   - Count backwards through `tokens` to isolate the text comprising the last `self.tokens` words.
   - Join the isolated tokens and strip leading whitespace (`lstrip()`).
   - Use a regex search like `re.search(r'[.!?]\s+([A-Z])', truncated)` to look for a sentence boundary within the truncated text.
   - If a boundary is found, return the substring starting from the captured uppercase letter.
   - If no boundary is found, prepend `[...] ` to the truncated string and return it.

### Step 5: Integrate Clipboard Context into Prompt
1. Inside the `_stop_recording` method of `src/harp/daemon.py`, locate the section where the `instruction` variable is defined.
2. If `self._is_command_mode` and `self.clipboard` are both `True`:
   - Call `self._get_clipboard_context()`.
   - If a valid context string is returned:
     - Log the exact context being sent using `self.console.print(...)`.
     - Append a new section to `instruction`: `f"

Here is some context from the user's clipboard to help you understand the command or what to operate on:
<context>
{context}
</context>"`

### Step 6: Implement Copy-to-Clipboard Post-Transcription
1. Still inside the `_stop_recording` method, locate the line where `transcription = response.full_text` is processed.
2. Below that, check if `self.to_clipboard` is `True`.
3. If `True`, use a `try...except` block:
   - Call `pyperclip.copy(transcription)`.
   - Print a success message (e.g., `"[bold green]Copied transcription to clipboard![/]"`) or an error message if it fails.

## Testing Strategy
1. **Unit Tests (Daemon & Utilities)**
   - Test `_get_clipboard_context` by mocking `pyperclip.paste()`. Provide sample texts with various sentence boundaries, exact word limits, and texts exceeding `self.tokens` to ensure the regex boundary logic behaves correctly.
   - Ensure the initialization works without breaking existing tests.
2. **Integration Tests (Stop Recording Logic)**
   - Update `test_stop_recording_success` (in `tests/test_daemon_async.py` and `tests/test_daemon.py`) to mock `pyperclip.copy` and `pyperclip.paste`.
   - Verify that the `instruction` passed to the mocked `api_client.transcribe` correctly incorporates the clipboard text when the appropriate flags are active.
3. **End-to-End Manual Testing**
   - Run `harp start -c -C -n 5`.
   - Copy a lengthy multi-sentence paragraph to the clipboard.
   - Trigger Command Mode, speak a query relying on clipboard content.
   - Observe the terminal to verify only the last 5 words (or sentence boundary) are sent.
   - After execution, verify the clipboard was successfully overwritten with the generated text.