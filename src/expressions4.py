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

filter_exp:  "filter" CNAME "(" filter_params ")" "(" exp_list ")"         -> filter

exp_list: exp ("," exp)*                             

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

class Ascender(object):

    def walk(self, node):
        node_type, children = node[0], node[1:]
        assert isinstance(node_type, str)
        children = [self.walk(c) for c in children]
        method = getattr(self, node_type) if hasattr(self, node_type) else None
        return method(children) if method is not None else self.__default(node_type, children)
        
    def __default(self, node_type, children):
        return [node_type] + children

class Descender(object):

    def visit(self, node):
        node_type = node[0]
        assert isinstance(node, str)
        children = node[1:]
        method = getattr(self, node_type) if hasattr(self, node_type) else None
        return method(node_type, children) if method is not None else self.__default(node, children)
        
    def visit_children(self, node):
        return [self.visit(c) for c in node[1:]]
        
    def __default(self, node, children):
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

    def param_def(self, args):
        return [args[0].value, args[1]]

    def _apply_params(self, params, node):
        if isinstance(node, (list, tuple)):
            #print("_apply_params:", node)
            if node[0] == "dataset":
                dataset_name_list = node[1]
                if dataset_name_list[0] is None and "namespace" in params:
                    dataset_name_list[0] = params["namespace"]
                    #print("_apply_params: applied namespace:", params["namespace"])
            else:
                for n in node[1:]:
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
        if isinstance(left, list) and len(left) and left[0] == "union":
            return left + [right]
        else:
            return ["union", left, right]

    def join(self, args):
        assert len(args) == 1
        args = args[0]
        if len(args) == 1:  return args[0]
        joins = []
        others = []
        for a in args:
            if isinstance(a, list) and len(a) and a[0] == "join":
                joins += a[1:]
            else:
                others.append(a)
        return ["join"] + joins + others
        
    def subtract(self, args):
        assert len(args) == 2
        left, right = args
        return ["minus", left, right]
        
    def mult(self, args):
        assert len(args) == 2
        left, right = args
        if isinstance(left, list) and len(left) and left[0] == "join":
            return left + [right]
        else:
            return ["join", left, right]
            
    def union(self, args):
        assert len(args) == 1
        args = args[0]
        if len(args) == 1:  return args[0]
        unions = []
        others = []
        for a in args:
            if isinstance(a, list) and len(a) and a[0] == "union":
                unions += a[1:]
            else:
                others.append(a)
        return ["union"] + joins + others
        
    def dataset_name(self, args):
        assert len(args) in (1,2)
        if len(args) == 1:
            return [None, args[0].value]      # no namespace
        else:
            return [args[0].value, args[1].value]

    def dataset(self, args):
        assert len(args) in (1,2)
        if len(args) == 1:
            return ["dataset", args[0], None]       # dataset without meta_filter
        else:
            return ["dataset", args[0], args[1]]
        
    def filter(self, args):
        assert len(args) == 3
        return ["filter", args[0].value, args[1:]]
        
    def metafilter_exp(self, args):
        assert len(args) == 2
        return ["meta_filter"] + args
        
    def filter_params(self, args):
        #print("filter_params:", args)
        return args
        
    def cmp_op(self, args):
        return [args[1].value, args[0].value, args[2]]
        
    def in_op(self, args):
        return ["in", args[1].value, args[0]]
        
    def meta_not(self, args):
        assert len(args) == 1
        #print("meta_not: arg:", args[0])
        return ["not", args[0]]
        
    def meta_and(self, args):
        assert len(args) == 2
        left, right = args
        #print("meta_and:", left, right)
        if isinstance(left, list) and len(left) > 0 and left[0] == "meta_and":
            return left + [right]
        else:
            return ["meta_and", left, right]
        
    def meta_or(self, args):
        assert len(args) == 2
        left, right = args
        if isinstance(left, list) and len(left) > 0 and left[0] == "meta_or":
            return left + [right]
        else:
            return ["meta_or", left, right]
            
class _Evaluator(Ascender):

    def __init__(self, db, filters, default_namespace):
        self.Filters = filters
        self.DB = db
        self.DefaultNamespace = default_namespace
        
    def dataset(self, args):
        assert len(args) == 2
        (namespace, name), meta_exp = args
        dataset = DBDataset.get(self.DB, namespace, name)
        condition = None if meta_exp is None else self.meta_exp_to_sql(meta_exp)
        files = dataset.list_files(condition=condition, with_metadata=True)
        return files
        
    def union(self, args):
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
        
    def join(self, args):
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
        
    def minus(self, expressions):
        assert len(expressions) == 2
        left, right = expressions
        #print("minus: left:", left)
        left_files = list(left)
        left_ids = set(f.FID for f in left_files)
        right_ids = set(f.FID for f in right)
        result_ids = left_ids - right_ids
        return (f for f in left_files if f.FID in result_ids)

    def filter(self, args):
        assert len(args) == 3
        name, params, inputs = args
        #print("params:", params)
        name = name.value
        filter_function = self.Filters[name]
        return filter_function(inputs, params)
        
    def meta_filter(self, args):
        assert len(args) == 2
        files, meta_exp = args
        return (f for f in files if self.evaluate_meta_expression(f, meta_exp))
        
    def evaluate_meta_expression(self, f, meta_expression):
        op = meta_expression[0]
        if op in self.BOOL_OPS:
            args = meta_expression[1:]
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
            op, name, value = meta_expression
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
        op = meta_expression[0]
        if op in Expression.BOOL_OPS:
            args = meta_expression[1:]
            if op in ('or','and'):
                return (' ' + op + ' ').join([
                    '(' + self.meta_exp_to_sql(part) + ')' for part in args])
            elif op == 'not':
                return ' not (' + self.meta_exp_to_sql(args[1]) + ')'
            else:
                raise ValueError("Unrecognized boolean operation '%s'" % (op,))
        else:
            op, name, value = meta_expression
            if op in ('<', '>', '<=', '>=', '==', '=', '!='):
                sql_op = '=' if op == '==' else op
                if isinstance(value, bool): colname = "bool_value"
                elif isinstance(value, int): colname = "int_value"
                elif isinstance(value, float): colname = "float_value"
                elif isinstance(value, str): colname = "string_value"
                else:
                        raise ValueError("Unrecognized value type %s for attribute %s" % (type(value), name))
                return "attr.name='%s' and attr.%s %s '%s'" % (name, colname, op, value)
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
        
