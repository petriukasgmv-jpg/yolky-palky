import os
import subprocess
import sys
import tempfile


def _run_memory_check(data_dir):
    code = (
        "from types import SimpleNamespace as S; "
        "import memory; "
        "m=S(from_user=S(id=7, first_name='Test', username='test'), chat=S(id=7)); "
        "memory.ensure_user(m); "
        "memory.set_budget(7, 500); "
        "assert memory.get_user(7)['budget_euro'] == 500; "
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
    assert result.stdout.strip().endswith("userstate.db")


def test_budget_persists_in_external_dir():
    with tempfile.TemporaryDirectory() as data_dir:
        _run_memory_check(data_dir)
