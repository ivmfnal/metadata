from dbobjects import DBDataset, DBFile, DBNamedQuery, DBFileSet
import json, time

from lark import Lark
from lark import Transformer, Tree, Token
from lark.visitors import Interpreter
import pprint

CMP_OPS = [">" , "<" , ">=" , "<=" , "==" , "=" , "!="]

MQL_Grammar = """
?query:  ("with" param_def_list)? "files"? qualifiable_query

?qualifiable_query:  metafilterable_query "where" meta_exp       -> meta_filter
    | metafilterable_query                         
    
?metafilterable_query:  "union" "(" query_list ")"  -> union
    |   "[" query_list "]"                          -> union
    |   "join"  "(" query_list ")"                  -> join
    |   "{" query_list "}"                          -> join
    |   "parents" "(" query ")"                     -> parents_of
    |   "children" "(" query ")"                    -> children_of
    |   query "-" query                             -> subtract
    |   "(" query ")"                               -> s_
    |   "filter" qualified_name "(" constant_list? ")" "(" query_list ")"       -> filter
    |   "query" qualified_name                      -> named_query
    |   data_source
    
query_list: query ("," query)*                     
    
!data_source: source_spec_list ("with" "children" "recursively"?)? ("having" meta_exp)?

source_spec_list: "from"  source_spec ("," source_spec)* 

source_spec:    qualified_name
    | dataset_pattern

dataset_pattern:    "matching" STRING (":" STRING)?

qualified_name: (FNAME ":")? FNAME

param_def_list :  param_def ("," param_def)*

param_def: CNAME "=" constant

?meta_exp:   meta_or                                                           

meta_or:    meta_and ( "or" meta_and )*

meta_and:   term_meta ( "and" term_meta )*

term_meta:  ANAME CMPOP constant                    -> cmp_op
    | constant "in" ANAME                           -> in_op
    | "(" meta_exp ")"                              -> s_
    | "!" term_meta                                 -> meta_not
    
constant_list:    constant ("," constant)*                    

constant : SIGNED_FLOAT                             -> float_constant                      
    | STRING                                        -> string_constant
    | SIGNED_INT                                    -> int_constant
    | BOOL                                          -> bool_constant

ANAME: WORD ("." WORD)*

FNAME: LETTER ("_"|"-"|"."|LETTER|DIGIT)*

WORD: LETTER ("_"|LETTER|DIGIT)*

CMPOP: ">" | "<" | ">=" | "<=" | "==" | "=" | "!=" | "~" | "!~" 

BOOL: "true"i | "false"i                         

%import common.CNAME
%import common.SIGNED_INT
%import common.SIGNED_FLOAT
%import common.ESCAPED_STRING       -> STRING
%import common.WS
%import common.LETTER
%import common.DIGIT
%ignore WS
"""



class Node(object):

    JSON_CLASS = "node"

    def __init__(self, typ, children=[], meta=None):
        self.T = typ
        self.M = meta
        self.C = children[:]

    def __str__(self):
        return "[Node %s (%d) m:%s]" % (self.T, len(self.C), self.M or "")
        
    __repr__ = __str__
        
    def line(self):
        return "%s %s" % (self.T, self.M or "")

    def __add__(self, lst):
        return Node(self.T, self.C + lst, self.M)
        
    def __iadd__(self, addition):
        if isinstance(addition, Node):
            self.C.append(addition)
        elif isinstance(addition, list):
            self.C += addition
        else:
            raise ValueError("Unknown type: %s %s, expected either a Node or a list of Nodes" % (type(addition), addition))
        return self

    def as_list(self):
        out = [self.T, self.M]
        for c in self.C:
                if isinstance(c, Node):
                        out.append(c.as_list())
                else:
                        out.append(c)
        return out
        
    def _pretty(self, indent=""):
        out = []
        out.append("%s%s" % (indent, self.line()))
        for c in self.C:
            if isinstance(c, Node):
                out += c._pretty(indent+"    ")
            else:
                out.append("%s%s" % (indent + "    ", repr(c)))
        return out
        
    def pretty(self):
        return "\n".join(self._pretty())
        
    def jsonable(self):
        d = dict(T=self.T, M=self.M, C=[c.jsonable() if isinstance(c, Node) else c
                        for c in self.C]
        )
        return d
        
    def to_json(self):
        d = self.jsonable()
        d["///class///"] = self.JSON_CLASS
        return json.dumps(d)

    @staticmethod
    def from_jsonable(data):
        if isinstance(data, dict) and data.get("///class///") == "node":
            typ = data["T"]
            if typ == "DataSource":
                return DataSource.from_jsonable(data)
            elif typ == "MetaExp":
                return MetaExp.from_jsonable(data)
            else:
                return Node(data["T"],
                    children = [Node.from_jsonable(c) for c in data.get("C", [])],
                    meta = data.get("M")
            )
        else:
            return data

    @staticmethod
    def from_json(text):
        return Node.from_jsonable(json.loads(text))

