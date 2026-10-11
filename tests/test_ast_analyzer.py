from app.tools.ast_analyzer import PythonASTAnalyzer

def test_find_functions():
    source="""
def hello(name):
    return f"Hello {name}"

def add(a,b):
    return a+b
"""

    analyzer=PythonASTAnalyzer()
    tree = analyzer.parse(source)
    functions = analyzer.find_function(tree)

    assert functions == [
        {
            "name":"hello",
            "line":2,
            "end_line":3,
        },
        {
            "name":"add",
            "line":5,
            "end_line":6
        }
    ]

def test_find_classes():
    source = """
class UserService:
    def get_user(self):
        pass


class PaymentService:
    pass
"""

    analyzer=PythonASTAnalyzer()

    tree = analyzer.parse(source)
    classes=analyzer.find_classes(tree)

    assert classes == [
        {
            "name":"UserService",
            "line":2,
            "end_line":4,
        },
        {
            "name":"PaymentService",
            "line":7,
            "end_line":8
        }
    ]


def test_find_imports():
    source = """
import requests
import os
from pathlib import Path
from app.services import UserService
"""

    analyzer = PythonASTAnalyzer()

    tree = analyzer.parse(source)
    imports = analyzer.find_imports(tree)


    assert imports == [
        "requests",
        "os",
        "pathlib",
        "app.services",
    ]


def test_find_function_calls():
    source = """
def fetch(url):
    response = requests.get(url)
    data = response.json()
    print(data)
    return data
"""

    analyzer = PythonASTAnalyzer()


    tree = analyzer.parse(source)
    calls = analyzer.find_function_calls(tree)

    assert calls == [
        {
            "name": "requests.get",
            "line": 3,
        },
        {
            "name": "response.json",
            "line": 4,
        },
        {
            "name": "print",
            "line": 5,
        },
    ]


def test_analyze_file():
    source = """
import requests


class APIClient:

    def fetch(self, url):
        response = requests.get(url)
        return response.json()
"""

    analyzer = PythonASTAnalyzer()

    result = analyzer.analyze_file(source)

    assert result["imports"] == ["requests"]

    assert result["classes"] == [
        {
            "name": "APIClient",
            "line": 5,
            "end_line": 9,
        }
    ]

    assert result["functions"] == [
        {
            "name": "fetch",
            "line": 7,
            "end_line": 9,
        }
    ]

    assert result["function_calls"] == [
        {
            "name": "requests.get",
            "line": 8,
        },
        {
            "name": "response.json",
            "line": 9,
        },
    ]


def test_invalid_python():
    source = """
def broken(
"""

    analyzer = PythonASTAnalyzer()

    try:
        analyzer.analyze_file(source)
    except SyntaxError:
        assert True
    else:
        assert False

