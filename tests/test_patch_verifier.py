import pytest
from app.llm import FakeLLMProvider
from app.schemas.finding import Finding
from app.tools.patch_generator import GeneratedPatch, PatchGenerator
from app.tools.patch_verifier import PatchVerifier


@pytest.mark.asyncio
async def test_patch_generator():
    fake_response = {
        "path": "app/main.py",
        "target_code": "requests.get(url)",
        "replacement_code": "requests.get(url, timeout=10)",
        "explanation": "Add explicit timeout parameter to prevent indefinite hanging.",
        "regression_test_code": "def test_timeout(): pass",
    }

    provider = FakeLLMProvider(response_content=fake_response)
    generator = PatchGenerator(provider=provider)

    finding = Finding(
        rule="requests_timeout",
        path="app/main.py",
        line=5,
        title="Missing timeout",
        description="requests.get lacks timeout",
    )

    patch = await generator.generate_patch(finding, "def run():\n    requests.get(url)\n")
    assert patch.path == "app/main.py"
    assert patch.target_code == "requests.get(url)"
    assert patch.replacement_code == "requests.get(url, timeout=10)"


def test_patch_verifier_success():
    verifier = PatchVerifier()
    patch = GeneratedPatch(
        path="app/main.py",
        target_code="requests.get(url)",
        replacement_code="requests.get(url, timeout=10)",
        explanation="Add timeout",
    )

    original = "def run():\n    requests.get(url)\n"
    res = verifier.verify_patch(patch, original)

    assert res.success is True
    assert res.syntax_check == "passed"
    assert "timeout=10" in res.modified_content


def test_patch_verifier_syntax_error():
    verifier = PatchVerifier()
    patch = GeneratedPatch(
        path="app/main.py",
        target_code="requests.get(url)",
        replacement_code="requests.get(url,",  # invalid syntax
        explanation="Broken code",
    )

    original = "def run():\n    requests.get(url)\n"
    res = verifier.verify_patch(patch, original)

    assert res.success is False
    assert res.syntax_check == "failed"
    assert "syntax error" in res.error.lower()


def test_patch_verifier_target_not_found():
    verifier = PatchVerifier()
    patch = GeneratedPatch(
        path="app/main.py",
        target_code="nonexistent_code()",
        replacement_code="fixed()",
        explanation="Target missing",
    )

    res = verifier.verify_patch(patch, "def run(): pass\n")
    assert res.success is False
    assert "Target code snippet not found" in res.error


def test_patch_verifier_indentation_tolerant():
    verifier = PatchVerifier()
    # Target code missing 4-space indentation
    patch = GeneratedPatch(
        path="app/main.py",
        target_code="if value < 0:\n    raise ValueError('negative')",
        replacement_code="# allow negative values\n# if value < 0:\n#     raise ValueError('negative')",
        explanation="Allow negative",
    )

    original = "def check(value):\n    if value < 0:\n        raise ValueError('negative')\n    return value\n"
    res = verifier.verify_patch(patch, original)
    assert res.success is True
    assert res.syntax_check == "passed"
    assert "# allow negative values" in res.modified_content
    assert "    # allow negative values" in res.modified_content


def test_patch_verifier_rejects_undefined_self_method():
    verifier = PatchVerifier()
    patch = GeneratedPatch(
        path="app/providers/base.py",
        target_code="completion_kwargs = self._convert(params)",
        replacement_code="completion_kwargs = self._convert(params)\nself._validate_model_capabilities(params, completion_kwargs)",
        explanation="Call hallucinated method",
    )

    original = """class BaseProvider:
    def _convert(self, params):
        return {}
    def run(self, params):
        completion_kwargs = self._convert(params)
"""
    res = verifier.verify_patch(patch, original)
    assert res.success is False
    assert res.syntax_check == "semantic_failed"
    assert "undefined method 'self._validate_model_capabilities()'" in res.error


def test_patch_verifier_rejects_undefined_global_function():
    verifier = PatchVerifier()
    patch = GeneratedPatch(
        path="app/utils.py",
        target_code="return val",
        replacement_code="return phantom_repair_func(val)",
        explanation="Call unimported global func",
    )

    original = "def clean(val):\n    return val\n"
    res = verifier.verify_patch(patch, original)
    assert res.success is False
    assert res.syntax_check == "semantic_failed"
    assert "undefined function or class 'phantom_repair_func()'" in res.error


def test_patch_verifier_allows_newly_defined_method():
    verifier = PatchVerifier()
    patch = GeneratedPatch(
        path="app/providers/base.py",
        target_code="""    def run(self, params):
        completion_kwargs = self._convert(params)""",
        replacement_code="""    def _validate_capabilities(self, params):
        return True

    def run(self, params):
        self._validate_capabilities(params)
        completion_kwargs = self._convert(params)""",
        explanation="Define and call new method",
    )

    original = """class BaseProvider:
    def _convert(self, params):
        return {}

    def run(self, params):
        completion_kwargs = self._convert(params)
"""
    res = verifier.verify_patch(patch, original)
    assert res.success is True
    assert res.syntax_check == "passed"


def test_patch_verifier_allows_newly_defined_helper_function():
    verifier = PatchVerifier()
    patch = GeneratedPatch(
        path="app/utils.py",
        target_code="""def clean(val):
    return val""",
        replacement_code="""def _sanitize(x):
    return x.strip()

def clean(val):
    return _sanitize(val)""",
        explanation="Define and call new helper function",
    )

    original = """def clean(val):
    return val
"""
    res = verifier.verify_patch(patch, original)
    assert res.success is True
    assert res.syntax_check == "passed"




