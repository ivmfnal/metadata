from webpie import WPApp, WPHandler, Response
import psycopg2, json, time, secrets
from dbobjects import DBFile, DBDataset, DBFileSet, DBNamedQuery
from wsdbtools import ConnectionPool
from urllib.parse import quote_plus, unquote_plus

from py3 import to_str
from mql5 import Query
from signed_token import SignedToken
from Version import Version

class BaseHandler(WPHandler):

    def text_chunks(self, gen, chunk=100000):
        buf = []
        size = 0
        for x in gen:
            n = len(x)
            buf.append(x)
            size += n
            if size >= chunk:
                yield "".join(buf)
                size = 0
                buf = []
        if buf:
            yield "".join(buf)
            


class GUIHandler(BaseHandler):

    def jinja_globals(self):
        user = self.App.user_from_request(self.Request)
        return {"GLOBAL_User":user}

    def index(self, request, relpath, **args):
        return self.redirect("./datasets")
        
    def mql(self, request, relpath, **args):
        namespace = request.POST.get("namespace") or self.App.DefaultNamespace
        query_text = request.POST.get("query")
        query = parsed = assembled = optimized = None
        results = False
        with_sql = None
        if query_text:
            query = Query(query_text, default_namespace=namespace or None)
            parsed = query.parse()
            with self.App.DB.connect() as db:
                assembled = query.assemble(db, namespace)
            optimized = query.optimize()
            with_sql = query.generate_sql()
            results = True
        
        return self.render_to_response("mql.html", namespace = namespace, show_results = results,
            query_text = query_text or "", parsed = parsed, assembled = assembled, optimized = optimized,
		    with_sql = with_sql)

    def show_file(self, request, relpath, fid=None, **args):
        with self.App.DB.connect() as db:
            f = DBFile.get(db, fid=fid, with_metadata=True)
            return self.render_to_response("show_file.html", f=f)

    def datasets(self, request, relpath, **args):
        with self.App.DB.connect() as db:
            datasets = DBDataset.list(db)
        datasets = sorted(list(datasets), key=lambda x: (x.Namespace, x.Name))
        return self.render_to_response("datasets.html", datasets=datasets)

    def dataset_files(self, request, relpath, dataset=None, with_meta="no"):
        with_meta = with_meta == "yes"
        namespace, name = (dataset or relpath).split(":",1)
        with self.App.DB.connect() as db:
            dataset = DBDataset.get(db, namespace, name)
            files = sorted(list(dataset.list_files(with_metadata=with_meta)), key=lambda x: (x.Namespace, x.Name))
        return self.render_to_response("dataset_files.html", files=files, dataset=dataset, with_meta=with_meta)
        
    def _meta_stats(self, files):
        #
        # returns [ (meta_name, [(value, count), ...]) ... ]
        #
        stats = {}
        for f in files:
            for n, v in f.Metadata.items():
                if isinstance(v, list): v = tuple(v)
                n_dict = stats.setdefault(n, {})
                count = n_dict.setdefault(v, 0)
                n_dict[v] = count + 1
        out = []
        for name, counts in stats.items():
            clist = []
            for v, c in counts.items():
                if isinstance(v, tuple):    v = list(v)
                clist.append((v, c))
            out.append((name, sorted(clist, key=lambda vc: (-vc[1], vc[0]))))
        return sorted(out)
        
    def query(self, request, relpath, query=None, namespace=None, **args):
        namespace = namespace or request.POST.get("namespace") or self.App.DefaultNamespace
        #print("namespace:", namespace)
        if query is not None:
            query_text = unquote_plus(query)
        elif "query" in request.POST:
            query_text = request.POST["query"]
        else:
            query_text = request.body_file.read()
        query_text = to_str(query_text or "")
        results = None
        url_query = None
        files = None
        runtime = None
        meta_stats = None
        with_meta = True
        if request.method == "POST":
                if request.POST["action"] == "run":
                        with_meta = request.POST.get("with_meta", "off") == "on"
                        t0 = time.time()
                        if query_text:
                            #print("with_meta=", with_meta)
                            with self.App.DB.connect() as db:
                                results = Query(query_text, default_namespace=namespace or None)    \
                                    .run(db, self.App.filters(), limit=1000, with_meta=with_meta)
                            url_query = query_text.replace("\n"," ")
                            while "  " in url_query:
                                url_query = url_query.replace("  ", " ")
                            url_query = quote_plus(url_query)
                            if namespace: url_query += "&namespace=%s" % (namespace,)
                        else:
                            results = None
                            url_query = None
                        files = None if results is None else list(results)
                        meta_stats = None if not with_meta else self._meta_stats(files)
                        #print("meta_stats:", meta_stats, "    with_meta:", with_meta, request.POST.get("with_meta"))
                            
                        #print("query: results:", len(files))
                        runtime = time.time() - t0
                elif request.POST["action"] == "load":
                        with self.App.DB.connect() as db:
                            namespace, name = request.POST["query_to_load"].split(":",1)
                            query_text = DBNamedQuery.get(db, namespace, name).Source

        with self.App.DB.connect() as db:
            queries = list(DBNamedQuery.list(db, namespace))
            queries = sorted(queries, key=lambda q: (q.Namespace, q.Name))
        
        resp = self.render_to_response("query.html", 
            named_queries = queries,
            query=query_text, url_query=url_query,
            show_files=files is not None, files=files, 
            runtime = runtime, meta_stats = meta_stats, with_meta = with_meta,
            namespace=namespace or "")
        return resp
        
    def named_queries(self, request, relpath, namespace=None, **args):
        with self.App.DB.connect() as db:
            queries = list(DBNamedQuery.list(db, namespace))
        return self.render_to_response("named_queries.html", namespace=namespace,
            queries = queries)
            
    def named_query(self, request, relpath, name=None, namespace=None, edit="no", **args):
        if namespace is None:
            name, namespace = name.split(":",1)
            
        with self.App.DB.connect() as db:
            query = DBNamedQuery.get(db, namespace, name)
        
        return self.render_to_response("named_query.html", 
                query=query, edit = edit=="yes")

    def create_named_query(self, request, relapth, **args):
        return self.render_to_response("named_query.html",
                create=True)

    def save_named_query(self, request, relpath, **args):
        name = request.POST["name"]
        namespace = request.POST["namespace"]
        source = request.POST["source"]
        create = request.POST["create"] == "yes"
        
        with self.App.DB.connect() as db:
            query = DBNamedQuery(db, name=name, namespace=namespace, source=source).save()
        
        return self.render_to_response("named_query.html", query=query, edit = True)
        