def pass_node(method):
    def decorated(self, *params, **args):
        return method(self, *params, **args)
    decorated.__pass_node__ = True
    return decorated

class Visitor(object):

    def walk(self, node, context=None):
        if not isinstance(node, Node):
            return
        node_type, children = node.T, node.C
        
        if hasattr(self, node_type):
            method = getattr(self, node_type)
            visit_children = method(node, context)
        else:
            visit_children = self.__default(node, context)

        if visit_children:
            for c in children:
                self.walk(c, context)
        return node
        
    def __default(self, node, context):
        return True
        
class Descender(object):

    # descends objects top to bottom, possibly replacing them

    def walk(self, node, context):
        #print("Descender", self.__class__.__name__, ".walk: node:", node.pretty())

        if not isinstance(node, Node):
            return node

        node_type, children = node.T, node.C
        
        if hasattr(self, node_type):
            method = getattr(self, node_type)
            #print("Descender", self.__class__.__name__, ".walk: method:", method)
            #if node.T == "DataSource":
            #    print("Descender:", self.__class__.__name__, "   input:", node.pretty())
            new_node = method(node, context)
            #if new_node.T == "DataSource":
            #    print("Descender:", self.__class__.__name__, "   new_node:", new_node.pretty())
                
        else:
            new_node = self.__default(node, context)
            
            
        #print("Descender.walk: new_node:", new_node.pretty())
        return new_node

    def __default(self, node, context):
        node.C = [self.walk(c, context) for c in node.C]
        return node
        
class Ascender(object):

    def __init__(self):
        self.Indent = ""

    def walk(self, node):
        #print("Ascender %s: walk: in: %s" % (self.__class__.__name__, node))
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
            if hasattr(method, "__pass_node__") and getattr(method, "__pass_node__"):
                out = method(node)
            else:
                out = method(children, node.M)
        else:
            out = self.__default(node, children)
        #print("Ascender %s: walk: out: %s" % (self.__class__.__name__, out))
        return out
        
    def __default(self, node, children):
        return node
        return Node(node.T, children=children, meta=node.M)
        
class DataSource(Node):

    def __init__(self, patterns, with_children, recursively, having):
        Node.__init__(self, "DataSource")
        self.Patterns = patterns
        self.WithChildren = with_children
        self.Recursively = recursively
        self.Having = having
        self.Wheres = None      # and-list
        self.WheresDNF = None

    def line(self):
        return "DataSource %s with_children=%s rec=%s having=%s" % (self.Patterns, self.WithChildren,
                self.Recursively, self.Having)
                
    def _pretty(self, indent=""):
        out = []
        out.append("%s%s" % (indent, self.line()))
        if self.Wheres is not None:
            out.append("%s  where:" % (indent,))
            out += self.Wheres._pretty(indent+"    ")
        return out

    def setHaving(self, having):
        self.Having = having
    
    def addWhere(self, where):
        assert isinstance(where, Node) and where.T == "meta_or"
        if self.Wheres is None:
            self.Wheres = where
        else:
            self.Wheres = self.Wheres & where
        
    def wheres_dnf(self):
        return self.WheresDNF
        
    def file_list(self, with_metadata):
        return DBFileList.from_data_source(self, with_metadata)   
        


class _MetaRegularizer(Ascender):
    # converts the meta expression into DNF form:
    #
    #   Node(or, [Node(and, [exp, ...])])
    #

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

    def meta_or(self, children, meta):
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

    def meta_and(self, children, meta):
        children = self._flatten_bool("meta_and", children)
        or_present = False
        for c in children:
            if c.T == "meta_or":
                or_present = True
                break

        if or_present:
            paths = list(self._generate_and_terms([], children))
            #print("paths:")
            #for p in paths:
            #    print(p)
            paths = [self._flatten_bool("meta_and", p) for p in paths]
            #print("meta_and: children:", paths)
            return Node("meta_or", [Node("meta_and", p) for p in paths])
        else:
            return Node("meta_and", children)
                
    
    @staticmethod
    def _make_DNF_lists(exp):
        if exp is None: return None
        if exp.T in CMP_OPS or exp.T == "in":
            return self._make_DNF(Node("meta_and", [exp]))
        elif exp.T == "meta_and":
            return self._make_DNF(Node("meta_or", [exp]))
        elif exp.T == "meta_or":
            or_exp = []
            assert exp.T == "meta_or"
            for meta_and in exp.C:
                and_exp = []
                assert meta_and.T == "meta_and"
                for c in meta_and.C:
                    assert c.T in CMP_OPS or c.T == "in", "Unknown operation %s, expected cmp op or 'in'" % (c.T,)
                    and_exp.append((c.T, c.C[0], c.C[1]))
                or_exp.append(and_exp)
            return or_exp
            
