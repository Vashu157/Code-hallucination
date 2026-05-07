import ast
import builtins
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field

# --- AST Feature Extraction Classes ---

@dataclass
class VariableDefinition:
    """Represents a variable assignment or function parameter extracted from the AST."""
    name: str
    def_type: str  # e.g., 'assignment', 'parameter', 'annotated_assignment'
    lineno: int


class CodeFeatureExtractor(ast.NodeVisitor):
    """
    Traverses an AST to extract features such as variable assignments,
    function parameters, and definitions.
    """
    def __init__(self) -> None:
        self.variables: List[VariableDefinition] = []
        self.parameters: List[VariableDefinition] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        """Extracts variable assignments (e.g., x = 5)."""
        for target in node.targets:
            self._extract_target(target, 'assignment', node.lineno)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Extracts annotated assignments (e.g., x: int = 5)."""
        self._extract_target(node.target, 'annotated_assignment', node.lineno)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        """Extracts augmented assignments (e.g., x += 5)."""
        self._extract_target(node.target, 'augmented_assignment', node.lineno)
        self.generic_visit(node)

    def _extract_target(self, target: ast.expr, def_type: str, lineno: int) -> None:
        """Helper method to handle target expression types recursively."""
        if isinstance(target, ast.Name):
            self.variables.append(VariableDefinition(target.id, def_type, lineno))
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._extract_target(elt, def_type, lineno)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Extracts parameters from function definitions."""
        self._extract_function_parameters(node.args, node.lineno)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Extracts parameters from async function definitions."""
        self._extract_function_parameters(node.args, node.lineno)
        self.generic_visit(node)

    def _extract_function_parameters(self, args: ast.arguments, lineno: int) -> None:
        """Helper method to parse function arguments."""
        for arg in args.args + args.posonlyargs + args.kwonlyargs:
            self.parameters.append(VariableDefinition(arg.arg, 'parameter', lineno))
        if args.vararg:
            self.parameters.append(VariableDefinition(args.vararg.arg, 'vararg', lineno))
        if args.kwarg:
            self.parameters.append(VariableDefinition(args.kwarg.arg, 'kwarg', lineno))


# --- Control Flow Graph (CFG) Generation Classes ---

@dataclass
class BasicBlock:
    """
    Represents a basic block in the Control Flow Graph.
    A basic block is a straight-line code sequence with no branches.
    """
    block_id: int
    statements: List[ast.stmt] = field(default_factory=list)
    successors: List['BasicBlock'] = field(default_factory=list)

    def add_statement(self, stmt: ast.stmt) -> None:
        """Appends a statement to the basic block."""
        self.statements.append(stmt)

    def add_successor(self, block: 'BasicBlock') -> None:
        """Adds a successor block representing a forward path in control flow."""
        if block not in self.successors:
            self.successors.append(block)


class CFG:
    """Represents a simplified Control Flow Graph mapping paths between basic blocks."""
    def __init__(self) -> None:
        self.blocks: List[BasicBlock] = []
        self.entry_block: Optional[BasicBlock] = None


class CFGBuilder:
    """
    Constructs a simplified CFG from an AST.
    It splits statements into basic blocks and identifies the control flow
    for conditionals (If) and loops (For, While).
    """
    def __init__(self) -> None:
        self.cfg = CFG()
        self._block_counter = 0
        self.current_block: Optional[BasicBlock] = None

    def _new_block(self) -> BasicBlock:
        self._block_counter += 1
        block = BasicBlock(self._block_counter)
        self.cfg.blocks.append(block)
        return block

    def build(self, node: ast.AST) -> CFG:
        """Builds the CFG starting from the root AST node."""
        self.current_block = self._new_block()
        self.cfg.entry_block = self.current_block

        if isinstance(node, ast.Module):
            self._visit_statements(node.body)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._visit_statements(node.body)
            
        return self.cfg

    def _visit_statements(self, stmts: List[ast.stmt]) -> None:
        """Iterates through and processes a list of statements."""
        for stmt in stmts:
            self._visit_statement(stmt)

    def _visit_statement(self, stmt: ast.stmt) -> None:
        """Routes a statement to its specific parsing logic."""
        if isinstance(stmt, ast.If):
            self._visit_If(stmt)
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            self._visit_For(stmt)
        elif isinstance(stmt, ast.While):
            self._visit_While(stmt)
        else:
            if self.current_block is None:
                self.current_block = self._new_block()
            self.current_block.add_statement(stmt)

    def _visit_If(self, node: ast.If) -> None:
        """Processes an If conditional and creates corresponding branch blocks."""
        if self.current_block is None:
            self.current_block = self._new_block()
            
        self.current_block.add_statement(node)
        if_header_block = self.current_block
        
        # Process the 'Then' body
        then_block = self._new_block()
        if_header_block.add_successor(then_block)
        self.current_block = then_block
        self._visit_statements(node.body)
        then_exit_block = self.current_block
        
        # Process the 'Else' body
        else_exit_block = None
        if node.orelse:
            else_block = self._new_block()
            if_header_block.add_successor(else_block)
            self.current_block = else_block
            self._visit_statements(node.orelse)
            else_exit_block = self.current_block
            
        # End of 'If' logic - unify control flow paths
        end_if_block = self._new_block()
        if then_exit_block:
            then_exit_block.add_successor(end_if_block)
        if else_exit_block:
            else_exit_block.add_successor(end_if_block)
        else:
            if_header_block.add_successor(end_if_block)
            
        self.current_block = end_if_block

    def _visit_For(self, node: Union[ast.For, ast.AsyncFor]) -> None:
        """Delegates For loops to the generalized loop handler."""
        self._handle_loop(node)

    def _visit_While(self, node: ast.While) -> None:
        """Delegates While loops to the generalized loop handler."""
        self._handle_loop(node)

    def _handle_loop(self, node: Union[ast.For, ast.AsyncFor, ast.While]) -> None:
        """Processes Loops, mapping backwards flow and breaks."""
        if self.current_block is None:
            self.current_block = self._new_block()
            
        # Add the loop condition/header to the current block
        self.current_block.add_statement(node)
        loop_header_block = self.current_block
        
        # Process the loop body
        body_block = self._new_block()
        loop_header_block.add_successor(body_block)
        self.current_block = body_block
        self._visit_statements(node.body)
        body_exit_block = self.current_block
        
        # Loop body goes back to header
        if body_exit_block:
            body_exit_block.add_successor(loop_header_block)
            
        # Block representing code executed after the loop
        after_loop_block = self._new_block()
        loop_header_block.add_successor(after_loop_block)
        
        # Handle 'Else' clause in loops (executes when loop doesn't break)
        if node.orelse:
            orelse_block = self._new_block()
            loop_header_block.add_successor(orelse_block)
            self.current_block = orelse_block
            self._visit_statements(node.orelse)
            orelse_exit_block = self.current_block
            if orelse_exit_block:
                orelse_exit_block.add_successor(after_loop_block)
                
        self.current_block = after_loop_block

# --- Core Analyzer API ---

class CodeAnalyzer:
    """
    Facade class providing an easy interface for parsing code,
    extracting AST features, and building a CFG.
    """
    def __init__(self, source_code: str) -> None:
        self.source_code = source_code
        self.ast_tree: Optional[ast.Module] = None
        self.extractor = CodeFeatureExtractor()
        self.cfg_builder = CFGBuilder()

    def parse(self) -> None:
        """Parses the raw source code string into an AST module."""
        self.ast_tree = ast.parse(self.source_code)

    def extract_features(self) -> None:
        """Traverses the AST to extract variables and parameters."""
        if self.ast_tree is None:
            raise ValueError("AST has not been generated. Call parse() first.")
        self.extractor.visit(self.ast_tree)

    def build_cfg(self) -> CFG:
        """Builds and returns the CFG from the parsed AST."""
        if self.ast_tree is None:
            raise ValueError("AST has not been generated. Call parse() first.")
        return self.cfg_builder.build(self.ast_tree)


# --- SSA Transformation & Error Detection Classes ---

class SSATransformer(ast.NodeTransformer):
    """
    Transforms an AST into Static Single Assignment (SSA) form by
    renaming variables upon reassignment (e.g., x -> x_1, x_2).
    """
    def __init__(self) -> None:
        self.var_counters: Dict[str, int] = {}
        self.current_env: Dict[str, str] = {}

    def _rename_target(self, name: str) -> str:
        if name not in self.var_counters:
            self.var_counters[name] = 1
        else:
            self.var_counters[name] += 1
        new_name = f"{name}_{self.var_counters[name]}"
        self.current_env[name] = new_name
        return new_name

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            arg.arg = self._rename_target(arg.arg)
        if node.args.vararg:
            node.args.vararg.arg = self._rename_target(node.args.vararg.arg)
        if node.args.kwarg:
            node.args.kwarg.arg = self._rename_target(node.args.kwarg.arg)
            
        self.generic_visit(node)
        return node

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        node.value = self.visit(node.value)
        new_targets = []
        for target in node.targets:
            if isinstance(target, ast.Name):
                new_name = self._rename_target(target.id)
                new_targets.append(ast.Name(id=new_name, ctx=target.ctx))
            else:
                new_targets.append(self.visit(target))
        node.targets = new_targets
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:
        if node.value:
            node.value = self.visit(node.value)
        if isinstance(node.target, ast.Name):
            new_name = self._rename_target(node.target.id)
            node.target = ast.Name(id=new_name, ctx=node.target.ctx)
        else:
            node.target = self.visit(node.target)
        return node

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if isinstance(node.ctx, ast.Load):
            if node.id in self.current_env:
                node.id = self.current_env[node.id]
        elif isinstance(node.ctx, ast.Store):
            node.id = self._rename_target(node.id)
        return node


class StaticDetector(ast.NodeVisitor):
    """
    Analyzes an SSA-transformed AST to detect hallucinations:
    - Identity Hallucination (IH): Variable used before assignment.
    - External Source Hallucination (ESH): Module/function called but not defined/imported.
    - Structure Access Hallucination (SAH): Obvious out-of-bounds error or range() step of 0.
    """
    def __init__(self) -> None:
        self.errors: List[Dict[str, Any]] = []
        self.defined_names = set(dir(builtins))
        self.var_values: Dict[str, ast.AST] = {}
        
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.defined_names.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.defined_names.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.defined_names.add(node.name)
        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            self.defined_names.add(arg.arg)
        if node.args.vararg:
            self.defined_names.add(node.args.vararg.arg)
        if node.args.kwarg:
            self.defined_names.add(node.args.kwarg.arg)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.defined_names.add(target.id)
                self.var_values[target.id] = node.value
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            self.defined_names.add(node.target.id)
            if node.value:
                self.var_values[node.target.id] = node.value
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        is_esh = False
        if isinstance(node.func, ast.Name):
            if node.func.id not in self.defined_names:
                self.errors.append({
                    'error_type': 'External Source Hallucination (ESH)',
                    'variable_name': node.func.id,
                    'line_number': node.lineno
                })
                is_esh = True
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                if node.func.value.id not in self.defined_names:
                    self.errors.append({
                        'error_type': 'External Source Hallucination (ESH)',
                        'variable_name': f"{node.func.value.id}.{node.func.attr}",
                        'line_number': node.lineno
                    })
                    is_esh = True

        # Check for SAH: range() step of 0
        if isinstance(node.func, ast.Name) and node.func.id == 'range':
            if len(node.args) == 3:
                step_arg = node.args[2]
                if isinstance(step_arg, ast.Constant) and step_arg.value == 0:
                    self.errors.append({
                        'error_type': 'Structure Access Hallucination (SAH)',
                        'variable_name': 'range() step of 0',
                        'line_number': node.lineno
                    })

        if not is_esh:
            self.visit(node.func)
        for arg in node.args:
            self.visit(arg)
        for kw in node.keywords:
            self.visit(kw)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        target_len = None
        if isinstance(node.value, (ast.List, ast.Tuple)):
            target_len = len(node.value.elts)
        elif isinstance(node.value, ast.Name) and node.value.id in self.var_values:
            val_node = self.var_values[node.value.id]
            if isinstance(val_node, (ast.List, ast.Tuple)):
                target_len = len(val_node.elts)
                
        if target_len is not None and isinstance(node.slice, ast.Constant):
            if isinstance(node.slice.value, int):
                if node.slice.value >= target_len or node.slice.value < -target_len:
                    self.errors.append({
                        'error_type': 'Structure Access Hallucination (SAH)',
                        'variable_name': f"index {node.slice.value} out of bounds",
                        'line_number': node.lineno
                    })
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.defined_names.add(node.id)
        elif isinstance(node.ctx, ast.Load):
            if node.id not in self.defined_names:
                self.errors.append({
                    'error_type': 'Identity Hallucination (IH)',
                    'variable_name': node.id,
                    'line_number': node.lineno
                })
        self.generic_visit(node)


def detect_hallucinations(source_code: str) -> List[Dict[str, Any]]:
    """Helper function to parse, transform to SSA, and detect hallucinations."""
    tree = ast.parse(source_code)
    
    transformer = SSATransformer()
    ssa_tree = transformer.visit(tree)
    ast.fix_missing_locations(ssa_tree)
    
    detector = StaticDetector()
    detector.visit(ssa_tree)
    
    return detector.errors

# --- Mock Testing ---

if __name__ == "__main__":
    MOCK_CODE = '''
import math

def calculate(a, b):
    x = a + b
    x = x * 2
    y = x + z  # IH: z is not defined
    res = unknown_func(y)  # ESH: unknown_func is not defined
    val = math.pi
    bad_math = unimported_module.do_something() # ESH: unimported_module
    
    # SAH: range step of 0
    for i in range(0, 10, 0):
        pass
        
    # SAH: obvious out of bounds error
    arr = [1, 2, 3]
    print(arr[5])
'''
    print("Testing hallucination detection on mock code...")
    errors = detect_hallucinations(MOCK_CODE)
    for err in errors:
        print(f"Detected {err['error_type']} -> Variable: '{err['variable_name']}' at line {err['line_number']}")
