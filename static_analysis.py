import ast
import copy
import builtins
import re
from typing import List, Dict, Set, Any, Optional, Union, Tuple
from dataclasses import dataclass, field

# --- AST Feature Extraction Classes ---

@dataclass
class VariableDefinition:
    """Represents a variable assignment or function parameter extracted from the AST."""
    name: str
    def_type: str  # e.g., 'assignment', 'parameter', 'annotated_assignment', 'augmented_assignment'
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


# --- Control Flow Graph (CFG) Classes ---

@dataclass
class PhiNode:
    """
    Represents an SSA phi-function at a CFG join block.
    target_var: The renamed version assigned by this phi (e.g., 's2', 'x3')
    base_var: The original variable name (e.g., 's', 'x')
    operands: Mapping from predecessor block_id to the incoming SSA version string or 'UNDEFINED'
    lineno: Line number of the join block / statement
    """
    target_var: str
    base_var: str
    operands: Dict[int, Optional[str]] = field(default_factory=dict)
    lineno: int = 0

    def has_undefined_operand(self) -> bool:
        """Returns True if any incoming path does not provide a defined value."""
        return any(v is None or v == "UNDEFINED" for v in self.operands.values())

    def __hash__(self) -> int:
        return hash((self.target_var, self.base_var, self.lineno))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PhiNode):
            return False
        return (self.target_var, self.base_var, self.lineno) == (other.target_var, other.base_var, other.lineno)

    def __repr__(self) -> str:
        ops_str = ", ".join(f"B{bid}:{ver}" for bid, ver in sorted(self.operands.items()))
        return f"{self.target_var} = φ({ops_str})"


@dataclass
class BasicBlock:
    """
    Represents a basic block in the Control Flow Graph.
    Contains straight-line code statements, predecessor and successor edges,
    dominator tree links, dominance frontier set, and phi nodes.
    """
    block_id: int
    statements: List[ast.stmt] = field(default_factory=list)
    predecessors: List['BasicBlock'] = field(default_factory=list)
    successors: List['BasicBlock'] = field(default_factory=list)
    phi_nodes: Dict[str, PhiNode] = field(default_factory=dict)  # base_var -> PhiNode
    idom: Optional['BasicBlock'] = None                          # Immediate dominator
    dom_children: List['BasicBlock'] = field(default_factory=list) # Dominator tree children
    df: Set['BasicBlock'] = field(default_factory=set)           # Dominance frontier
    is_terminated: bool = False                                  # True if ends with return/break/continue

    def add_statement(self, stmt: ast.stmt) -> None:
        """Appends a statement to the basic block."""
        self.statements.append(stmt)

    def add_successor(self, block: 'BasicBlock') -> None:
        """Adds a directed edge self -> block (and sets block's predecessor)."""
        if block not in self.successors:
            self.successors.append(block)
        if self not in block.predecessors:
            block.predecessors.append(self)

    def __hash__(self) -> int:
        return hash(self.block_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BasicBlock):
            return False
        return self.block_id == other.block_id

    def __repr__(self) -> str:
        preds = [b.block_id for b in self.predecessors]
        succs = [b.block_id for b in self.successors]
        return f"Block(id={self.block_id}, preds={preds}, succs={succs}, stmts={len(self.statements)}, phis={len(self.phi_nodes)})"


class CFG:
    """Represents a Control Flow Graph mapping paths between basic blocks."""
    def __init__(self) -> None:
        self.blocks: List[BasicBlock] = []
        self.entry_block: Optional[BasicBlock] = None

    def get_reachable_blocks(self) -> List[BasicBlock]:
        """Returns all basic blocks reachable from the entry block via BFS."""
        if not self.entry_block:
            return []
        visited: Set[int] = set()
        queue: List[BasicBlock] = [self.entry_block]
        reachable: List[BasicBlock] = []

        while queue:
            curr = queue.pop(0)
            if curr.block_id in visited:
                continue
            visited.add(curr.block_id)
            reachable.append(curr)
            for succ in curr.successors:
                if succ.block_id not in visited:
                    queue.append(succ)

        return reachable


