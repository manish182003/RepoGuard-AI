import json
import logging
import re
from typing import Any
from pydantic import BaseModel, Field
from typing import Any
from app.llm import BaseLLMProvider, GroqProvider, LLMMessage
from app.schemas.finding import Finding

logger = logging.getLogger(__name__)

PATCH_SYSTEM_PROMPT = """
You are RepoGuard AI Patch Generator.

Your task is to propose a minimal, safe Python fix and regression test for a confirmed software defect or GitHub issue.

STRICT RULES & CONSTRAINTS:
1. Do not rewrite whole files. Only provide the minimal exact line(s) to replace.
2. Return JSON matching this exact schema:
   {
     "path": "repository/file.py",
     "target_code": "exact lines of code to replace",
     "replacement_code": "exact lines of replacement code",
     "explanation": "Why this patch fixes the bug safely",
     "regression_test_code": "def test_regression_bug():\\n    # real assertion verifying the fixed behavior\\n    assert ..."
   }
3. The regression_test_code must test the specific defect or issue behavior. Avoid trivial placeholder assertions like 'assert True'.
4. DEFINING NEW METHODS & FUNCTIONS: You ARE allowed to define new helper methods, functions, or classes if required by the bug fix. HOWEVER, you MUST provide their COMPLETE definition within your `replacement_code`. NEVER call a method or function that has no definition.
5. STRICT ANTI-HALLUCINATION: NEVER call methods on `self` (`self.some_method()`) without defining that method. Do NOT call phantom methods or assume helper methods exist elsewhere.
6. SELF-CONTAINED FIX: Your patch must be 100% self-contained and syntactically complete. Any new function, method, or imported helper you call must be fully defined or imported in your replacement code.
7. DIRECT ROOT CAUSE RESOLUTION: When fixing a reported GitHub issue, your patch must directly satisfy the reported Expected Behavior and prevent the reported error. Do not make cosmetic changes to unrelated branches.
"""


class GeneratedPatch(BaseModel):
    path: str
    target_code: str
    replacement_code: str
    explanation: str
    regression_test_code: str = ""


class PatchGenerator:
    """Generates minimal patches and regression tests for confirmed findings."""

    def __init__(self, provider: BaseLLMProvider | None = None):
        self.provider = provider or GroqProvider()

    async def generate_patch(
        self,
        finding: Finding,
        file_content: str,
        error_feedback: str | None = None,
        target_issue: Any | None = None,
    ) -> GeneratedPatch:
        # Ensure target line and surrounding context are fully visible to the model
        if len(file_content) > 30000 and finding.line:
            lines = file_content.splitlines(keepends=True)
            start_line = max(0, finding.line - 60)
            end_line = min(len(lines), finding.line + 60)
            snippet = "".join(lines[start_line:end_line])
        else:
            snippet = file_content[:30000]

        issue_details_text = ""
        if target_issue:
            i_title = getattr(target_issue, "title", "") or (target_issue.get("title") if isinstance(target_issue, dict) else "")
            i_body = getattr(target_issue, "body", "") or (target_issue.get("body") if isinstance(target_issue, dict) else "")
            i_num = getattr(target_issue, "number", finding.related_issue_id) or (target_issue.get("number") if isinstance(target_issue, dict) else finding.related_issue_id)
            issue_details_text = f"""
TARGET GITHUB ISSUE #{i_num}: {i_title}
REPORTED ISSUE DESCRIPTION, SYMPTOMS & EXPECTED BEHAVIOR:
{i_body or 'No detailed description provided.'}

CRITICAL FIX OBJECTIVE:
1. Your patch MUST directly and specifically fix the exact reproduction case, error symptoms, and behavior reported in Issue #{i_num}.
2. Ensure you adhere to the Expected Behavior reported by the issue. If the expected behavior is raising a specific error class (e.g. FilterError), or normalizing types, you MUST do so.
3. Do not just patch adjacent lines. Directly resolve the root cause of the reported error.
"""
        elif finding.related_issue_id:
            issue_details_text = f"Related GitHub Issue: #{finding.related_issue_id}\n"

        feedback_info = f"\nCORRECTION REQUIRED: Your previous patch failed verification with this error:\n{error_feedback}\nYou MUST fix this error and ensure no undefined methods or phantom functions are called.\n" if error_feedback else ""
        user_prompt = f"""
Defect Title: {finding.title}
Defect Description: {finding.description}
{issue_details_text}
{feedback_info}File Path: {finding.path}
Target Line: {finding.line}
Evidence: {json.dumps(finding.evidence)}

Current File Content:
```python
{snippet}
```
"""

        messages = [
            LLMMessage(role="system", content=PATCH_SYSTEM_PROMPT.strip()),
            LLMMessage(role="user", content=user_prompt.strip()),
        ]

        response = await self.provider.generate(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        content = response.content.strip()
        if not content:
            raise ValueError("Patch generator received empty LLM response.")

        def clean_and_repair_json(raw: str) -> str:
            text = raw.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
                text = re.sub(r"\s*```$", "", text)

            start_idx = text.find("{")
            if start_idx != -1:
                text = text[start_idx:]

            last_idx = text.rfind("}")
            if last_idx != -1 and last_idx > 0:
                candidate = text[:last_idx + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except Exception:
                    pass

            # Balance quotes and braces if truncated
            quotes = len(re.findall(r'(?<!\\)"', text))
            if quotes % 2 != 0:
                text += '"'
            if not text.rstrip().endswith("}"):
                text = text.rstrip() + "\n}"
            return text

        try:
            cleaned = clean_and_repair_json(content)
            return GeneratedPatch.model_validate_json(cleaned)
        except Exception as parse_err:
            logger.warning(f"Initial patch parse failed ({parse_err}). Attempting 1-shot repair retry...")
            retry_messages = messages + [
                LLMMessage(role="assistant", content=content[:1500]),
                LLMMessage(
                    role="user",
                    content="Your JSON was incomplete or malformed. Return ONLY the complete, valid JSON object with keys: path, target_code, replacement_code, explanation, regression_test_code."
                )
            ]
            retry_response = await self.provider.generate(
                messages=retry_messages,
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            retry_cleaned = clean_and_repair_json(retry_response.content)
            return GeneratedPatch.model_validate_json(retry_cleaned)
