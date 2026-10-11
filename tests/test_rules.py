from app.tools.rules import PythonRuleEngine


def test_detect_requests_without_timeout():
    source = """
import requests

response = requests.get(url)
"""

    engine = PythonRuleEngine()

    findings = engine.check_http_timeouts(
        source=source,
        path="client.py",
    )

    assert len(findings) == 1

    finding = findings[0]

    assert finding.rule == "PYTHON-HTTP-NO-TIMEOUT"
    assert finding.severity == "medium"
    assert finding.path == "client.py"
    assert finding.line == 4
    assert finding.status == "candidate"


def test_requests_with_timeout_is_safe():
    source = """
import requests

response = requests.get(url, timeout=10)
"""

    engine = PythonRuleEngine()

    findings = engine.check_http_timeouts(
        source=source,
        path="client.py",
    )

    assert findings == []


def test_multiple_requests():
    source = """
import requests

first = requests.get(url1)
second = requests.post(url2, timeout=5)
third = requests.delete(url3)
"""

    engine = PythonRuleEngine()

    findings = engine.check_http_timeouts(
        source=source,
        path="client.py",
    )

    assert len(findings) == 2

    assert findings[0].line == 4
    assert findings[1].line == 6


def test_detect_bare_except():
    source = """
try:
    do_something()
except:
    pass
"""
    engine = PythonRuleEngine()
    findings = engine.check_bare_except(source, "app.py")
    assert len(findings) == 1
    assert findings[0].rule == "PYTHON-BARE-EXCEPT"
    assert findings[0].line == 4


def test_detect_mutable_default_arg():
    source = """
def process_data(items=[]):
    items.append(1)
    return items
"""
    engine = PythonRuleEngine()
    findings = engine.check_mutable_default_args(source, "app.py")
    assert len(findings) == 1
    assert findings[0].rule == "PYTHON-MUTABLE-DEFAULT-ARG"
    assert findings[0].line == 2