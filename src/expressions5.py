from dbobjects import DBDataset, DBFile, DBNamedQuery, DBFileSet
import json, time

from lark import Lark
from lark import Transformer, Tree, Token
from lark.visitors import Interpreter
import pprint


grammar = """
exp:  add_exp                                   -> f_

add_exp : add_exp "+" mul_exp                   -> add
        | add_exp "-" mul_exp                   -> subtract
        | mul_exp                               -> f_
    
mul_exp : mul_exp "*" term_with_params          -> mult
        | term_with_params                      -> f_
    
term_with_params    : with_clause term2         
                    | term2                     -> f_
        
with_clause :  "with" param_def ("," param_def)*

param_def: CNAME "=" constant

term2   : term                                      -> f_
        | filterable_term "where" meta_exp          -> meta_filter

?term   : dataset_exp                               -> f_
        | filterable_term                           -> f_
    
?filterable_term: union                                    -> f_
    | join                                      -> f_
    | "filter" CNAME "(" filter_params ")" "(" exp_list ")"         -> filter
    | "parents" "(" exp ")"                     -> parents_of
    | "children" "(" exp ")"                    -> children_of
    | "query" namespace_name                    -> named_query
    | "(" exp ")"                               -> f_

union: "union" "(" exp_list ")"
    | "[" exp_list "]"

join: "join" "(" exp_list ")"
    | "{" exp_list "}"

exp_list: exp ("," exp)*                             

filter_params:    ( constant ("," constant)* )?                    -> filter_params

dataset_exp: "dataset" namespace_name ("where" meta_exp)?           -> dataset

namespace_name: (CNAME ":")? CNAME

?meta_exp:   meta_or                                -> f_

meta_or:    meta_and ( "or" meta_and )*

meta_and:   term_meta ( "and" term_meta )*

term_meta:  CNAME CMPOP constant                    -> cmp_op
    | constant "in" CNAME                           -> in_op
    | "(" meta_exp ")"                              -> f_
    | "!" term_meta                                 -> meta_not
    
constant : SIGNED_FLOAT                             -> float_constant                      
    | STRING                                        -> string_constant
    | SIGNED_INT                                    -> int_constant
    | BOOL                                          -> bool_constant

CMPOP: ">" | "<" | ">=" | "<=" | "==" | "=" | "!="

BOOL: "true" | "false"                              


%import common.CNAME
%import common.SIGNED_INT
%import common.SIGNED_FLOAT
%import common.ESCAPED_STRING       -> STRING
%import common.WS
%ignore WS
"""

CMP_OPS = [">" , "<" , ">=" , "<=" , "==" , "=" , "!="]


class Node(object):
    def __init__(self, typ, children=[], value=None):
        self.T = typ
        self.V = value
        self.C = children[:]

    def __str__(self):
        return "<Node %s v=%s c:%d>" % (self.T, self.V, len(self.C))

    __repr__ = __str__

    def __add__(self, lst):
        return Node(self.T, self.C + lst, self.V)

    def as_list(self):
        out = [self.T, self.V]
        for c in self.C:
                if isinstance(c, Node):
                        out.append(c.as_list())
                else:
                        out.append(c)
        return out
        
    def _pretty(self, indent=0):
        out = []
        out.append("%s%s %s" % ("  "*indent, self.T, '' if self.V is None else repr(self.V)))
        for c in self.C:
            if isinstance(c, Node):
                out += c._pretty(indent+2)
            else:
                out.append("%s%s" % ("  "*(indent+2), repr(c)))
        return out
        
    def pretty(self):
        return "\n".join(self._pretty())
        
    def jsonable(self):
        d = dict(T=self.T, V=self.V, C=[c.jsonable() if isinstance(c, Node) else c
                        for c in self.C]
        )
        d["///class///"] = "node"
        return d
        
    def to_json(self):
        return json.dumps(self.jsonable())

    @staticmethod
    def from_jsonable(data):
        if isinstance(data, dict) and data.get("///class///") == "node":
            return Node(data["T"],
                children = [Node.from_jsonable(c) for c in data.get("C", [])],
                value = data.get("V")
            )
        else:
            return data

    @staticmethod
    def from_json(text):
        return Node.from_jsonable(json.loads(text))

