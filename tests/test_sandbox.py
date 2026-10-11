import pytest
from app.tools.sandbox import SubprocessSandbox


@pytest.mark.asyncio
async def test_subprocess_sandbox_passing_test():
    sandbox = SubprocessSandbox(timeout_seconds=10)

    files = {
        "app/calc.py": "def add(a, b):\n    return a + b\n"
    }

    test_code = "from app.calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"

    res = await sandbox.run_pytest_in_sandbox(files, test_file_path="test_calc.py", test_code=test_code)

    assert res.success is True
    assert res.exit_code == 0
    assert "PASSED" in res.stdout


@pytest.mark.asyncio
async def test_subprocess_sandbox_failing_test():
    sandbox = SubprocessSandbox(timeout_seconds=10)

    files = {
        "app/calc.py": "def add(a, b):\n    return a - b\n"  # bug in implementation
    }

    test_code = "from app.calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"

    res = await sandbox.run_pytest_in_sandbox(files, test_file_path="test_calc.py", test_code=test_code)

    assert res.success is False
    assert res.exit_code != 0
    assert "FAILED" in res.stdout


@pytest.mark.asyncio
async def test_subprocess_sandbox_timeout():
    sandbox = SubprocessSandbox(timeout_seconds=1)

    # Infinite loop code
    files = {
        "app/loop.py": "import time\ndef hang():\n    time.sleep(5)\n"
    }

    test_code = "from app.loop import hang\n\ndef test_hang():\n    hang()\n"

    res = await sandbox.run_pytest_in_sandbox(files, test_file_path="test_hang.py", test_code=test_code)

    assert res.success is False
    assert "timed out" in res.error.lower()
