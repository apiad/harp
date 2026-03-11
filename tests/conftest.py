import sys
from unittest.mock import MagicMock

# Mock pynput before it's imported by any code under test
# This prevents it from trying to connect to a display server in CI
mock_pynput = MagicMock()
sys.modules["pynput"] = mock_pynput
sys.modules["pynput.keyboard"] = mock_pynput.keyboard