class Ascender(object):

    def __init__(self):
        self.Indent = ""

    def walk(self, node):
        if not isinstance(node, Node):
            return node
        node_type, children = node.T, node.C
        #print("Ascender.walk:", node_type, children)
        assert isinstance(node_type, str)
        #print("walk: in:", node.pretty())
        saved = self.Indent 
        self.Indent += "  "
        children = [self.walk(c) for c in children]
        self.Indent = saved
        #print("walk: children->", children)
        if hasattr(self, node_type):
            method = getattr(self, node_type)
            if hasattr(method, "pass_node") and getattr(method, "pass_node"):
                out = method(node)
            else:
                out = method(children, node.V)
        else:
            out = self.__default(node, children)
        return out
        
    def __default(self, node, children):
        return Node(node.T, children=children, value=node.V)

class _Converter(Transformer):
    
    def convert(self, tree, default_namespace):
        tree = self.transform(tree)
        return self._apply_params({"namespace":default_namespace}, tree)

    def f_(self, args):
        assert len(args) == 1
        return args[0]
    
    def int_constant(self, args):
        return int(args[0].value)
        
    def float_constant(self, args):
        return float(args[0].value)

    def bool_constant(self, args):
        #print("bool_constant:", args, args[0].value)
        return args[0].value == "true"
        
    def string_constant(self, args):
        s = args[0].value
        if s[0] == '"':
            s = s[1:-1]
        return s
        
    def named_query(self, args):
        assert len(args) == 1
        return Node("named_query", value = args[0].V)       # value = (namespace, name) - tuple
        
    def exp_list(self, args):
        return args

    def __default__(self, data, children, meta):
        #print("__default__:", data, children)
        return Node(data, children)
        
    def param_def(self, args):
        return (args[0].value, args[1])

    def _apply_params(self, params, node):
        if isinstance(node, Node):
            #print("_apply_params:", node)
            if node.T == "namespace_name":
                assert len(node.V) == 2
                if node.V[0] is None and "namespace" in params:
                    node.V[0] = params["namespace"]
                    #print("_apply_params: applied namespace:", params["namespace"])
            else:
                for n in node.C:
                    self._apply_params(params, n)        
        return node    
        
    def term_with_params(self, args):
        assert len(args) == 2
        params, term = args
        return self._apply_params(params, term)
        
    def with_clause(self, args):
        return dict(args)
        
    def parents_of(self, args):
        assert len(args) == 1
        return Node("parents_of", args)
        
    def children_of(self, args):
        assert len(args) == 1
        return Node("children_of", args)
        
    def add(self, args):
        assert len(args) == 2
        left, right = args
        if isinstance(left, Node) and left.T == "union":
            return left + [right]
        else:
            return Node("union", [left, right])

    def union(self, args):
        assert len(args) == 1
        args = args[0]
        if len(args) == 1:  return args[0]
        unions = []
        others = []
        for a in args:
            if isinstance(a, Node) and a.T == "union":
                unions += a[1:]
            else:
                others.append(a)
        return Node("union", unions + others)
        
    def mult(self, args):
        assert len(args) == 2
        left, right = args
        if isinstance(left, Node) and left.T == "join":
            return left + [right]
        else:
            return Node("join", [left, right])
            
    def join(self, args):
        assert len(args) == 1
        args = args[0]
        if len(args) == 1:  return args[0]
        joins = []
        others = []
        for a in args:
            if isinstance(a, Node) and a.T == "join":
                joins += a.C
            else:
                others.append(a)
        return Node("join", joins + others)
        
    def subtract(self, args):
        assert len(args) == 2
        left, right = args
        return Node("minus", [left, right])
        
    def namespace_name(self, args):
        assert len(args) in (1,2)
        if len(args) == 1:
            return Node("namespace_name", value=[None, args[0].value])      # no namespace
        else:
            return Node("namespace_name", value=[args[0].value, args[1].value])

    def dataset(self, args):
        assert len(args) in (1,2)
        if len(args) == 1:
            return Node("dataset", [args[0], None])       # dataset without meta_filter
        else:
            return Node("dataset", [args[0], args[1]])
        
    def filter(self, args):
        assert len(args) == 3
        return Node("filter", args[2], value = (args[0].value, args[1]))
        
    #def metafilter_exp(self, args):
    #    assert len(args) == 2
    #    return Node("meta_filter", args)
        
    def filter_params(self, args):
        #print("filter_params:", args)
        return args
        
    def cmp_op(self, args):
        return Node(args[1].value, [args[0].value, args[2]])
        
    def in_op(self, args):
        return Node("in", [args[1].value, args[0]])
        
    #def meta_not(self, args):
    #    assert len(args) == 1
    #    #print("meta_not: arg:", args[0])
    #    return Node("meta_not", [args[0]])
        
    def meta_and(self, args):
        if len(args) == 1:
            return args[0]
        children = []
        for a in args:
            if a.T == "meta_and":
                children += a.C
            else:
                children.append(a)
        return Node("meta_and", children)
        
    def meta_or(self, args):
        if len(args) == 1:
            return args[0]
        children = []
        for a in args:
            if a.T == "meta_or":
                children += a.C
            else:
                children.append(a)
        return Node("meta_or", children)

    def _apply_not(self, node):
        if node.T == "meta_and":
            return Node("meta_or", [self._apply_not(c) for c in node.C])
        elif node.T == "meta_or":
            return Node("meta_and", [self._apply_not(c) for c in node.C])
        elif node.T == "meta_not":
            return node.C[0]
        elif node.T in CMP_OPS:
            new_op = {
                ">":    "<=",
                "<":    ">=",
                ">=":    "<",
                "<=":    ">",
                "=":    "!=",
                "==":    "!=",
                "!=":    "=="
            }[node.T]
            return Node(new_op, node.C)
            
    def meta_not(self, children):
        assert len(children) == 1
        return self._apply_not(children[0])

