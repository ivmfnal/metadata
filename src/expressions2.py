from dbobjects import DBDataset, DBFile
import json

from lark import Lark
from lark import Transformer
import pprint

grammar = """
exp:    exp1                                    -> forward
    | exp "-" exp1                              -> minus

?exp1: "[" exp_list "]"                         -> union
    | "{" exp_list "}"                          -> intersect
    | filter_exp                                -> forward
    | select_exp                                -> forward
    | dataset_exp                               -> forward

filter_exp:  "filter" CNAME "(" filter_params ")" "(" exp_list ")"         -> filter

exp_list: exp ("," exp)*                             

filter_params:    ( constant ("," constant)* )?                    -> filter_params

?select_exp: exp "where" meta_exp                                  -> meta_filter

?dataset_exp: "dataset" dataset_name ("where" meta_exp)?                    -> dataset

dataset_name: (CNAME ":")? CNAME

?meta_exp:   and_meta                                //-> forward
    | meta_exp "or" and_meta                        -> meta_or
    
?and_meta:   term_meta                               //-> forward
    | and_meta "and" term_meta                      -> meta_and
    
term_meta:  CNAME CMPOP constant                    -> cmp_op
    | constant "in" CNAME                           -> in_op
    | "(" meta_exp ")"                              -> forward
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


class _Evaluator(Transformer):

    def __init__(self, db, filters, default_namespace):
        Transformer.__init__(self)
        self.Filters = filters
        self.DB = db
        self.DefaultNamespace = default_namespace
        
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
        
    def union(self, args):
        expressions = args[0]
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

    def intersect(self, args):
        expressions = args[0]
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

    def dataset_name(self, args):
        assert len(args) in (1,2)
        if len(args) == 1:
            if self.DefaultNamespace is None:
                raise ValueError("Default namespace is not defined")
            out = [self.DefaultNamespace, args[0].value]
        else:
            out = [args[0].value, args[1].value]
        return out
        
    def dataset(self, args):
        assert len(args) in (1,2)
        namespace, name = args[0]
        dataset = DBDataset.get(self.DB, namespace, name)

        meta_expression = None if len(args) < 2 else args[1]
        condition = None if not meta_expression else self.meta_exp_to_sql(meta_expression)
        
        files = dataset.list_files(condition=condition, with_metadata=True)
        return files
        
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
        
    def filter_params(self, args):
        #print("filter_params:", args)
        return args
        
    def cmp_op(self, args):
        return [args[0].value, args[1], args[2]]
        
    def forward(self, args):
        assert len(args) == 1
        return args[0]
        
    def meta_not(self, args):
        assert len(args) == 1
        return ["not", args[0]]
        
    def meta_and(self, args):
        assert len(args) == 2
        left, right = args
        #print("meta_and:", left, right)
        if isinstance(left, list) and len(left) > 0 and left[0] == "and":
            return left + [right]
        else:
            return ["and", left, right]
        
    def meta_or(self, args):
        assert len(args) == 2
        left, right = args
        if isinstance(left, list) and len(left) > 0 and left[0] == "or":
            return left + [right]
        else:
            return ["or", left, right]

    BOOL_OPS = ("and", "or", "not")

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
                return not self.evaluate_meta_expression(f, args[1])
            else:
                raise ValueError("Unrecognized boolean operation '%s'" % (op,))
        else:
            # <attr> <cmp> <value>
            name, op, value = meta_expression
            attr_value = f.get_attribute(name, None)
            if op == "<":          return attr_value < value
            elif op == ">":        return attr_value > value
            elif op == "<=":       return attr_value <= value
            elif op == ">=":       return attr_value >= value
            elif op in ("==",'='): 
                print("evaluate_meta_expression:", repr(attr_value), repr(value))
                return attr_value == value
            elif op == "!=":       return attr_value != value
            elif op == "in":       return value in attr_value       # exception, e.g.   123 in event_list
            else:
                raise ValueError("Invalid comparison operator '%s' in %s" % (op, meta_expression))

    @staticmethod                
    def meta_exp_to_sql(meta_expression):
        op = meta_expression[0]
        if op in Expression.BOOL_OPS:
            args = meta_expression[1:]
            if op in ('or','and'):
                return (' ' + op + ' ').join([
                    '(' + Expression.meta_exp_to_sql(part) + ')' for part in args])
            elif op == 'not':
                return ' not (' + self.meta_exp_to_sql(args[1]) + ')'
            else:
                raise ValueError("Unrecognized boolean operation '%s'" % (op,))
        else:
            # <attr> <cmp> <value>
            name, op, value = meta_expression
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
        self.Parsed = self.Parser.parse(self.Text)
        self.DB = db
        self.DefaultNamespace = default_namespace
        
    def run(self, filters={}):
        t = _Evaluator(self.DB, filters, self.DefaultNamespace)
        return t.transform(self.Parsed)
        
        
        
        