class DataHandler(BaseHandler):

    def json_generator(self, lst):
        from collections.abc import Iterable
        assert isinstance(lst, Iterable)
        yield "["
        first = True
        for x in lst:
            j = json.dumps(x)
            if not first: j = ","+j
            yield j
            first = False
        yield "]"
        
    def json_chunks(self, lst, chunk=100000):
        return self.text_chunks(self.json_generator(lst), chunk)

    def datasets(self, request, relpath, **args):
        with self.App.DB.connect() as db:
            datasets = DBDataset.list(db)
        return self.json_chunks((
            { "name":ds.Name, "namespace":ds.Namespace } for ds in datasets))

    def dataset(self, request, relpath, **args):
        method = request.method
        if method == "POST":
            return self.create_dataset(request, relpath, **args)
        elif method == "PUT":
            return self.update_dataset(request, relpath, **args)

        # assume GET
        with self.App.DB.connect() as db:
            namespace, name = relpath.split(":", 1)
            dataset = DBDataset.get(db, namespace, name)
            return dataset.to_json(), "text/json"
            
    def dataset_count(self, request, relpath, **args):
        namespace, name = relpath.split(":", 1)
        with self.App.DB.connect() as db:
            nfiles = DBDataset(db, namespace, name).nfiles
        return '{"nfiles":%d}\n' % (nfiles,), {"Content-Type":"text/json",
            "Access-Control-Allow-Origin":"*"
        } 
        
            
    def create_dataset(self, request, relpath, **args):
        with self.App.DB.connect() as db:
            namespace, name = relpath.split(":", 1)
            dataset = DBDataset(namespace, name).save()
            return dataset.to_json(), "text/json"  
            
    def file(self, request, relpath, **args):
        method = request.method
        if method == "POST":
            return self.create_file(request, relpath, **args)
        elif method == "PUT":
            return self.update_file(request, relpath, **args)
        else:
            return self.get_file(request, relpath, **args)

    def create_file(self, request, relpath, fid=None, parent=None, **args):
        # method: POST, URI: .../file/dataset:name/namespace:name?fid=fid&parent=fid
        # request body = metadata in JSON format
        dataset_spec, file_spec = relpath.split("/",1)
        dataset_namespace, dataset_name = dataset_spec.split(":",1)
        file_namespace, file_name = file_spec.split(":",1)
        metadata = json.loads(request.body) if request.body else None
        with self.App.DB.connect() as db:
                ds = DBDataset.get(db, dataset_namespace, dataset_name)
                f = DBFile(db, file_namespace, file_name, fid=fid).save(do_commit=False)
                if metadata:
                        f.save_metadata(metadata, do_commit=False)
                if parent is not None:
                        parent = DBFile.get(db, fid=parent)
                        parent.add_child(f, do_commit=False)
                ds.add_file(f, do_commit=True)
        return json.dumps({"fid":f.FID}) + "\n", "text/json"
            
    def update_file(self, request, relpath, fid=None, **args):
        # update file metadata
        # method: PUT, URI: .../file/namespace:name or
        #              URI: .../file?fid=fid
        # request body = metadata in JSON format
        if (not relpath) == (not fid):
                return 403, "Either namespace:name or FID must be specified, but not both"
        namespace = name = None
        if relpath:
                namespace, name = relpath.split(":",1)
        metadata = json.loads(request.body)
        with self.App.DB.connect() as db:
                f = DBFile.get(db, namespace=namespace, name=name, fid=fid)
                f.save_metadata(metadata)
        return json.dumps({"fid":f.FID}) + "\n", "text/json"
            
    def get_file(self, request, relpath, fid=None, with_metadata="yes", **args):
        if (not relpath) == (not fid):
                return 403, "Either namespace:name or FID must be specified, but not both"
        namespace = name = None
        if relpath:
                namespace, name = relpath.split(":",1)
        with_metadata = with_metadata == "yes"
        with self.App.DB.connect() as db:
            if fid:
                f = DBFile.get(db, fid = fid)
            else:
                f = DBFile.get(db, namespace=namespace, name=name)
            return f.to_json(with_metadata=with_metadata), "text/json"
            
    def query(self, request, relpath, query=None, namespace=None, with_meta="no", **args):
        with_meta = with_meta == "yes"
        namespace = namespace or self.App.DefaultNamespace
        if query is not None:
            query_text = unquote_plus(query)
        elif "query" in request.POST:
            query_text = request.POST["query"]
        else:
            query_text = request.body_file.read()
        query_text = to_str(query_text or "")
        t0 = time.time()
        if query_text:
            with self.App.DB.connect() as db:
                results = Query(query_text, default_namespace=namespace or None) \
                    .run(db, self.App.filters(), with_meta=with_meta)
            url_query = query_text.replace("\n"," ")
            while "  " in url_query:
                url_query = url_query.replace("  ", " ")
            url_query = quote_plus(url_query)
            if namespace: url_query += "&namespace=%s" % (namespace,)
        else:
            results = None
            url_query = None
        if not results:
            return "[]", "text/json"
        if with_meta:
            data = (
                { 
                    "filename":f.Name, "namespace":f.Namespace,
                    "fid":f.FID,
                    "metadata": f.Metadata or {}
                } for f in results )
        else:
            data = (
                { 
                    "filename":f.Name, "namespace":f.Namespace,
                    "fid":f.FID
                } for f in results )
        return self.json_chunks(data), "text/json"
        
    def named_queries(self, request, relpath, namespace=None, **args):
        with self.App.DB.connect() as db:
            queries = list(DBNamedQuery.list(db, namespace))
        data = ("%s:%s" % (q.Namespace, q.Name) for q in queries)
        return self.json_chunks(data), "text/json"
            