class CFGBuilder:
    """
    Constructs a CFG from a Python AST (Module or FunctionDef).
    Accurately maps branch splits, join points, loops, back-edges, breaks, and returns.
    """
    def __init__(self) -> None:
        self.cfg = CFG()
        self._block_counter = 0
        self.current_block: Optional[BasicBlock] = None
        self._loop_stack: List[Tuple[BasicBlock, BasicBlock]] = []  # (header_block, exit_block)

    def _new_block(self) -> BasicBlock:
        self._block_counter += 1
        block = BasicBlock(self._block_counter)
        self.cfg.blocks.append(block)
        return block

    def build(self, node: ast.AST) -> CFG:
        """Builds the CFG starting from the root AST node."""
        self.current_block = self._new_block()
        self.cfg.entry_block = self.current_block

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Register function parameters as initial definitions in entry block
            for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
                if arg.annotation and isinstance(arg.annotation, ast.Name):
                    param_stmt = ast.AnnAssign(
                        target=ast.Name(id=arg.arg, ctx=ast.Store(), lineno=node.lineno, col_offset=0),
                        annotation=arg.annotation,
                        value=None,
                        simple=1,
                        lineno=node.lineno,
                        col_offset=0
                    )
                else:
                    param_stmt = ast.Assign(
                        targets=[ast.Name(id=arg.arg, ctx=ast.Store(), lineno=node.lineno, col_offset=0)],
                        value=ast.Constant(value=None, lineno=node.lineno, col_offset=0),
                        lineno=node.lineno,
                        col_offset=0
                    )
                self.current_block.add_statement(param_stmt)
            if node.args.vararg:
                param_stmt = ast.Assign(
                    targets=[ast.Name(id=node.args.vararg.arg, ctx=ast.Store(), lineno=node.lineno, col_offset=0)],
                    value=ast.Constant(value=None, lineno=node.lineno, col_offset=0),
                    lineno=node.lineno,
                    col_offset=0
                )
                self.current_block.add_statement(param_stmt)
            if node.args.kwarg:
                param_stmt = ast.Assign(
                    targets=[ast.Name(id=node.args.kwarg.arg, ctx=ast.Store(), lineno=node.lineno, col_offset=0)],
                    value=ast.Constant(value=None, lineno=node.lineno, col_offset=0),
                    lineno=node.lineno,
                    col_offset=0
                )
                self.current_block.add_statement(param_stmt)
            self._visit_statements(node.body)
        elif isinstance(node, ast.Module):
            self._visit_statements(node.body)
        else:
            self._visit_statement(node)

        return self.cfg

    def _visit_statements(self, stmts: List[ast.stmt]) -> None:
        """Iterates through and processes a sequence of statements."""
        for stmt in stmts:
            if self.current_block and self.current_block.is_terminated:
                break
            self._visit_statement(stmt)

    def _visit_statement(self, stmt: ast.stmt) -> None:
        """Routes an AST statement to its CFG construction logic."""
        if self.current_block is None:
            self.current_block = self._new_block()

        if isinstance(stmt, ast.If):
            self._visit_If(stmt)
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            self._visit_For(stmt)
        elif isinstance(stmt, ast.While):
            self._visit_While(stmt)
        elif isinstance(stmt, ast.Return):
            self.current_block.add_statement(stmt)
            self.current_block.is_terminated = True
            self.current_block = self._new_block()
        elif isinstance(stmt, ast.Break):
            self.current_block.add_statement(stmt)
            self.current_block.is_terminated = True
            if self._loop_stack:
                _, exit_block = self._loop_stack[-1]
                self.current_block.add_successor(exit_block)
            self.current_block = self._new_block()
        elif isinstance(stmt, ast.Continue):
            self.current_block.add_statement(stmt)
            self.current_block.is_terminated = True
            if self._loop_stack:
                header_block, _ = self._loop_stack[-1]
                self.current_block.add_successor(header_block)
            self.current_block = self._new_block()
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            def_stmt = ast.Assign(
                targets=[ast.Name(id=stmt.name, ctx=ast.Store(), lineno=stmt.lineno, col_offset=0)],
                value=ast.Constant(value=None, lineno=stmt.lineno, col_offset=0),
                lineno=stmt.lineno,
                col_offset=0
            )
            self.current_block.add_statement(def_stmt)
        else:
            self.current_block.add_statement(stmt)

    def _visit_If(self, node: ast.If) -> None:
        """Constructs branch paths for If-Else conditionals."""
        header_block = self.current_block
        cond_expr = ast.Expr(value=node.test, lineno=node.lineno, col_offset=node.col_offset)
        header_block.add_statement(cond_expr)

        then_entry = self._new_block()
        header_block.add_successor(then_entry)
        self.current_block = then_entry
        self._visit_statements(node.body)
        then_exit = self.current_block

        else_entry = None
        else_exit = None
        if node.orelse:
            else_entry = self._new_block()
            header_block.add_successor(else_entry)
            self.current_block = else_entry
            self._visit_statements(node.orelse)
            else_exit = self.current_block

        join_block = self._new_block()

        if then_exit and not then_exit.is_terminated:
            then_exit.add_successor(join_block)

        if else_entry:
            if else_exit and not else_exit.is_terminated:
                else_exit.add_successor(join_block)
        else:
            header_block.add_successor(join_block)

        self.current_block = join_block

    def _visit_For(self, node: Union[ast.For, ast.AsyncFor]) -> None:
        """Constructs loop header, body back-edges, and exit for For loops."""
        pre_loop_block = self.current_block

        header_block = self._new_block()
        pre_loop_block.add_successor(header_block)

        target_assign = ast.Assign(
            targets=[node.target],
            value=ast.Call(func=ast.Name(id='iter', ctx=ast.Load(), lineno=node.lineno, col_offset=0),
                           args=[node.iter], keywords=[], lineno=node.lineno, col_offset=0),
            lineno=node.lineno,
            col_offset=node.col_offset
        )
        header_block.add_statement(target_assign)

        after_block = self._new_block()
        self._loop_stack.append((header_block, after_block))

        body_entry = self._new_block()
        header_block.add_successor(body_entry)
        self.current_block = body_entry
        self._visit_statements(node.body)
        body_exit = self.current_block

        if body_exit and not body_exit.is_terminated:
            body_exit.add_successor(header_block)

        self._loop_stack.pop()

        if node.orelse:
            orelse_block = self._new_block()
            header_block.add_successor(orelse_block)
            self.current_block = orelse_block
            self._visit_statements(node.orelse)
            orelse_exit = self.current_block
            if orelse_exit and not orelse_exit.is_terminated:
                orelse_exit.add_successor(after_block)
        else:
            header_block.add_successor(after_block)

        self.current_block = after_block

    def _visit_While(self, node: ast.While) -> None:
        """Constructs loop header, condition evaluation, back-edges, and exit for While loops."""
        pre_loop_block = self.current_block

        header_block = self._new_block()
        pre_loop_block.add_successor(header_block)

        cond_expr = ast.Expr(value=node.test, lineno=node.lineno, col_offset=node.col_offset)
        header_block.add_statement(cond_expr)

        after_block = self._new_block()
        self._loop_stack.append((header_block, after_block))

        body_entry = self._new_block()
        header_block.add_successor(body_entry)
        self.current_block = body_entry
        self._visit_statements(node.body)
        body_exit = self.current_block

        if body_exit and not body_exit.is_terminated:
            body_exit.add_successor(header_block)

        self._loop_stack.pop()

        if node.orelse:
            orelse_block = self._new_block()
            header_block.add_successor(orelse_block)
            self.current_block = orelse_block
            self._visit_statements(node.orelse)
            orelse_exit = self.current_block
            if orelse_exit and not orelse_exit.is_terminated:
                orelse_exit.add_successor(after_block)
        else:
            header_block.add_successor(after_block)

        self.current_block = after_block


# --- Dominance & SSA Construction Algorithms (Cytron et al. / Paper Alg. 1 & 2) ---

def compute_dominators(cfg: CFG) -> None:
    """
    Computes reachable blocks, dominator sets, immediate dominators (idom),
    dominator tree children (dom_children), and dominance frontiers (DF).
    """
    reachable = cfg.get_reachable_blocks()
    if not reachable or cfg.entry_block is None:
        return

    entry = cfg.entry_block

    # 1. Iterative dominance computation
    dom: Dict[int, Set[BasicBlock]] = {}
    dom[entry.block_id] = {entry}
    for b in reachable:
        if b.block_id != entry.block_id:
            dom[b.block_id] = set(reachable)

    changed = True
    while changed:
        changed = False
        for b in reachable:
            if b.block_id == entry.block_id:
                continue
            pred_doms = [dom[p.block_id] for p in b.predecessors if p.block_id in dom]
            if pred_doms:
                new_dom = {b}.union(set.intersection(*pred_doms))
            else:
                new_dom = {b}
            if new_dom != dom[b.block_id]:
                dom[b.block_id] = new_dom
                changed = True

    # 2. Compute immediate dominator (idom) & dominator tree
    for b in reachable:
        b.idom = None
        b.dom_children = []
        b.df = set()

    for b in reachable:
        if b.block_id == entry.block_id:
            continue
        sdom = dom[b.block_id] - {b}
        if sdom:
            # BUG-3 FIX: Break ties by selecting the strict dominator with the largest dominator set
            # (deepest in the tree), then by block_id for determinism when sizes are equal.
            idom_block = max(sdom, key=lambda d: (len(dom[d.block_id]), d.block_id))
            b.idom = idom_block
            idom_block.dom_children.append(b)

    # 3. Compute Dominance Frontiers (DF)
    for b in reachable:
        if len(b.predecessors) >= 2:
            for p in b.predecessors:
                runner: Optional[BasicBlock] = p
                while runner is not None and (b.idom is None or runner.block_id != b.idom.block_id):
                    runner.df.add(b)
                    runner = runner.idom