class _Assembler(Ascender):

    def __init__(self, db, default_namespace):
        self.DB = db
        self.DefaultNamespace = default_namespace
        
    def walk(self, inp):
        #print("Assembler.walk(): in:", inp.pretty() if isinstance(inp, Node) else repr(inp))
        out = Ascender.walk(self, inp)
        #print("Assembler.walk(): out:", out.pretty() if isinstance(out, Node) else repr(out))
        return out
        
    def named_query(self, children, query_name):
        namespace, name = query_name
        namespace = namespace or self.DefaultNamespace
        Query.from_db(self.DB, namespace, name).parse()
        
class _Optimizer(Ascender):
    
    def parents_of(self, node):
        children = node.C
        assert len(children) == 1
        child = children[0]
        if isinstance(child, Node) and child.T in ("union", "join"):
            return Node(child.T, [Node("parents_of", cc) for cc in child.C])
        else:
            return node 

    parents_of.pass_node = True
            
    def children_of(self, node):
        children = node.C
        assert len(children) == 1
        child = children[0]
        if isinstance(child, Node) and child.T in ("union", "join"):
            # parents (union(x,y,z)) = union(parents(x), parents(y), parents(z))
            return Node(child.T, [Node("children_of", cc) for cc in child.C])
        else:
            return node

    children_of.pass_node = True

    def meta_filter(self, children, value):
        assert len(children) == 2
        query, meta_exp = children
        return self.apply_meta_exp(query, meta_exp)
        
    def apply_meta_exp(self, node, exp):
        # propagate meta filter expression as close to "dataset" as possible
        t = node.T
        if t in ("join", "union"):
            new_children = [self.apply_meta_exp(c, exp) for c in node.C]
            return Node(t, new_children)
        elif t == "minus":
            assert len(node.C) == 2
            left, right = node.C
            return Node(t, [self.apply_meta_exp(left, exp), right])
        elif t == "filter":
            return Node("meta_filter", [node, exp])
        elif t == "dataset":
            assert len(node.C) == 2
            ds, meta_exp = node.C
            if meta_exp is None:
                new_exp = exp 
            elif meta_exp.T == "and":
                new_exp = meta_exp + [exp]
            else:
                new_exp = Node("meta_and", [meta_exp, exp])
            return Node("dataset", [ds, new_exp])
        else:
            raise ValueError("Unknown node type in Optimizer.apply_meta_exp: %s" % (node,))
            
