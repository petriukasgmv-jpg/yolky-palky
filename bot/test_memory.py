import os
import subprocess
import sys
import tempfile


def test_memory_uses_external_data_dir():
    with tempfile.TemporaryDirectory() as data_dir:
        code = (
            "import memory; "
            "assert memory.DB_PATH.startswith(" + repr(data_dir) + "); "
            "print(memory.DB_PATH)"
        )
        env = os.environ.copy()
        env["BOT_DATA_DIR"] = data_dir
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=os.path.dirname(__file__),
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "userstate.db" in result.stdout