class _____MetaExp(Node):

    def __init__(self, node):
        Node.__init__(self, "MetaExp")
        assert isinstance(node, Node) and node.T == "meta_or"
        self.Root = node       
        
    def _pretty(self, indent=""):
        out = []
        out.append("%sMetaExp:" % (indent,))
        out += ["%s  %s" % (indent, line) for line in self.Root._pretty()]
        return out

                
    def __and__(self, another):
        combined = Node("meta_and", [self.Root, another])
        self.Root = self.canonic(combined)
        
    def __or__(self, another):
        assert isinstance(self.Root, Node) and self.Root.T == "meta_or"
        assert isinstance(another, MetaExp) and isinstance(another.Root, Node) and another.Root.T == "meta_or"
        return MetaExp(self.Root + another.Root.C)
                
    def canonic(self, node):
        return self._MetaDNFConverter().walk(node)
        
            
    def dnf(self):
        return self._make_DNF(self.canonic(self.Root))
        
class _ParamsApplier(Descender):

    def DataSource(self, node, params):
        #print("_ParamsApplier.DataSource: params:", params)
        if params is not None:
            assert isinstance(params, dict)
            default_namespace = params.get("namespace")
            #print("_ParamsApplier.DataSource: default_namespace", default_namespace)
            patterns = []
            for match, (namespace, name) in node.Patterns:
                namespace = namespace or default_namespace
                patterns.append((match, (namespace, name)))
            node.Patterns = patterns
        return node

    def query(self, node, params):
        if len(node.C) == 2:
            p, q = args
            new_params = params.copy()
            new_params.update(p)
            return Node("query", [self.walk(q, new_params)])
        else:
            return node
            
    def qualified_name(self, node, params):
        if params is not None:
            assert isinsatnce(params, dict)
            assert len(node.M) == 2
            if node.M[0] is None:
                node.M[0] = params.get("namespace")
        return node