class _MetaExpressionDNF(object):
    
    def __init__(self, dataset_namespace, dataset_name, meta_exp):
        # root can be a meta expression in "almost" DNF:
        #   meta condition
        #   and(meta_condition,...)
        #.  or(and(meta_condition,...),...)
        print("_MetaExpressionDNF: input:", meta_exp.pretty())
        self.Expression = self.make_canonic(meta_exp)
        print("_MetaExpressionDNF: canonic:", self.Expression)
        self.DatasetNamespace = dataset_namespace
        self.DatasetName = dataset_name
        
    def __str__(self):
        return self.sql()
        
    __repr__= __str__
        
    def make_canonic(self, exp):
        if exp.T in CMP_OPS or exp.T == "in":
            return self.make_canonic(Node("meta_and", [exp]))
        elif exp.T == "meta_and":
            return self.make_canonic(Node("meta_or", [exp]))
        elif exp.T != "meta_or":
            raise ValueError("Unknown expression top node type %s" % (exp.T,))
        
        # make sure it is already in DNF
        for c in exp.C:
            if c.T != "meta_and":
                raise ValueError("The expression is not in DNF. Second level exp is of type %s: %s" % (c.T, exp.pretty()))
            for cc in c.C:
                if not cc.T in CMP_OPS and cc.T != "in":
                    raise ValueError("The expression is not in DNF. Third level exp is not a condition: %s %s" % (cc.T, exp.pretty()))
        
        return [
            and_p.C for and_p in exp.C
        ]

    def sql_and(self, and_term):
        print("sql_and: arg:", and_term)
        assert len(and_term) > 0
        parts = []
        for i, t in enumerate(and_term):
            op, (aname, aval) = t.T, t.C
            cname = None
            if op == "in":
                if isinstance(aval, int):       cname = "int_array"
                elif isinstance(aval, float):   cname = "float_array"
                elif isinstance(aval, bool):    cname = "bool_array"
                elif isinstance(aval, str):     cname = "string_array"
                else:
                        raise ValueError("Unrecognized value type %s for attribute %s" % (type(aval), aname))
                parts.append(f"a{i}.name='{aname}' and '{aval}' in a{i}.{cname}")
            else:
                if isinstance(aval, int):       cname = "int_value"
                elif isinstance(aval, float):   cname = "float_value"
                elif isinstance(aval, bool):    cname = "bool_value"
                elif isinstance(aval, str):     cname = "string_value"
                else:
                        raise ValueError("Unrecognized value type %s for attribute %s" % (type(aval), aname))
                parts.append(f"a{i}.name='{aname}' and a{i}.{cname} {op} '{aval}'")
        joins = [f"inner join file_attributes a{i} on a{i}.file_id = f.id" for i in range(len(parts))]
        return """
            select f.id as fid
                from files f
                    inner join files_datasets fd on fd.file_id = f.id
                    %s
                where 
                    fd.dataset_namespace = '%s' and fd.dataset_name = '%s' and
                    %s
                """ % (
                " ".join(joins), self.DatasetNamespace, self.DatasetName, " and ".join(parts))
                
    def sql_or(self, parts):
        ands = [self.sql_and(p) for p in parts]
        return """
            select files.id, files.namespace, files.name, 
                        a.name,
                        a.int_array, a.float_array, a.string_array, a.bool_array,
                        a.int_value, a.float_value, a.string_value, a.bool_value
                from files left outer join file_attributes a on (a.file_id = files.id)
                where files.id in (select distinct fid from (%s) as ands)
        """ % (" union ".join(ands))
        
    def sql(self):
        return self.sql_or(self.Expression)

