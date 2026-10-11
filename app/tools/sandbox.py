import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SandboxTestResult(BaseModel):
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    error: str | None = None
    execution_time_seconds: float = 0.0


class SubprocessSandbox:
    """Isolated execution sandbox for executing unit tests and verifying patches safely."""

    def __init__(self, timeout_seconds: int = 30, max_output_chars: int = 5000):
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars

    async def run_pytest_in_sandbox(
        self,
        files: dict[str, str],
        test_file_path: str = "test_regression.py",
        test_code: str = "",
    ) -> SandboxTestResult:
        """Creates a temporary workspace directory, writes target source files and test code,

        and executes pytest in an isolated subprocess with strict timeouts.
        """
        temp_dir = tempfile.mkdtemp(prefix="repoguard_sandbox_")
        start_time = asyncio.get_event_loop().time()

        try:
            # 1. Write source files into temporary directory workspace
            for rel_path, content in files.items():
                full_path = os.path.join(temp_dir, rel_path.replace("/", os.sep))
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)

            # 2. Write regression test file if test_code is provided
            if test_code.strip():
                full_test_path = os.path.join(temp_dir, test_file_path.replace("/", os.sep))
                os.makedirs(os.path.dirname(full_test_path), exist_ok=True)
                with open(full_test_path, "w", encoding="utf-8") as f:
                    f.write(test_code)

            # 3. Spawn isolated subprocess running pytest
            python_executable = os.sys.executable

            cmd = [python_executable, "-m", "pytest", "-o", f"pythonpath={temp_dir}"]
            if test_code.strip():
                cmd.append(test_file_path)
            cmd.append("-v")

            env = os.environ.copy()
            existing_pp = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = f"{temp_dir}{os.pathsep}{existing_pp}" if existing_pp else temp_dir

            def _execute_pytest_sync():
                return subprocess.run(
                    cmd,
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=float(self.timeout_seconds),
                )

            try:
                completed = await asyncio.to_thread(_execute_pytest_sync)
                stdout_str = completed.stdout or ""
                stderr_str = completed.stderr or ""
                exit_code = completed.returncode
            except subprocess.TimeoutExpired:
                execution_time = asyncio.get_event_loop().time() - start_time
                return SandboxTestResult(
                    success=False,
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    error=f"Pytest execution timed out after {self.timeout_seconds} seconds.",
                    execution_time_seconds=round(execution_time, 2),
                )

            # Truncate output strings if exceeding maximum limits
            if len(stdout_str) > self.max_output_chars:
                stdout_str = stdout_str[: self.max_output_chars] + "\n... [Output Truncated]"
            if len(stderr_str) > self.max_output_chars:
                stderr_str = stderr_str[: self.max_output_chars] + "\n... [Output Truncated]"

            execution_time = asyncio.get_event_loop().time() - start_time

            return SandboxTestResult(
                success=(exit_code == 0),
                exit_code=exit_code,
                stdout=stdout_str,
                stderr=stderr_str,
                execution_time_seconds=round(execution_time, 2),
            )



        except Exception as exc:
            logger.exception("Failed to execute sandbox pytest process")
            execution_time = asyncio.get_event_loop().time() - start_time
            return SandboxTestResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                error=f"Sandbox error: {exc}",
                execution_time_seconds=round(execution_time, 2),
            )
        finally:
            # Clean up temporary directory workspace
            shutil.rmtree(temp_dir, ignore_errors=True)