class _Converter(Transformer):

    def _apply_params(self, tree, params):
        #print("_Converter._apply_params: params:", params)
        out = _ParamsApplier().walk(tree, params)
        #print("_Converter._apply_params done")
        return out
    
    def convert(self, tree, default_namespace):
        tree = self.transform(tree)
        #print("_Converter.transform: tree:", tree.pretty())
        return self._apply_params(tree, {"namespace":default_namespace})

    def query(self, args):
        if len(args) == 2:
            params, query = args
            return self._apply_params(query, params)
        else:
            return args[0]
        
    def s_(self, args):
        assert len(args) == 1
        return args[0]

    def int_constant(self, args):
        return int(args[0].value)
        
    def float_constant(self, args):
        return float(args[0].value)

    def bool_constant(self, args):
        #print("bool_constant:", args, args[0].value)
        return args[0].value.lower() == "true"
        
    def string_constant(self, args):
        s = args[0].value
        if s[0] == '"':
            s = s[1:-1]
        return s
        
    def data_source(self, args):
        spec_list = args[0].M
        with_children = False
        recursively = False
        having = None
        args_ = args[1:]
        for i, a in enumerate(args_):
            if a.value == "children":
                with_children = True
            elif a.value == "recursively":
                recursively = True
            elif a.value == "having":
                having = args_[i+1]
        ds = DataSource(spec_list, with_children, recursively, having)
        #print("data_source:", ds)
        return ds
        
    def source_spec_list(self, args):
        return Node("source_spec_list", [], meta=[a.M for a in args])
        
    def dataset(self, args):
        return 

    def source_spec(self, args):
        assert len(args) == 1
        return Node("source_spec", meta=(args[0].T == "dataset_pattern", args[0].M))
            
    def dataset_pattern(self, args):
        if len(args) == 1:
            return Node("dataset_pattern", meta=[None, args[0].value])
        else:
            return Node("dataset_pattern", meta=[args[0].value, args[1].value])
        
    def qualified_name(self, args):
        if len(args) == 1:
            return Node("qualified_name", meta=[None, args[0].value])
        else:
            return Node("qualified_name", meta=[args[0].value, args[1].value])
        
    def named_query(self, args):
        assert len(args) == 1
        return Node("named_query", meta = args[0].M)       # value = (namespace, name) - tuple
        
    def exp_list(self, args):
        return args

    def __default__(self, type, children, meta):
        #print("__default__:", data, children)
        return Node(type, children)
        
    def param_def(self, args):
        return (args[0].value, args[1])

    def param_def_list(self, args):
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
        args = args[0].C
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
        #print("join: args:", args)
        #for a in args:
        #    print("  ", a.pretty())
        assert len(args) == 1
        args = args[0].C
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
        
    def qualified_name(self, args):
        assert len(args) in (1,2)
        if len(args) == 1:
            return Node("qualified_name", meta=[None, args[0].value])      # no namespace
        else:
            return Node("qualified_name", meta=[args[0].value, args[1].value])

    def dataset(self, args):
        assert len(args) in (1,2)
        if len(args) == 1:
            return Node("dataset", [args[0], None])       # dataset without meta filter
        else:
            return Node("dataset", [args[0], args[1]])
        
    def filter(self, args):
        assert len(args) == 3
        return Node("filter", args[2], meta = (args[0].value, args[1]))
        
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
        
    def meta_and(self, args):
        children = []
        for a in args:
            if a.T == "meta_and":
                children += a.C
            else:
                children.append(a)
        return Node("meta_and", children)
        
    def meta_or(self, args):
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
                "~~":   "!~~",
                "!~~":  "~~",
                "~~*":   "!~~*",
                "!~~*":  "~~*",
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
        Ascender.__init__(self)
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
        return Query.from_db(self.DB, namespace, name).parse()

class _ProvenancePusher(Ascender):

    @pass_node
    def parents_of(self, node):
        children = node.C
        assert len(children) == 1
        child = children[0]
        if isinstance(child, Node) and child.T in ("union", "join"):
            return Node(child.T, [Node("parents_of", cc) for cc in child.C])
        else:
            return node 

    @pass_node
    def children_of(self, node):
        children = node.C
        assert len(children) == 1
        child = children[0]
        if isinstance(child, Node) and child.T in ("union", "join"):
            # parents (union(x,y,z)) = union(parents(x), parents(y), parents(z))
            return Node(child.T, [Node("children_of", cc) for cc in child.C])
        else:
            return node

class _MetaExpPusher(Descender):

    def meta_filter(self, node, meta_exp):
        node_q, node_exp = node.C
        if meta_exp is None:
            meta_exp = node_exp
        elif node_exp is None:
            meta_exp = meta_exp     # duh
        else:
            meta_exp = Node("meta_and", [meta_exp, node_exp])
        #print("_MetaExpPusher.meta_filter: node_q:", node_q.pretty())
        out = self.walk(node_q, meta_exp)
        #print("                          walk()->:", out.pretty())
        return out
        
    def join(self, node, meta_exp):
        return Node("join", [self.walk(c, meta_exp) for c in node.C])

    def union(self, node, meta_exp):
        return Node("union", [self.walk(c, meta_exp) for c in node.C])
        
    def minus(self, node, meta_exp):
        assert len(node.C) == 2
        left, right = node.C
        return Node(t, [self.walk(left, meta_exp), right])
        
    def filter(self, node, meta_exp):
        return Node("meta_filter", [node, meta_exp])
        
    def DataSource(self, node, meta_exp):
        #print("_MetaExpPusher.DataSource: node:", node.pretty())
        if meta_exp is not None:    node.addWhere(meta_exp)
        #print("_MetaExpPusher.DataSource: out: ", node.pretty())
        return node
        
class _DNFConverter(Visitor):

    # find all DataSource nodes and apply DNF converter to their Wheres

    def DataSource(self, node, context):
        exp = node.Wheres
        if exp is not None:
            assert isinstance(exp, Node)
            exp = _MetaRegularizer().walk(exp)
            node.WheresDNF = _MetaRegularizer._make_DNF_lists(exp)
        return False
        
class _SQLGenerator(Ascender):

    @pass_node
    def DataSource(self, data_source):
        keep_meta = True
        return Node("SQL", meta=data_source.sql())
            