class _MetaExpOptmizer(Ascender):
    
    def _flatten_bool(self, op, nodes):
        #print("_flatten_bool: input:", nodes)
        new_nodes = []
        for c in nodes:
            if c.T == op:
                new_nodes += self._flatten_bool(op, c.C)
            else:
                new_nodes.append(c)
        #print("_flatten_bool: output:", new_nodes)
        return new_nodes
        
    def meta_or(self, children, value):
        children = [x if x.T == "meta_and" else Node("meta_and", [x]) for x in self._flatten_bool("meta_or", children)]
        out = Node("meta_or", children)
        return out
    
    def _generate_and_terms(self, path, rest):
        if len(rest) == 0:  yield path
        else:
            node = rest[0]
            rest = rest[1:]
            if node.T == "meta_or":
                for c in node.C:
                    my_path = path + [c]
                    for p in self._generate_and_terms(my_path, rest):
                        yield p
            else:
                for p in self._generate_and_terms(path + [node], rest):
                    yield p

    def meta_and(self, children, value):
        children = self._flatten_bool("meta_and", children)
        or_present = False
        for c in children:
            if c.T == "meta_or":
                or_present = True
                break
        
        if or_present:
            paths = list(self._generate_and_terms([], children))
            print("paths:")
            for p in paths:
                print(p)
            paths = [self._flatten_bool("meta_and", p) for p in paths]
            print("meta_and: children:", paths)
            return Node("meta_or", [Node("meta_and", p) for p in paths])
        else:
            return Node("meta_and", children)
            
    def dataset(self, children, value):
        assert len(children) == 2
        ds, exp = children
        ds_namespace, ds_name = ds.V
        return Node("dataset", [ds, None if exp is None else _MetaExpressionDNF(ds_namespace, ds_name, exp)])
            
class _Evaluator(Ascender):

    def __init__(self, db, filters):
        self.Filters = filters
        self.DB = db

    def parents_of(self, args, value):
        assert len(args) == 1
        arg = args[0]
        if False and arg.T == "dataset":      # not implemented yet
            return self.dataset(arg.C, arg.V, "parents")
        else:
            return arg.parents(with_metadata=True)

    def children_of(self, args, value):
        assert len(args) == 1
        arg = args[0]
        #print("_Evaluator.children_of: arg:", arg)
        if False and arg.T == "dataset":      # not implemented yet
            return self.dataset(arg.C, arg.V, "children")
        else:
            #print("children_of: calling children()...")
            return arg.children(with_metadata=True)

    def dataset(self, args, value, provenance=None):
        assert len(args) == 2
        dataset_name, meta_exp = args
        namespace, name = dataset_name.V
        dataset = DBDataset.get(self.DB, namespace, name)
        condition = None if meta_exp is None else self.meta_exp_to_sql(meta_exp)
        files = dataset.list_files(condition=condition, 
            relationship="self" if provenance is None else provenance, 
            with_metadata=True)
        #print ("Evaluator.dataset: files:", files)
        assert isinstance(files, DBFileSet)
        return files
        
    def union(self, args, value):
        return DBFileSet.union(self.DB, args)
        
    def join(self, args, value):
        return DBFileSet.join(self.DB, args)
        
    def minus(self, expressions, value):
        assert len(expressions) == 2
        left, right = expressions
        return left - right

    def filter(self, args, value):
        name, params = value
        inputs = args
        #print("Evaluator.filter: inputs:", inputs)
        filter_function = self.Filters[name]
        return DBFileSet(self.DB, filter_function(inputs, params))
        
    def meta_filter(self, args, value):
        assert len(args) == 2
        files, meta_exp = args
        return DBFileSet(self.DB, (f for f in files if self.evaluate_meta_expression(f, meta_exp)))
        
    def _eval_meta_bool(self, f, bool_op, parts):
        assert len(parts) > 0
        p0 = parts[0]
        rest = parts[1:]
        ok = self.evaluate_meta_expression(f, p0)
        if bool_op == "and":
            if len(rest) and ok:
                ok = self._eval_meta_bool(f, bool_op, rest)
            return ok
        elif bool_op == "or":
            if len(rest) and not ok:
                ok = self._eval_meta_bool(f, bool_op, rest)
            return ok
        elif bool_op == "not":
            assert len(rest) == 0
            return not ok
        else:
            raise ValueError("Unrecognized boolean operation '%s'" % (op,))
            
    BOOL_OPS = ("and", "or", "not")

    def evaluate_meta_expression(self, f, meta_expression):
        op, args = meta_expression.T, meta_expression.C
        if op in self.BOOL_OPS:
            return self._eval_meta_bool(f, op, args)
        else:
            # 
            name, value = args
            attr_value = f.get_attribute(name, None)
            if op == "<":          return attr_value < value
            elif op == ">":        return attr_value > value
            elif op == "<=":       return attr_value <= value
            elif op == ">=":       return attr_value >= value
            elif op in ("==",'='): 
                #print("evaluate_meta_expression:", repr(attr_value), repr(value))
                return attr_value == value
            elif op == "!=":       return attr_value != value
            elif op == "in":       return value in attr_value       # exception, e.g.   123 in event_list
            else:
                raise ValueError("Invalid comparison operator '%s' in %s" % (op, meta_expression))

    def meta_exp_to_sql(self, meta_expression):
        op, args = meta_expression.T, meta_expression.C
        if op in self.BOOL_OPS:
            bool_op = op
            exps = args
        else:
            bool_op = "and"
            
        if op in self.BOOL_OPS:
            if op in ('or','and'):
                sql_op = op
                return (' ' + sql_op + ' ').join([
                    '(' + self.meta_exp_to_sql(part) + ')' for part in args])
            elif op == 'not':
                return ' not (' + self.meta_exp_to_sql(args[1]) + ')'
            else:
                raise ValueError("Unrecognized boolean operation '%s'" % (op,))
        else:
            name, value = args
            if op in ('<', '>', '<=', '>=', '==', '=', '!='):
                sql_op = '=' if op == '==' else op
                if isinstance(value, bool): colname = "bool_value"
                elif isinstance(value, int): colname = "int_value"
                elif isinstance(value, float): colname = "float_value"
                elif isinstance(value, str): colname = "string_value"
                else:
                        raise ValueError("Unrecognized value type %s for attribute %s" % (type(value), name))
                return "attr.name='%s' and attr.%s %s '%s'" % (name, colname, sql_op, value)
            elif op == 'in':
                value, _, name = meta_expression
                if isinstance(value, bool): colname = "bool_array"
                elif isinstance(value, int): colname = "int_array"
                elif isinstance(value, float): colname = "float_array"
                elif isinstance(value, str): colname = "string_array"
                else:
                        raise ValueError("Unrecognized value type %s for attribute %s" % (type(value), name))
                return "attr.name='%s' and '%s' in attr.%s" % (name, value, colname)
            else:
                raise ValueError("Invalid comparison operator '%s' in %s" % (op, meta_expression))
        