class AuthHandler(WPHandler):

    def whoami(self, request, relpath, **args):
        return str(self.App.user_from_request(request)), "text/plain"
        
    def auth(self, request, relpath, redirect=None, **args):
        from rfc2617 import digest_server
        # give them cookie with the signed token
        
        ok, data = digest_server("metadata", request.environ, self.App.get_password)
        if ok:
            resp = self.App.response_with_auth_cookie(data, redirect)
            return resp
        elif data:
            return Response("Authorization required", status=401, headers={
                'WWW-Authenticate': data
            })

        else:
            return 403, "Authentication failed"

    def logout(self, request, relpath, redirect=None, **args):
        return self.App.response_with_unset_auth_cookie(redirect)

class RootHandler(WPHandler):
    
    def __init__(self, *params, **args):
        WPHandler.__init__(self, *params, **args)
        self.data = DataHandler(*params, **args)
        self.gui = GUIHandler(*params, **args)
        self.auth = AuthHandler(*params, **args)

    def index(self, req, relpath, **args):
        return self.redirect("./gui/index")
        
class App(WPApp):

    Version = Version

    def __init__(self, cfg, root, **args):
        WPApp.__init__(self, root, **args)
        self.Cfg = cfg
        self.DefaultNamespace = cfg.get("default_namespace")
        self.DB = ConnectionPool(postgres=cfg["database"]["connstr"])
        self.Filters = {}
        if "filters" in cfg:
            filters_mod = __import__(cfg["filters"].get("module", "filters"), 
                                globals(), locals(), [], 0)
            for n in cfg["filters"].get("names", []):
                self.Filters[n] = getattr(filters_mod, n)
                
        #
        # Authentication/authtorization
        #        
        self.Users = cfg["users"]       #   { username: { "passwrord":password }, ...}
        self.TokenSecret = secrets.token_bytes(128)     # used to sign tokens
        self.Tokens = {}		# { token id -> token object }
        
    def get_password(self, realm, username):
        # realm is ignored for now
        return self.Users.get(username).get("password")

    TokenExpiration = 24*3600*3600

    def user_from_request(self, request):
        #print("user_from_request: cookies:", request.cookies)
        encoded = request.cookies.get("auth_token")
        #print("user_from_request: encoded:", encoded)
        if not encoded:	return None
        try:	token = SignedToken.decode(encoded, self.TokenSecret)
        except:	return None		# invalid token
        return token.Payload.get("user")

    def response_with_auth_cookie(self, user, redirect):
        token = SignedToken({"user": user}, expiration=self.TokenExpiration).encode(self.TokenSecret)
        if redirect:
            resp = Response(status=302, headers={"Location": redirect})
        else:
            resp = Response(status=200, content_type="text/plain")
        resp.set_cookie("auth_token", token, max_age = int(self.TokenExpiration))
        return resp

    def response_with_unset_auth_cookie(self, redirect):
        if redirect:
            resp = Response(status=302, headers={"Location": redirect})
        else:
            resp = Response(status=200, content_type="text/plain")
        try:	resp.set_cookie("auth_token", "-", max_age=100)
        except:	pass
        return resp

    def filters(self):
        return self.Filters
       
import yaml, os

import sys, getopt
opts, args = getopt.getopt(sys.argv[1:], "c:")
opts = dict(opts)
config = opts.get("-c", os.environ.get("METADATA_SERVER_CFG"))
if not config:
    print("Configuration file must be provided either using -c command line option or via METADATA_SERVER_CFG environment variable")
    sys.exit(1)
config = yaml.load(open(config, "r"), Loader=yaml.SafeLoader)  
application=App(config, RootHandler, enable_static=True, static_location=config.get("static_path", "./static"))
application.initJinjaEnvironment(
    tempdirs=[config.get("templates", ".")], 
    globals={
        "GLOBAL_Version": Version, 
        "GLOBAL_SiteTitle": config.get("site_title", "DEMO Metadata Catalog")
    }
)

if __name__ == "__main__":
    application.run_server(8080)
else:
    # running under uwsgi
    pass
    
    
        
