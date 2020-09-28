from lark import Lark
from lark import Transformer, Tree, Token
import pprint

class Token(object):
    
    JSON_CLASS = "token"

    def __init__(self, typ, value):
        self.T = typ
        self.V = value

    def __str__(self):
        return "Token(%s, %s)" % (self.T, self.V)

    def pretty(self):
        #print("pretty---")
        return self._pretty()
        
    def _pretty(self, indent=""):
        return ['%s%s "%s"' % (indent, self.T, self.V)]

    def jsonable(self):
        return dict(T=self.T, V=self.V)
        
    def to_json(self):
        d = self.jsonable()
        d["///class///"] = self.JSON_CLASS
        return json.dumps(d)

    @staticmethod
    def from_jsonable(data):
        if isinstance(data, dict) and data.get("///class///") == Token.JSON_CLASS:
            typ = data["T"]
            val = data["V"]
            return Token(typ, val)
        else:
            return data

    @staticmethod
    def from_json(text):
        return Token.from_jsonable(json.loads(text))

class Node(object):

    JSON_CLASS = "node"

    def __init__(self, typ, children=[], meta=None):
        self.T = typ
        self.M = meta
        self.C = children[:]

    def __str__(self):
        return "Node(%s (%d children) meta:%s)" % (self.T, len(self.C), self.M)
        
    __repr__ = __str__
        
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
        out.append("%s%s" % (indent, self.T))
        if self.M is not None:
            if isinstance(self.M, Node):
                meta_pretty = self.M._pretty("")
                out.append("%s. m:%s" % (indent, meta_pretty[0]))
                out += [indent + ". . " + l for l in meta_pretty[1:]]
            else:
                out.append("%s. (%s)" % (indent, self.M))
        
        nc = len(self.C)
        for i, c in enumerate(self.C):
            extra = ". "
            if isinstance(c, (Token, Node)):
                out += c._pretty(indent+extra)
            else:
                out.append("%s%s" % (indent + ". ", repr(c)))
        return out
        
    def pretty(self):
        #print("pretty---")
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
        if isinstance(data, dict) and data.get("///class///") == Node.JSON_CLASS:
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

class Visitor(object):	# deprecated

    #
    # Visits each node top-down. Calls corresponding method of each node passing the "context". 
    # If the method returns True, recursively visits the node children
    # Can be used to re-calculate metadata
    #

    def walk(self, node, context=None):
        if not isinstance(node, Node):
            return
        node_type, children = node.T, node.C
        
        if hasattr(self, node_type):
            method = getattr(self, node_type)
            visit_children = method(node, context)
        else:
            visit_children = self._default(node, context)

        if visit_children:
            for c in children:
                self.walk(c, context)
        return node

    def visit_children(self, node, context):
        for c in node.C:
            self.walk(c, context)
        
    def _default(self, node, context):
        return True
        
class Descender(object):

    #
    # Descends objects top to bottom, possibly replacing them
    # If a user method is defined for the node type, it has to explicitly call visit_children(self, context)
    # If the user method returns None, it is equivalent to returning the node itself
    # Default method does visit children
    #

    def walk(self, node, context=None):

        if not isinstance(node, Node):
            return node

        node_type, children = node.T, node.C
        
        if hasattr(self, node_type):
            method = getattr(self, node_type)
            new_node = method(node, context)
        else:
            new_node = self._default(node, context)

        if new_node is None:
            new_node = node

        return new_node

    def visit_children(self, node, context):
        node.C = [self.walk(c, context) for c in node.C]
        return node
        
    def _default(self, node, context):
        #print("Descender._default: node:", node.pretty())
        return self.visit_children(node, context)
        
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
            out = self._default(node, children)
        #print("Ascender %s: walk: out: %s" % (self.__class__.__name__, out))
        return out
        
    def _default(self, node, children):
        return Node(node.T, children=children, meta=node.M)
        
class PostParser(Transformer):
    
    #
    # Converts from Tree structure returned by Lark to Nodes
    #
    
    def __default__(self, data, children, meta):
        #print("PostParser.__default(", data, children, meta, ")")
        return Node(data, children)
        
    def __default_token__(self, token):
        return Token(token.type, token.value)
        
        