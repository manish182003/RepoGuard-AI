import ast

class PythonASTAnalyzer:
    """Analyze Python source code using Python's AST."""

    def parse(self,source:str)->ast.AST:
        return ast.parse(source)

    def find_function(self,tree:ast.AST)->list[dict]:

        functions=[]

        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                functions.append(
                    {
                        "name":node.name,
                        "line":node.lineno,
                         "end_line":node.end_lineno   
                    }
                )

        return functions

    def find_classes(self,tree:ast.AST)->list[dict]:

        classes=[]

        for node in ast.walk(tree):
            if isinstance(node,ast.ClassDef):
                classes.append(
                    {
                        "name":node.name,
                        "line":node.lineno,
                        "end_line":node.end_lineno
                    }
                )

        return classes

    def find_imports(self,tree:ast.AST)->list[str]:

        imports=[]

        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node,ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        return imports

    def find_function_calls(self,tree:ast.AST)->list[dict]:

        calls=[]

        for node in ast.walk(tree):
            if not isinstance(node,ast.Call):
                continue

            calls.append(
                {
                    "name":self._get_call_name(node.func),
                    "line":node.lineno
                }
            )

        return calls

    def _get_call_name(self,node:ast.AST)->str:
        if isinstance(node,ast.Name):
            return node.id

        if isinstance(node,ast.Attribute):
            parts=[]

            current=node

            while isinstance(current,ast.Attribute):
                parts.append(current.attr)
                current=current.value

            if isinstance(current,ast.Name):
                parts.append(current.id)

            return ".".join(reversed(parts))
        
        return "<unknown>"


    def analyze_file(self,source:str)->dict:
        tree=self.parse(source)
        
        return {
            "functions":self.find_function(tree),
            "classes":self.find_classes(tree),
            "imports":self.find_imports(tree),
            "function_calls":self.find_function_calls(tree)
        }



