import ast

code="""
def calculate_total(items):
    total=0

    for item in items:
        total+=item.price

    return total
"""

tree=ast.parse(code)
print(ast.dump(tree,indent=4))