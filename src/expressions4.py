from dbobjects import DBDataset, DBFile
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

term2   : term                                  -> f_
        | term "where" meta_exp                 -> metafilter_exp

?term: union                                    -> f_
    | join                                      -> f_
    | filter_exp                                -> f_
    | dataset_exp                               -> f_
    | "(" exp ")"                               -> f_
    
union: "union" "(" exp_list ")"
    | "[" exp_list "]"

join: "join" "(" exp_list ")"
    | "{" exp_list "}"

exp_list: exp ("," exp)*                             

filter_exp:  "filter" CNAME "(" filter_params ")" "(" filter_inputs ")"         -> filter

filter_inputs: exp ("," exp)*                             

filter_params:    ( constant ("," constant)* )?                    -> filter_params

dataset_exp: "dataset" dataset_name ("where" meta_exp)?           -> dataset

dataset_name: (CNAME ":")? CNAME

?meta_exp:   and_meta                                
    | meta_exp "or" and_meta                        -> meta_or
    
?and_meta:   term_meta                               
    | and_meta "and" term_meta                      -> meta_and
    
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

class Ascender(object):

    def walk(self, node):
        if not isinstance(node, Node):
            return node
        node_type, children = node.T, node.C
        #print("Ascender.walk:", node_type, children)
        assert isinstance(node_type, str)
        children = [self.walk(c) for c in children]
        method = getattr(self, node_type) if hasattr(self, node_type) else None
        return method(children, node.V) if method is not None else self.__default(node)
        
    def __default(self, node):
        return node

class Descender(object):

    def visit(self, node):
        node_type, children = node.T, node.C
        assert isinstance(node, str)
        method = getattr(self, node_type) if hasattr(self, node_type) else None
        return method(children, node.V) if method is not None else self.__default(node)
        
    def visit_children(self, node):
        if isinstance(node, Node):
            return [self.visit(c) for c in nodeC]
        
    def __default(self, node):
        return self.visit_children(node)

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
        
    def exp_list(self, args):
        return args

    def filter_inputs(self, args):
        return Node("filter_inputs", args)

    def param_def(self, args):
        return (args[0].value, args[1])

    def _apply_params(self, params, node):
        if isinstance(node, Node):
            #print("_apply_params:", node)
            if node.T == "dataset_name":
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
        
    def add(self, args):
        assert len(args) == 2
        left, right = args
        if isinstance(left, Node) and left.T == "union":
            return left + [right]
        else:
            return Node("union", [left, right])

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
        
    def mult(self, args):
        assert len(args) == 2
        left, right = args
        if isinstance(left, Node) and left.T == "join":
            return left + [right]
        else:
            return Node("join", [left, right])
            
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
        
    def dataset_name(self, args):
        assert len(args) in (1,2)
        if len(args) == 1:
            return Node("dataset_name", value=[None, args[0].value])      # no namespace
        else:
            return Node("dataset_name", value=[args[0].value, args[1].value])

    def dataset(self, args):
        assert len(args) in (1,2)
        if len(args) == 1:
            return Node("dataset", [args[0], None])       # dataset without meta_filter
        else:
            return Node("dataset", [args[0], args[1]])
        
    def filter(self, args):
        assert len(args) == 3
        return Node("filter", [args[0].value, args[1], args[2]])
        
    def metafilter_exp(self, args):
        assert len(args) == 2
        return Node("meta_filter", args)
        
    def filter_params(self, args):
        #print("filter_params:", args)
        return args
        
    def cmp_op(self, args):
        return Node(args[1].value, [args[0].value, args[2]])
        
    def in_op(self, args):
        return Node("in", [args[1].value, args[0]])
        
    def meta_not(self, args):
        assert len(args) == 1
        #print("meta_not: arg:", args[0])
        return Node("not", [args[0]])
        
    def meta_and(self, args):
        assert len(args) == 2
        left, right = args
        #print("meta_and:", left, right)
        if isinstance(left, Node) and left.T == "meta_and":
            return left + [right]
        else:
            return Node("meta_and", [left, right])
        
    def meta_or(self, args):
        assert len(args) == 2
        left, right = args
        if isinstance(left, Node) and left.T == "meta_or":
            return left + [right]
        else:
            return Node("meta_or", [left, right])
            