class Query(object):

    _Parser = Lark(grammar, start="exp")

    def __init__(self, source, default_namespace=None):
        self.Source = source
        self.DefaultNamespace = default_namespace
        self.Parsed = self.Optimized = self.Assembled = None
        
    def remove_comments(self, text):
        out = []
        for l in text.split("\n"):
            l = l.split('#', 1)[0]
            out.append(l)
        return '\n'.join(out)
        
    def parse(self):
        if self.Parsed is None:
            tree = self._Parser.parse(self.remove_comments(self.Source))
            self.Parsed = _Converter().convert(tree, self.DefaultNamespace)
        return self.Parsed
        
    def assemble(self, db, default_namespace = None):
        if self.Assembled is None:
            parsed = self.parse()
            #print("Query.assemble(): parsed:", parsed.pretty())
            self.Assembled = _Assembler(db, default_namespace).walk(parsed)
            #print("Query.assemble: self.Assembled:", self.Assembled.pretty())
        return self.Assembled
        
    def skip_assembly(self):
        if self.Assembled is None:
            self.Assembled = self.parse()
        return self.Assembled
        
    def optimize(self):
        #print("Query.optimize: entry")
        assert self.Assembled is not None
        #print("optimize: assembled:", self.Assembled.pretty())
        meta_optimized = _MetaExpOptmizer().walk(self.Assembled)
        self.Optimized = _Optimizer().walk(meta_optimized)
        #print("Query.optimize: optimized:", self.Optimized)
        return self.Optimized

    def run(self, db, filters={}):
        self.assemble(db, self.DefaultNamespace)
        #print("Query.run: assemled:", self.Assembled.pretty())
        return _Evaluator(db, filters).walk(self.optimize())
        
    @property
    def code(self):
        return self.parse().to_json()
        
    @staticmethod
    def from_db(db, namespace, name):
        return Query(DBNamedQuery.get(db, namespace, name).Source)

    def to_db(self, db, namespace, name):
        return DBNamedQuery(db, namespace, name, self.Source).save()

if __name__ == "__main__":
    import sys
    tree = Query.Parser.parse(open(sys.argv[1], "r").read())
    converted = _Converter().transform(tree)
    pprint.pprint(converted)

        