class _Evaluator(Ascender):

    def __init__(self, db, filters, with_meta, limit):
        Ascender.__init__(self)
        self.Filters = filters
        self.DB = db
        self.WithMeta = with_meta
        self.Limit = limit

    def parents_of(self, args, meta):
        assert len(args) == 1
        arg = args[0]
        return arg.parents(with_metadata=True)

    def children_of(self, args, meta):
        assert len(args) == 1
        arg = args[0]
        return arg.children(with_metadata=True)
            
    @pass_node        
    def DataSource(self, node):
        assert isinstance(node, DataSource)
        #print("_Evaluator.DataSource: node:", node.pretty())
        return DBFileSet.from_data_source(self.DB, node, self.WithMeta, self.Limit)
        
    def ____dataset(self, args, meta, provenance=None):
        assert len(args) == 2
        dataset_name, meta_exp = args
        namespace, name = dataset_name.M
        dataset = DBDataset.get(self.DB, namespace, name)
        keep_meta = meta["keep_meta"]
        files = dataset.list_files(condition=meta_exp, 
            relationship="self" if provenance is None else provenance, 
            with_metadata=keep_meta, limit=self.Limit)
        #print ("Evaluator.dataset: files:", files)
        assert isinstance(files, DBFileSet)
        return files
        
    def source_spec_list(self, args, meta):
        #print("source_spec_list: args:", args)
        return DBFileSet.union(self.DB, args)
        
    def data_source_rec(self, args, meta):
        assert len(args) == 1
        return args[0]
        
    def data_source(self, args, meta):
        assert len(args) == 1
        return args[0]
        
    def union(self, args, meta):
        return DBFileSet.union(self.DB, args)
        
    def join(self, args, meta):
        return DBFileSet.join(self.DB, args)
        
    def minus(self, expressions, meta):
        assert len(expressions) == 2
        left, right = expressions
        return left - right

    def filter(self, args, meta):
        name, params = meta
        inputs = args
        #print("Evaluator.filter: inputs:", inputs)
        filter_function = self.Filters[name]
        return DBFileSet(self.DB, filter_function(inputs, params))
        
    def meta_filter(self, args, meta):
        assert len(args) == 2
        files, meta_exp = args
        out = DBFileSet(self.DB, (f for f in files if self.evaluate_meta_expression(f, meta_exp)))
        #print("Evaluator.meta_filter: out:", out)
        return out
        
        
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

    _Parser = Lark(MQL_Grammar, start="query")

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
        #print("parsed:", self.Parsed.pretty())
        return self.Parsed
        
    def assemble(self, db, default_namespace = None):
        #print("Query.assemble: self.Assembled:", self.Assembled)
        if self.Assembled is None:
            parsed = self.parse()
            #print("Query.assemble(): parsed:", parsed.pretty())
            self.Assembled = _Assembler(db, default_namespace).walk(parsed)
            #print("Query.assemble: self.Assembled:", self.Assembled)
        return self.Assembled
        
    def skip_assembly(self):
        if self.Assembled is None:
            self.Assembled = self.parse()
        return self.Assembled
        
    def optimize(self):
        #print("Query.optimize: entry")
        assert self.Assembled is not None
        if self.Optimized is None:
            #print("optimize: assembled:", self.Assembled.pretty())
            optimized = _ProvenancePusher().walk(self.Assembled)
            #print("optimize: after _ProvenancePusher:", optimized.pretty())
            optimized = _MetaExpPusher().walk(optimized, None)
            #print("Query.optimize: optimized:", optimized.pretty())
            optimized = _DNFConverter().walk(optimized, None)
            #print("Query.optimize: DNF converted:", optimized.pretty())
            self.Optimized = optimized
        return self.Optimized

    def generate_sql(self):
        #print("generate_sql: canonic:", canonic.pretty())
        sql = _SQLGenerator().walk(canonic)
        #print("generate_sql: canonic: sql:", sql.pretty())
        return sql

    def _____limit_results(self, gen, limit):
        #print("_limit_results: gen:", gen)
        for x in gen:
            if limit > 0:
                yield x
            else:
                break
            limit -= 1

    def run(self, db, filters={}, limit=None, with_meta=True):
        #print("Query.run: DefaultNamespace:", self.DefaultNamespace)
        self.assemble(db, self.DefaultNamespace)
        #print("Query.run: assemled:", self.Assembled.pretty())
        optimized = self.optimize()
        out = _Evaluator(db, filters, with_meta, limit).walk(optimized)
        #print ("run: out:", out)
        return out
        
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

        