class _Evaluator(Ascender):

    def __init__(self, db, filters, default_namespace):
        self.Filters = filters
        self.DB = db
        self.DefaultNamespace = default_namespace
        
    def dataset(self, args, value):
        assert len(args) == 2
        dataset_name, meta_exp = args
        namespace, name = dataset_name.V
        dataset = DBDataset.get(self.DB, namespace, name)
        condition = None if meta_exp is None else self.meta_exp_to_sql(meta_exp)
        files = dataset.list_files(condition=condition, with_metadata=True)
        #print ("Evaluator.dataset: files:", files)
        return files
        
    def union(self, args, value):
        expressions = args
        if len(expressions) == 1:
            return expressions[0]
        def union_generator(file_lists):
            first = file_lists[0]
            if len(file_lists) == 1:
                return first
            file_ids = set()
            for lst in file_lists:
                for f in lst:
                    if not f.FID in file_ids:
                        file_ids.add(f.FID)
                        yield f
        return union_generator(expressions)
        
    def join(self, args, value):
        expressions = args
        first = expressions[0]
        if len(expressions) == 1:
            return first
        file_list = list(first)
        file_ids = set(f.FID for f in file_list)
        for another in expressions[1:]:
            another_ids = set(f.FID for f in another)
            file_ids &= another_ids
        return (f for f in file_list if f.FID in file_ids)
        
    def minus(self, expressions, value):
        assert len(expressions) == 2
        left, right = expressions
        #print("minus: left:", left)
        left_files = list(left)
        left_ids = set(f.FID for f in left_files)
        right_ids = set(f.FID for f in right)
        result_ids = left_ids - right_ids
        return (f for f in left_files if f.FID in result_ids)

    def filter_inputs(self, args, value):
        return args		# list of iterables

    def filter(self, args, value):
        assert len(args) == 3
        name, params, inputs = args
        #print("Evaluator.filter: inputs:", inputs)
        filter_function = self.Filters[name]
        return filter_function(inputs, params)
        
    def meta_filter(self, args, value):
        assert len(args) == 2
        files, meta_exp = args
        return (f for f in files if self.evaluate_meta_expression(f, meta_exp))

    BOOL_OPS = ("and", "or", "not")
        
    def evaluate_meta_expression(self, f, meta_expression):
        op, args = meta_expression.T, meta_expression.C
        if op in self.BOOL_OPS:
            if op == 'and':
                ok = self.evaluate_meta_expression(f, args[0])
                if ok and args[1:]:
                    ok = self.evaluate_meta_expression(f, ["and"] + args[1:])
                return ok
            elif op == 'or':
                ok = self.evaluate_meta_expression(f, args[0])
                if not ok and args[1:]:
                    ok = self.evaluate_meta_expression(f, ["or"] + args[1:])
                return ok
            elif op == 'not':
                return not self.evaluate_meta_expression(f, args[0])
            else:
                raise ValueError("Unrecognized boolean operation '%s'" % (op,))
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
            args = meta_expression[1:]
            if op in ('or','and'):
                return (' ' + op + ' ').join([
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

    Parser = Lark(grammar, start="exp")

    def __init__(self, db, exp_text, default_namespace = None):
        self.Text = exp_text
        self.Parsed = Query.parse(self.Text)
        self.Converted = _Converter().convert(self.Parsed, default_namespace)
        self.DB = db
        self.DefaultNamespace = default_namespace
        
    @staticmethod
    def remove_comments(text):
        out = []
        for l in text.split("\n"):
            l = l.split('#', 1)[0]
            out.append(l)
        return '\n'.join(out)
    
    @staticmethod
    def parse(text):
        return Query.Parser.parse(Query.remove_comments(text))
        
    def run(self, filters={}):
        out = _Evaluator(self.DB, filters, self.DefaultNamespace).walk(self.Converted)
        return out
        
        
if __name__ == "__main__":
    import sys
    tree = Query.Parser.parse(open(sys.argv[1], "r").read())
    converted = _Converter().transform(tree)
    pprint.pprint(converted)

        