def _extract_defs_from_target(target: ast.expr) -> List[str]:
    """Helper to extract variable names being defined/stored."""
    names = []
    if isinstance(target, ast.Name):
        names.append(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            names.extend(_extract_defs_from_target(elt))
    return names


def _get_statement_defs(stmt: ast.stmt) -> List[str]:
    """Extracts all variable names assigned or defined in a statement."""
    defs: List[str] = []
    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            defs.extend(_extract_defs_from_target(target))
    elif isinstance(stmt, ast.AnnAssign):
        defs.extend(_extract_defs_from_target(stmt.target))
    elif isinstance(stmt, ast.AugAssign):
        defs.extend(_extract_defs_from_target(stmt.target))
    return defs


def insert_phi_nodes(cfg: CFG) -> None:
    """
    Algorithm 2 Phase 1 (φ-insertion):
    For every variable v, find DefSites(v), then for every node in the iterated
    dominance frontier IDF(DefSites(v)), insert a φ-function.
    """
    reachable = cfg.get_reachable_blocks()
    def_sites: Dict[str, Set[BasicBlock]] = {}

    for b in reachable:
        for stmt in b.statements:
            for var in _get_statement_defs(stmt):
                def_sites.setdefault(var, set()).add(b)

    for var, sites in def_sites.items():
        worklist = list(sites)
        has_phi: Set[int] = set()
        added_to_worklist: Set[int] = set(b.block_id for b in sites)

        while worklist:
            x = worklist.pop(0)
            for y in x.df:
                if y.block_id not in has_phi:
                    lineno = y.statements[0].lineno if y.statements else 0
                    phi = PhiNode(
                        target_var=var,
                        base_var=var,
                        operands={p.block_id: None for p in y.predecessors},
                        lineno=lineno
                    )
                    y.phi_nodes[var] = phi
                    has_phi.add(y.block_id)
                    if y.block_id not in added_to_worklist:
                        added_to_worklist.add(y.block_id)
                        worklist.append(y)


class SSARenamer:
    """
    Algorithm 2 Phase 2 (Dominator Tree Renaming):
    Recursive traversal down the dominator tree giving each assignment a fresh
    version number and resolving each use to the currently-live version on that specific path.
    """
    def __init__(self, cfg: CFG, known_globals: Optional[Set[str]] = None) -> None:
        self.cfg = cfg
        self.counters: Dict[str, int] = {}
        self.stacks: Dict[str, List[str]] = {}
        self.known_globals = known_globals or set(dir(builtins))
        self.undefined_uses: List[Dict[str, Any]] = []
        self.maybe_undefined_vars: Set[str] = set()
        self.var_version_map: Dict[str, str] = {}  # renamed_version -> base_var
        self.version_definitions: Dict[str, Tuple[int, Optional[ast.AST]]] = {} # version -> (lineno, value_node)
        self.var_types: Dict[str, str] = {}  # ssa_var -> inferred type
        self.var_dicts: Dict[str, Set[Any]] = {} # ssa_var -> known dict keys
        self.var_seq_lengths: Dict[str, int] = {} # ssa_var -> known list/tuple length

    def _new_version(self, base_var: str) -> str:
        count = self.counters.get(base_var, 0) + 1
        self.counters[base_var] = count
        version = f"{base_var}{count}"
        self.var_version_map[version] = base_var
        return version

    def rename(self) -> None:
        """Executes recursive renaming down the dominator tree with two-pass propagation."""
        if not self.cfg.entry_block:
            return
        # Pass 1: Recursive dominator tree traversal
        self._rename_block(self.cfg.entry_block)

        # Pass 2: Identify phi-nodes with undefined incoming paths and propagate
        changed = True
        while changed:
            changed = False
            for b in self.cfg.get_reachable_blocks():
                for var, phi in b.phi_nodes.items():
                    is_undef = any(
                        op == "UNDEFINED" or (op in self.maybe_undefined_vars and op is not None)
                        for op in phi.operands.values()
                    )
                    if is_undef:
                        if phi.target_var and phi.target_var not in self.maybe_undefined_vars:
                            self.maybe_undefined_vars.add(phi.target_var)
                            changed = True

        # Pass 3: Re-verify uses against resolved maybe_undefined_vars
        for b in self.cfg.get_reachable_blocks():
            for stmt in b.statements:
                self._check_maybe_undefined_in_stmt(stmt)

    def _rename_block(self, block: BasicBlock) -> None:
        pushed: List[str] = []

        # 1. Rename phi-node targets in this block
        for var, phi in block.phi_nodes.items():
            new_ver = self._new_version(var)
            phi.target_var = new_ver
            self.stacks.setdefault(var, []).append(new_ver)
            pushed.append(var)
            self.version_definitions[new_ver] = (phi.lineno, None)

        # 2. Rename statements in this block
        for stmt in block.statements:
            self._rename_statement(stmt, block, pushed)

        # 3. Update phi-function operands in successor blocks
        for succ in block.successors:
            for var, phi in succ.phi_nodes.items():
                if var in self.stacks and self.stacks[var]:
                    current_ver = self.stacks[var][-1]
                    phi.operands[block.block_id] = current_ver
                else:
                    phi.operands[block.block_id] = "UNDEFINED"

        # 4. Recurse down dominator tree children
        for child in block.dom_children:
            self._rename_block(child)

        # 5. Pop versions pushed in this block to restore parent scope
        for var in pushed:
            if self.stacks.get(var):
                self.stacks[var].pop()

    def _rename_statement(self, stmt: ast.stmt, block: BasicBlock, pushed: List[str]) -> None:
        """Renames uses (loads) and defs (stores) inside an AST statement."""
        if isinstance(stmt, ast.Assign):
            self._rename_expr_uses(stmt.value, stmt.lineno)
            for target in stmt.targets:
                self._rename_target_defs(target, stmt.lineno, pushed, value_node=stmt.value)
        elif isinstance(stmt, ast.AnnAssign):
            if stmt.value:
                self._rename_expr_uses(stmt.value, stmt.lineno)
            self._rename_target_defs(stmt.target, stmt.lineno, pushed, value_node=stmt.value, annotation_node=stmt.annotation)
        elif isinstance(stmt, ast.AugAssign):
            # BUG-2 FIX: Capture the base var name BEFORE _rename_expr_uses mutates target.id
            aug_base_var = stmt.target.id if isinstance(stmt.target, ast.Name) else None
            self._rename_expr_uses(stmt.target, stmt.lineno)  # reads from target (load context)
            self._rename_expr_uses(stmt.value, stmt.lineno)
            # Pass aug_base_var so _rename_target_defs uses the original name, not the SSA-renamed one
            if aug_base_var is not None and isinstance(stmt.target, ast.Name):
                stmt.target.id = aug_base_var  # restore pre-read name so _rename_target_defs names correctly
            self._rename_target_defs(stmt.target, stmt.lineno, pushed, value_node=stmt.value)
        elif isinstance(stmt, ast.Expr):
            self._rename_expr_uses(stmt.value, stmt.lineno)
        elif isinstance(stmt, ast.Return):
            if stmt.value:
                self._rename_expr_uses(stmt.value, stmt.lineno)

    def _rename_expr_uses(self, expr: ast.AST, lineno: int) -> None:
        """Walks expression replacing variable loads with active SSA versions."""
        if isinstance(expr, ast.Name):
            if isinstance(expr.ctx, ast.Load):
                var = expr.id
                if var in self.known_globals:
                    return
                if var in self.stacks and self.stacks[var]:
                    active_ver = self.stacks[var][-1]
                    expr.id = active_ver
                else:
                    self.undefined_uses.append({
                        'error_type': 'Identity Hallucination (IH)',
                        'variable_name': var,
                        'ssa_version': None,
                        'line_number': lineno,
                        'detail': f"Variable '{var}' used before definition."
                    })
        elif isinstance(expr, ast.Call):
            if isinstance(expr.func, ast.Name):
                func_name = expr.func.id
                if func_name in self.stacks and self.stacks[func_name]:
                    expr.func.id = self.stacks[func_name][-1]
            elif isinstance(expr.func, ast.Attribute):
                self._rename_expr_uses(expr.func.value, lineno)
            else:
                self._rename_expr_uses(expr.func, lineno)
            for arg in expr.args:
                self._rename_expr_uses(arg, lineno)
            for kw in expr.keywords:
                self._rename_expr_uses(kw.value, lineno)
        elif isinstance(expr, ast.Subscript):
            self._rename_expr_uses(expr.value, lineno)
            self._rename_expr_uses(expr.slice, lineno)
        elif isinstance(expr, ast.BinOp):
            self._rename_expr_uses(expr.left, lineno)
            self._rename_expr_uses(expr.right, lineno)
        elif isinstance(expr, ast.UnaryOp):
            self._rename_expr_uses(expr.operand, lineno)
        elif isinstance(expr, ast.Compare):
            self._rename_expr_uses(expr.left, lineno)
            for comparator in expr.comparators:
                self._rename_expr_uses(comparator, lineno)
        elif isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
            for elt in expr.elts:
                self._rename_expr_uses(elt, lineno)
        elif isinstance(expr, ast.Dict):
            for k in expr.keys:
                if k:
                    self._rename_expr_uses(k, lineno)
            for v in expr.values:
                self._rename_expr_uses(v, lineno)
        elif isinstance(expr, ast.Attribute):
            self._rename_expr_uses(expr.value, lineno)
        elif isinstance(expr, ast.FormattedValue):
            self._rename_expr_uses(expr.value, lineno)
        elif isinstance(expr, ast.JoinedStr):
            for val in expr.values:
                self._rename_expr_uses(val, lineno)

    def _check_maybe_undefined_in_stmt(self, stmt: ast.stmt) -> None:
        """Post-pass check to flag any load whose SSA version resolved to maybe_undefined."""
        for node in ast.walk(stmt):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id in self.maybe_undefined_vars:
                    base_var = self.var_version_map.get(node.id, node.id)
                    # BUG-4 FIX: Use a set key for O(1) deduplication instead of O(N) list search
                    err_key = ('Identity Hallucination (IH)', base_var, stmt.lineno, node.id)
                    if not hasattr(self, '_seen_maybe_undef'):
                        self._seen_maybe_undef: Set[tuple] = set()
                    if err_key not in self._seen_maybe_undef:
                        self._seen_maybe_undef.add(err_key)
                        self.undefined_uses.append({
                            'error_type': 'Identity Hallucination (IH)',
                            'variable_name': base_var,
                            'ssa_version': node.id,
                            'line_number': stmt.lineno,
                            'detail': f"Variable '{base_var}' is potentially undefined (defined only on conditional branch)."
                        })

    def _rename_target_defs(self, target: ast.expr, lineno: int, pushed: List[str], value_node: Optional[ast.AST] = None, annotation_node: Optional[ast.AST] = None) -> None:
        """Assigns fresh SSA versions to definition targets and extracts type/structure info."""
        if isinstance(target, ast.Name):
            base_var = target.id
            new_ver = self._new_version(base_var)
            target.id = new_ver
            self.stacks.setdefault(base_var, []).append(new_ver)
            pushed.append(base_var)
            self.version_definitions[new_ver] = (lineno, value_node)
            
            if annotation_node and isinstance(annotation_node, ast.Name):
                self.var_types[new_ver] = annotation_node.id
                self.var_types[base_var] = annotation_node.id
            elif base_var in self.var_types:
                self.var_types[new_ver] = self.var_types[base_var]
            elif value_node is not None:
                inferred_type, extra_info = self._infer_node_type(value_node)
                self.var_types[new_ver] = inferred_type
                if inferred_type == "dict" and "keys" in extra_info:
                    self.var_dicts[new_ver] = extra_info["keys"]
                elif inferred_type in ("list", "tuple") and "length" in extra_info:
                    self.var_seq_lengths[new_ver] = extra_info["length"]
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._rename_target_defs(elt, lineno, pushed, value_node=None)

    def _infer_node_type(self, node: ast.AST) -> Tuple[str, Dict[str, Any]]:
        """Infers the abstract type of an AST node and extracts structural metadata."""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return "bool", {}
            elif isinstance(node.value, int):
                return "int", {}
            elif isinstance(node.value, float):
                return "float", {}
            elif isinstance(node.value, str):
                return "str", {"length": len(node.value)}
            elif node.value is None:
                return "NoneType", {}
        elif isinstance(node, ast.List):
            return "list", {"length": len(node.elts)}
        elif isinstance(node, ast.Tuple):
            return "tuple", {"length": len(node.elts)}
        elif isinstance(node, ast.Set):
            return "set", {"length": len(node.elts)}
        elif isinstance(node, ast.Dict):
            keys = set()
            for k in node.keys:
                if isinstance(k, ast.Constant):
                    keys.add(k.value)
            return "dict", {"keys": keys}
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_id = node.func.id
                if func_id in ('len', 'int', 'ord', 'count'):
                    return "int", {}
                elif func_id in ('str', 'chr', 'hex', 'bin'):
                    return "str", {}
                elif func_id in ('float',):
                    return "float", {}
                elif func_id in ('bool',):
                    return "bool", {}
                elif func_id in ('list',):
                    return "list", {}
                elif func_id in ('dict',):
                    return "dict", {}
                elif func_id in ('set',):
                    return "set", {}
                elif func_id in ('tuple',):
                    return "tuple", {}
        elif isinstance(node, ast.Name):
            if node.id in self.var_types:
                return self.var_types[node.id], {}
            if node.id in self.var_version_map and self.var_version_map[node.id] in self.var_types:
                return self.var_types[self.var_version_map[node.id]], {}
        elif isinstance(node, ast.BinOp):
            left_t, _ = self._infer_node_type(node.left)
            right_t, _ = self._infer_node_type(node.right)
            if left_t == "int" and right_t == "int":
                return "int", {}
            elif left_t == "str" and right_t == "str":
                return "str", {}
            elif left_t == "list" and right_t == "list":
                return "list", {}
            elif "float" in (left_t, right_t) and all(t in ("int", "float") for t in (left_t, right_t)):
                return "float", {}

        return "unknown", {}


# --- Core Analyzer & SSA Transformer API ---

@dataclass
class FunctionSSA:
    """Container for a function's CFG and SSA Renamer."""
    func_name: str
    cfg: CFG
    renamer: SSARenamer


class SSATransformer:
    """
    Facade class that orchestrates complete SSA transformation on an AST:
    1. Builds Control Flow Graphs for functions and module bodies
    2. Computes Dominator Tree & Dominance Frontiers (compute_dominators)
    3. Places φ-functions at iterated dominance frontiers (insert_phi_nodes - Algorithm 2 Phase 1)
    4. Recursively renames variables down the dominator tree (SSARenamer - Algorithm 2 Phase 2)
    """
    def __init__(self) -> None:
        self.function_ssas: Dict[str, FunctionSSA] = {}
        self.module_cfg: Optional[CFG] = None
        self.module_renamer: Optional[SSARenamer] = None
        self.all_renamers: List[SSARenamer] = []

    def transform(self, tree: ast.AST) -> List[SSARenamer]:
        """Runs the two-phase SSA algorithm on functions and module statements."""
        self.function_ssas.clear()
        self.all_renamers.clear()

        known_globals = set(dir(builtins))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    known_globals.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    known_globals.add(alias.asname or alias.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                known_globals.add(node.name)

        if isinstance(tree, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cfg_builder = CFGBuilder()
            cfg = cfg_builder.build(tree)
            compute_dominators(cfg)
            insert_phi_nodes(cfg)
            renamer = SSARenamer(cfg, known_globals=known_globals)
            for arg in tree.args.args + tree.args.posonlyargs + tree.args.kwonlyargs:
                if arg.annotation and isinstance(arg.annotation, ast.Name):
                    renamer.var_types[arg.arg] = arg.annotation.id
            renamer.rename()
            self.function_ssas[tree.name] = FunctionSSA(tree.name, cfg, renamer)
            self.all_renamers.append(renamer)
        elif isinstance(tree, ast.Module):
            for stmt in tree.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    cfg_builder = CFGBuilder()
                    cfg = cfg_builder.build(stmt)
                    compute_dominators(cfg)
                    insert_phi_nodes(cfg)
                    renamer = SSARenamer(cfg, known_globals=known_globals)
                    for arg in stmt.args.args + stmt.args.posonlyargs + stmt.args.kwonlyargs:
                        if arg.annotation and isinstance(arg.annotation, ast.Name):
                            renamer.var_types[arg.arg] = arg.annotation.id
                    renamer.rename()
                    self.function_ssas[stmt.name] = FunctionSSA(stmt.name, cfg, renamer)
                    self.all_renamers.append(renamer)

            cfg_builder = CFGBuilder()
            self.module_cfg = cfg_builder.build(tree)
            compute_dominators(self.module_cfg)
            insert_phi_nodes(self.module_cfg)
            self.module_renamer = SSARenamer(self.module_cfg, known_globals=known_globals)
            self.module_renamer.rename()
            self.all_renamers.append(self.module_renamer)

        return self.all_renamers


class CodeAnalyzer:
    """
    Facade class providing an easy interface for parsing code,
    extracting AST features, building a CFG, and generating SSA form.
    """
    def __init__(self, source_code: str) -> None:
        self.source_code = source_code
        self.ast_tree: Optional[ast.Module] = None
        self.extractor = CodeFeatureExtractor()
        self.ssa_transformer = SSATransformer()
        self.all_renamers: List[SSARenamer] = []

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
        cfg_builder = CFGBuilder()
        return cfg_builder.build(self.ast_tree)

    def transform_ssa(self) -> List[SSARenamer]:
        """Builds CFG and runs the full two-phase SSA transformation."""
        if self.ast_tree is None:
            raise ValueError("AST has not been generated. Call parse() first.")
        self.all_renamers = self.ssa_transformer.transform(self.ast_tree)
        return self.all_renamers


# --- Comprehensive 6-Type Static Hallucination Detector ---

class StaticDetector(ast.NodeVisitor):
    """
    Analyzes CFG and SSA-transformed structures to detect all 6 statically-detectable hallucinations:
    1. DCH (Data Compliance Hallucination): Incompatible data types in operations or method calls.
    2. SAH (Structure Access Hallucination): Dict missing keys, sequence out-of-bounds, range step 0.
    3. IH (Identity Hallucination): Variable used before assignment or conditionally undefined.
    4. ESH (External Source Hallucination): Module/function called but not defined/imported.
    5. PCH (Physical Constraint Hallucination): Unbounded data-structure growth inside loops.
    6. CBH (Computational Boundary Hallucination): Infinite loops (while True / unmutated vars), recursion with no base-case.
    """
    def __init__(self, renamers: Optional[List[SSARenamer]] = None, function_ssas: Optional[Dict[str, FunctionSSA]] = None) -> None:
        self.errors: List[Dict[str, Any]] = []
        self.defined_names = set(dir(builtins))
        self.renamers = renamers or []
        self.function_ssas = function_ssas or {}
        self.var_values: Dict[str, ast.AST] = {}
        self.var_types: Dict[str, str] = {}
        self.var_dicts: Dict[str, Set[Any]] = {}
        self.var_seq_lengths: Dict[str, int] = {}

        for renamer in self.renamers:
            for ver, (_, val_node) in renamer.version_definitions.items():
                self.defined_names.add(ver)
                if val_node is not None:
                    self.var_values[ver] = val_node
            for ver, vtype in renamer.var_types.items():
                self.var_types[ver] = vtype
            for ver, keys in renamer.var_dicts.items():
                self.var_dicts[ver] = keys
                # BUG-1 companion: Also index by base var so the original-tree subscript visitor finds it
                base = renamer.var_version_map.get(ver, ver)
                if base not in self.var_dicts:
                    self.var_dicts[base] = keys
            for ver, length in renamer.var_seq_lengths.items():
                self.var_seq_lengths[ver] = length
                base = renamer.var_version_map.get(ver, ver)
                if base not in self.var_seq_lengths:
                    self.var_seq_lengths[base] = length
            for ver, vtype in renamer.var_types.items():
                base = renamer.var_version_map.get(ver, ver)
                if base not in self.var_types:
                    self.var_types[base] = vtype

            for err in renamer.undefined_uses:
                self.errors.append({
                    'error_type': err['error_type'],
                    'variable_name': err['variable_name'],
                    'line_number': err['line_number'],
                    'detail': err.get('detail')
                })

    def _get_base_var(self, name: str) -> str:
        """Maps an SSA variable name back to its base variable name.

        Priority:
        1. Exact hit in var_version_map (authoritative SSA metadata).
        2. Greedy regex strip of a trailing pure-digit suffix — only applied when
           the candidate base name actually appears in var_version_map values,
           preventing false strips of real identifiers like 'md5' or 'i18n'.
        3. Return original name unchanged.
        """
        # 1. Authoritative lookup
        for renamer in self.renamers:
            if name in renamer.var_version_map:
                return renamer.var_version_map[name]
        # 2. BUG-6 FIX: Use greedy match (not non-greedy \w*?) so 'x10' → 'x', 'md5' → 'md5'
        #    only strip if result is a known base var; otherwise keep the name intact.
        m = re.match(r'^([a-zA-Z_]\w*\D)\d+$', name)
        if m:
            candidate = m.group(1)
            all_base_vars: Set[str] = set()
            for renamer in self.renamers:
                all_base_vars.update(renamer.var_version_map.values())
            if candidate in all_base_vars:
                return candidate
        return name

    def _get_inferred_type(self, node: ast.AST) -> str:
        """Resolves inferred type for expression nodes."""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return "bool"
            elif isinstance(node.value, int):
                return "int"
            elif isinstance(node.value, float):
                return "float"
            elif isinstance(node.value, str):
                return "str"
            elif node.value is None:
                return "NoneType"
        elif isinstance(node, ast.List):
            return "list"
        elif isinstance(node, ast.Tuple):
            return "tuple"
        elif isinstance(node, ast.Dict):
            return "dict"
        elif isinstance(node, ast.Set):
            return "set"
        elif isinstance(node, ast.Name):
            if node.id in self.var_types:
                return self.var_types[node.id]
            base = self._get_base_var(node.id)
            if base in self.var_types:
                return self.var_types[base]
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                fid = node.func.id
                if fid in ('len', 'int', 'ord'):
                    return "int"
                elif fid in ('str', 'chr'):
                    return "str"
                elif fid in ('float',):
                    return "float"
                elif fid in ('bool',):
                    return "bool"
                elif fid in ('list',):
                    return "list"
                elif fid in ('dict',):
                    return "dict"
        elif isinstance(node, ast.BinOp):
            lt = self._get_inferred_type(node.left)
            rt = self._get_inferred_type(node.right)
            if lt == rt and lt != "unknown":
                return lt
        return "unknown"

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
            if arg.annotation and isinstance(arg.annotation, ast.Name):
                self.var_types[arg.arg] = arg.annotation.id
        if node.args.vararg:
            self.defined_names.add(node.args.vararg.arg)
        if node.args.kwarg:
            self.defined_names.add(node.args.kwarg.arg)

        self._check_cbh_recursion(node)
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
            if isinstance(node.annotation, ast.Name):
                self.var_types[node.target.id] = node.annotation.id
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        # Check DCH: Incompatible types in binary operation (e.g., int + str)
        left_type = self._get_inferred_type(node.left)
        right_type = self._get_inferred_type(node.right)

        if left_type != "unknown" and right_type != "unknown":
            is_dch = False
            msg = ""
            if isinstance(node.op, ast.Add):
                if (left_type in ("int", "float") and right_type == "str") or (left_type == "str" and right_type in ("int", "float")):
                    is_dch = True
                    msg = f"Cannot add numeric '{left_type}' and text '{right_type}'"
                elif (left_type == "list" and right_type not in ("list", "unknown")) or (right_type == "list" and left_type not in ("list", "unknown")):
                    is_dch = True
                    msg = f"Cannot concatenate '{left_type}' and '{right_type}'"
                elif left_type == "dict" or right_type == "dict":
                    is_dch = True
                    msg = "Unsupported operand '+' for dictionary"
            elif isinstance(node.op, (ast.Sub, ast.Div, ast.FloorDiv, ast.Mod)):
                if left_type == "str" or right_type == "str":
                    if not (isinstance(node.op, ast.Mod) and left_type == "str"):
                        is_dch = True
                        msg = f"Unsupported arithmetic operation '{type(node.op).__name__}' between '{left_type}' and '{right_type}'"
                elif left_type in ("list", "dict", "set") or right_type in ("list", "dict", "set"):
                    is_dch = True
                    msg = f"Unsupported arithmetic operation on container types '{left_type}' and '{right_type}'"
            elif isinstance(node.op, ast.Mult):
                if left_type == "str" and right_type == "str":
                    is_dch = True
                    msg = "Cannot multiply sequence by non-int of type 'str'"
                elif left_type == "dict" or right_type == "dict":
                    is_dch = True
                    msg = "Cannot multiply dictionary"
                # BUG-7 FIX: list * list and set * anything are invalid
                elif left_type == "list" and right_type not in ("int", "unknown"):
                    is_dch = True
                    msg = f"Cannot multiply list by non-int type '{right_type}'"
                elif right_type == "list" and left_type not in ("int", "unknown"):
                    is_dch = True
                    msg = f"Cannot multiply list by non-int type '{left_type}'"
                elif left_type == "set" or right_type == "set":
                    is_dch = True
                    msg = f"Unsupported multiplication on 'set' type"

            if is_dch:
                self.errors.append({
                    'error_type': 'Data Compliance Hallucination (DCH)',
                    'variable_name': f"{left_type} {type(node.op).__name__} {right_type}",
                    'line_number': node.lineno,
                    'detail': msg
                })

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        is_esh = False
        if isinstance(node.func, ast.Name):
            if node.func.id not in self.defined_names:
                self.errors.append({
                    'error_type': 'External Source Hallucination (ESH)',
                    'variable_name': node.func.id,
                    'line_number': node.lineno,
                    'detail': f"Function '{node.func.id}' called without definition or import."
                })
                is_esh = True
        elif isinstance(node.func, ast.Attribute):
            obj_type = self._get_inferred_type(node.func.value)
            method = node.func.attr
            if obj_type in ("int", "float") and method in ('append', 'extend', 'pop', 'keys', 'values', 'items', 'upper', 'lower', 'split', 'strip'):
                self.errors.append({
                    'error_type': 'Data Compliance Hallucination (DCH)',
                    'variable_name': f"{obj_type}.{method}()",
                    'line_number': node.lineno,
                    'detail': f"Invalid method '{method}' invoked on primitive type '{obj_type}'."
                })
            elif obj_type == "str" and method in ('append', 'extend', 'pop', 'keys', 'values', 'items', 'add'):
                self.errors.append({
                    'error_type': 'Data Compliance Hallucination (DCH)',
                    'variable_name': f"str.{method}()",
                    'line_number': node.lineno,
                    'detail': f"Invalid method '{method}' invoked on string type."
                })
            elif obj_type == "list" and method in ('upper', 'lower', 'split', 'strip', 'keys', 'values', 'items', 'add'):
                self.errors.append({
                    'error_type': 'Data Compliance Hallucination (DCH)',
                    'variable_name': f"list.{method}()",
                    'line_number': node.lineno,
                    'detail': f"Invalid method '{method}' invoked on list type."
                })

            if isinstance(node.func.value, ast.Name):
                if node.func.value.id not in self.defined_names and node.func.value.id not in dir(builtins):
                    self.errors.append({
                        'error_type': 'External Source Hallucination (ESH)',
                        'variable_name': f"{node.func.value.id}.{node.func.attr}",
                        'line_number': node.lineno,
                        'detail': f"Module or receiver '{node.func.value.id}' not defined or imported."
                    })
                    is_esh = True

        if isinstance(node.func, ast.Name) and node.func.id == 'range':
            if len(node.args) == 3:
                step_arg = node.args[2]
                if isinstance(step_arg, ast.Constant) and step_arg.value == 0:
                    self.errors.append({
                        'error_type': 'Structure Access Hallucination (SAH)',
                        'variable_name': 'range() step of 0',
                        'line_number': node.lineno,
                        'detail': "range() step argument must not be zero."
                    })

        # BUG-5 FIX: Always visit arguments regardless of ESH. Only skip visiting node.func
        # itself when ESH flagged on a bare Name, to avoid cascading false positives.
        # For Attribute calls, the object was already inspected in the ESH attribute branch.
        if not is_esh or isinstance(node.func, ast.Attribute):
            self.visit(node.func)
        for arg in node.args:
            self.visit(arg)
        for kw in node.keywords:
            self.visit(kw)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        target_len = None
        if isinstance(node.value, (ast.List, ast.Tuple)):
            target_len = len(node.value.elts)
        elif isinstance(node.value, ast.Name):
            if node.value.id in self.var_seq_lengths:
                target_len = self.var_seq_lengths[node.value.id]
            elif node.value.id in self.var_values:
                val_node = self.var_values[node.value.id]
                if isinstance(val_node, (ast.List, ast.Tuple)):
                    target_len = len(val_node.elts)

        if target_len is not None and isinstance(node.slice, ast.Constant):
            if isinstance(node.slice.value, int):
                if node.slice.value >= target_len or node.slice.value < -target_len:
                    self.errors.append({
                        'error_type': 'Structure Access Hallucination (SAH)',
                        'variable_name': f"index {node.slice.value} out of bounds",
                        'line_number': node.lineno,
                        'detail': f"Index {node.slice.value} is out of bounds for sequence of statically known length {target_len}."
                    })

        if isinstance(node.value, ast.Name) and isinstance(node.slice, ast.Constant):
            if node.value.id in self.var_dicts:
                known_keys = self.var_dicts[node.value.id]
                key_val = node.slice.value
                if key_val not in known_keys:
                    self.errors.append({
                        'error_type': 'Structure Access Hallucination (SAH)',
                        'variable_name': f"dict key '{key_val}'",
                        'line_number': node.lineno,
                        'detail': f"Key '{key_val}' is provably absent from dictionary."
                    })

        self.generic_visit(node)

    def _walk_loop_body_no_nested_funcs(self, stmts: List[ast.stmt]):
        """Yields all AST nodes inside loop body statements, but does NOT
        descend into nested FunctionDef / AsyncFunctionDef bodies.
        This prevents a 'return' inside a lambda or helper function from
        incorrectly marking the enclosing while-loop as having an exit.
        """
        for stmt in stmts:
            yield stmt
            for child in ast.walk(stmt):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child is not stmt:
                    # Do not descend further into nested function bodies
                    continue
                yield child

    def visit_While(self, node: ast.While) -> None:
        is_const_true = isinstance(node.test, ast.Constant) and bool(node.test.value)

        # BUG-8 FIX: Only check for Break/Return in the direct loop body,
        # excluding nested function definitions which have their own scopes.
        has_break_or_return = False
        for child in self._walk_loop_body_no_nested_funcs(node.body):
            if isinstance(child, (ast.Break, ast.Return)):
                has_break_or_return = True
                break

        if is_const_true and not has_break_or_return:
            self.errors.append({
                'error_type': 'Computational Boundary Hallucination (CBH)',
                'variable_name': 'while True',
                'line_number': node.lineno,
                'detail': "Infinite loop detected: 'while True' loop contains no reachable break or return."
            })

        if not is_const_true and not has_break_or_return:
            cond_base_vars = set()
            for child in ast.walk(node.test):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                    cond_base_vars.add(self._get_base_var(child.id))

            body_defs = set()
            for stmt in node.body:
                for var in _get_statement_defs(stmt):
                    body_defs.add(self._get_base_var(var))
                for child in ast.walk(stmt):
                    if isinstance(child, ast.AugAssign) and isinstance(child.target, ast.Name):
                        body_defs.add(self._get_base_var(child.target.id))

            local_cond_vars = {v for v in cond_base_vars if v not in dir(builtins)}
            if local_cond_vars and not (local_cond_vars & body_defs):
                var_names = ", ".join(f"'{v}'" for v in sorted(local_cond_vars))
                self.errors.append({
                    'error_type': 'Computational Boundary Hallucination (CBH)',
                    'variable_name': f"loop condition on {var_names}",
                    'line_number': node.lineno,
                    'detail': f"Loop condition variable(s) {var_names} are never mutated inside the loop body."
                })

        self._check_pch_loop(node)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._check_pch_loop(node)
        self.generic_visit(node)

    def _check_pch_loop(self, node: Union[ast.While, ast.For]) -> None:
        """Detects unbounded collection growth or exponential memory consumption inside loops."""
        growth_calls: List[Tuple[str, int]] = []
        has_bound_guard = False

        for child in ast.walk(node):
            if isinstance(child, ast.If):
                for guard_node in ast.walk(child.test):
                    if isinstance(guard_node, ast.Call) and isinstance(guard_node.func, ast.Name) and guard_node.func.id == 'len':
                        has_bound_guard = True
                    elif isinstance(guard_node, ast.Compare):
                        has_bound_guard = True
            elif isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                if child.func.attr in ('append', 'extend', 'add', 'insert'):
                    growth_calls.append((child.func.attr, child.lineno))
            elif isinstance(child, ast.AugAssign) and isinstance(child.op, ast.Add):
                if isinstance(child.target, ast.Name) and isinstance(child.value, ast.Name):
                    if self._get_base_var(child.target.id) == self._get_base_var(child.value.id):
                        self.errors.append({
                            'error_type': 'Physical Constraint Hallucination (PCH)',
                            'variable_name': child.target.id,
                            'line_number': child.lineno,
                            'detail': f"Exponential memory growth detected on variable '{child.target.id}' inside loop."
                        })
            elif isinstance(child, ast.Assign) and isinstance(child.value, ast.BinOp) and isinstance(child.value.op, ast.Add):
                if len(child.targets) == 1 and isinstance(child.targets[0], ast.Name):
                    tgt = self._get_base_var(child.targets[0].id)
                    if isinstance(child.value.left, ast.Name) and isinstance(child.value.right, ast.Name):
                        if self._get_base_var(child.value.left.id) == tgt and self._get_base_var(child.value.right.id) == tgt:
                            self.errors.append({
                                'error_type': 'Physical Constraint Hallucination (PCH)',
                                'variable_name': child.targets[0].id,
                                'line_number': child.lineno,
                                'detail': f"Exponential memory growth detected on variable '{tgt}' inside loop."
                            })

        if isinstance(node, ast.While) and not has_bound_guard and growth_calls:
            is_infinite = isinstance(node.test, ast.Constant) and bool(node.test.value)
            if is_infinite:
                for method, lno in growth_calls:
                    self.errors.append({
                        'error_type': 'Physical Constraint Hallucination (PCH)',
                        'variable_name': f".{method}() in infinite loop",
                        'line_number': lno,
                        'detail': f"Unbounded collection growth via '.{method}()' inside unconstrained loop (excessive memory consumption)."
                    })
                    break

    def _check_cbh_recursion(self, func_node: ast.FunctionDef) -> None:
        """Detects direct recursive functions that lack a base-case / non-recursive return path."""
        has_recursive_call = False
        recursive_call_lineno = func_node.lineno

        for child in ast.walk(func_node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name) and child.func.id == func_node.name:
                    has_recursive_call = True
                    recursive_call_lineno = child.lineno

        if not has_recursive_call:
            return

        has_base_case = False
        for stmt in func_node.body:
            if isinstance(stmt, ast.If):
                has_base_case = True
                break
            elif isinstance(stmt, ast.Return):
                calls_self = any(
                    isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == func_node.name
                    for c in ast.walk(stmt)
                )
                if not calls_self:
                    has_base_case = True
                    break

        if not has_base_case:
            self.errors.append({
                'error_type': 'Computational Boundary Hallucination (CBH)',
                'variable_name': f"recursive function '{func_node.name}'",
                'line_number': recursive_call_lineno,
                'detail': f"Unbounded direct recursion: function '{func_node.name}' contains no reachable base-case condition."
            })


def detect_hallucinations(source_code: str) -> List[Dict[str, Any]]:
    """
    Parses code, executes two-phase CFG-backed SSA transformation,
    and runs StaticDetector to detect all 6 statically-identifiable hallucination types:
    DCH, SAH, IH, ESH, PCH, and CBH.
    """
    analyzer = CodeAnalyzer(source_code)
    analyzer.parse()

    # BUG-1 FIX: Deep-copy the original AST before SSA transformation.
    # SSARenamer mutates ast.Name.id nodes in-place (e.g. 'x' -> 'x1').
    # StaticDetector must walk the ORIGINAL tree to correctly resolve user-facing
    # variable names, dict/sequence metadata (var_values, var_seq_lengths), and
    # function parameter names. Without this copy, the detector sees 'age1' instead
    # of 'age' and misses SAH/DCH entries that depend on the original name lookups.
    original_tree = copy.deepcopy(analyzer.ast_tree)

    renamers = analyzer.transform_ssa()  # mutates analyzer.ast_tree in-place

    detector = StaticDetector(renamers=renamers, function_ssas=analyzer.ssa_transformer.function_ssas)
    detector.visit(original_tree)  # walk the un-mutated original tree

    seen = set()
    unique_errors = []
    for err in detector.errors:
        if 'type_code' not in err:
            m = re.search(r'\((DCH|SAH|IH|ESH|PCH|CBH)\)', err.get('error_type', ''))
            err['type_code'] = m.group(1) if m else 'UNKNOWN'
        if 'location' not in err:
            err['location'] = err.get('variable_name', 'unknown')
        if 'variable_name' not in err:
            err['variable_name'] = err.get('location', 'unknown')
        err['source'] = 'static'

        key = (err['error_type'], err['variable_name'], err['line_number'])
        if key not in seen:
            seen.add(key)
            unique_errors.append(err)

    return unique_errors


# --- Mock Testing ---

if __name__ == "__main__":
    MOCK_CODE = '''
import math

# 1. CBH: Recursive function with no base-case
def infinite_recurse(n):
    return infinite_recurse(n - 1)

def demo(a, b):
    # 2. IH: Undefined variable
    x = a + b
    y = x + undefined_var
    
    # 3. ESH: Unimported function call
    res = unknown_func(y)
    
    # 4. DCH: Incompatible types (int + str)
    age = 25
    bad_type = age + " years"
    
    # 5. SAH: Dict key not found & list out of bounds & range step 0
    config = {"host": "localhost", "port": 8080}
    missing_val = config["database"]
    arr = [1, 2, 3]
    bad_idx = arr[10]
    for i in range(0, 10, 0):
        pass
        
    # 6. PCH: Unbounded memory growth in loop
    buf = []
    while True:
        buf.append("infinite_data")
'''
    print("Testing 6-type static hallucination detection on mock code...")
    errors = detect_hallucinations(MOCK_CODE)
    for err in errors:
        print(f"[{err['error_type']}] -> Symbol: '{err['variable_name']}' at line {err['line_number']} | Detail: {err.get('detail')}")
