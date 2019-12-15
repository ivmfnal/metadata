from webpie import WPApp, WPHandler
import psycopg2, json, time, secrets
from dbobjects import DBFile, DBDataset, DBFileSet, DBNamedQuery
from wsdbtools import ConnectionPool
from urllib.parse import quote_plus, unquote_plus

from py3 import to_str
from mql5 import Query
from Version import Version

class GUIHandler(WPHandler):

    def show_file(self, request, relpath, name=None, fid=None, **args):
        fid, namespace, name = self.extract_file_spec(fid, name, relpath)
        with self.App.DB.connect() as db:
            f = DBFile.get(db, fid=fid, namespace=namespace, name=name, with_metadata=True)
            return self.render_to_response("show_file.html", f=f)

    def datasets(self, request, relpath, **args):
        with self.App.DB.connect() as db:
            datasets = DBDataset.list(db)
        datasets = sorted(list(datasets), key=lambda x: (x.Namespace, x.Name))
        return self.render_to_response("datasets.html", datasets=datasets)

    def dataset_files(self, request, relpath, format="html", dataset=None):
        namespace, name = (dataset or relpath).split(":",1)
        with self.App.DB.connect() as db:
            dataset = DBDataset.get(db, namespace, name)
            files = sorted(list(dataset.list_files(with_metadata=True)), key=lambda x: (x.Namespace, x.Name))
        return self.render_to_response("dataset_files.html", files=files)
	
    def query(self, request, relpath, query=None, namespace=None, **args):
        if query is not None:
            query_text = unquote_plus(query)
        elif "query" in request.POST:
            query_text = request.POST["query"]
        else:
            query_text = request.body_file.read()
        query_text = to_str(query_text or "")
        if namespace is None:
            namespace = request.POST.get("namespace")
        t0 = time.time()
        if query_text:
            with self.App.DB.connect() as db:
                results = Query(query_text, default_namespace=namespace or None).run(db, self.App.filters())
            url_query = query_text.replace("\n"," ")
            while "  " in url_query:
                url_query = url_query.replace("  ", " ")
            url_query = quote_plus(url_query)
            if namespace: url_query += "&namespace=%s" % (namespace,)
        else:
            results = None
            url_query = None
        files = None if results is None else list(results)
        #print("query: results:", len(files))
        runtime = time.time() - t0
        resp = self.render_to_response("query.html", 
            query=query_text, url_query=url_query,
            show_files=files is not None, files=files, 
            runtime = runtime,
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
        
    def create_file(self, request, relpath, name=None, fid=None, dataset=None, **args):
        assert dataset is not None
        dataset_namespace, dataset_name = dataset.split(":", 1)
        fid, namespace, name = self.extract_file_spec(fid, name, relpath)
        assert namespace is not None and name is not None
        with self.App.DB.connect() as db:
            # TODO: make it a single DB transaction
            ds = DBDataset.get(db, dataset_namespace, dataset_name)
            f = DBFile(db, name=name, namespace=namespace, fid=fid).save()
            if request.body_file:
                metadata = request.body_file.read()
                if metadata:
                    metadata = json.loads(metadata)
                    f.save_metadata(metadata)
            ds.add_file(f)
            return f.FID

class DataHandler(WPHandler):

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
            
    def create_dataset(self, request, relpath, **args):
        with self.App.DB.connect() as db:
            namespace, name = relpath.split(":", 1)
            dataset = DBDataset(namespace, name).save()
            return dataset.to_json(), "text/json"  
            
    def file(self, request, relpath, f="html", **args):
        method = request.method
        if method == "POST":
            return self.create_file(request, relpath, **args)
        elif method == "PUT":
            return self.update_file(request, relpath, **args)
        else:
            if f == "html":
                return self.show_file(request, relpath, **args)
            else:
                return self.get_file(request, relpath, **args)
            
    def extract_file_spec(self, fid, name, relpath):
        if name is None and fid is None and relpath:
            if ":" in relpath:
                name = relpath
            else:
                fid = relpath
        namespace = None
        if name:
            namespace, name = name.split(':', 1)
        return fid or None, namespace or None, name or None

    def get_file(self, request, relpath, name=None, fid=None, with_metadata="no", **args):
        with_metadata = with_metadata == "yes"
        fid, namespace, name = self.extract_file_spec(fid, name, relpath)
        if fid and namespace:   
            return 403, "Either namespace/name or FID must be specified, not both"
        if fid is None and namespace is None:   
            return 403, "Either namespace/name or FID must be specified"
        with self.App.DB.connect() as db:
            if fid:
                f = DBFile.get(db, fid = fid)
            else:
                f = DBFile.get(db, namespace=namespace, name=name)
            return f.to_json(with_metadata=with_metadata), "text/json"
            
    def datasets(self, request, relpath, **args):
        with self.App.DB.connect() as db:
            datasets = DBDataset.list(db)
        return self.json_chunks((
            { "name":ds.Name, "namespace":ds.Namespace } for ds in datasets))

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
            
    def json_chunks(self, lst, chunk=100000):
        return self.text_chunks(self.json_generator(lst), chunk)
            
    def query(self, request, relpath, format="html", query=None, namespace=None, **args):
        if query is not None:
            query_text = unquote_plus(query)
        elif "query" in request.POST:
            query_text = request.POST["query"]
        else:
            query_text = request.body_file.read()
        query_text = to_str(query_text or "")
        if namespace is None:
            namespace = request.POST.get("namespace")
        t0 = time.time()
        if query_text:
            with self.App.DB.connect() as db:
                results = Query(query_text, default_namespace=namespace or None).run(db, self.App.filters())
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
        data = (
            { 
                "filename":f.Name, "namespace":f.Namespace,
                "fid":f.FID,
                "metadata": f.Metadata or {}
            } for f in results )
        return self.json_chunks(data), "text/json"
        
    def named_queries(self, request, relpath, format="html", namespace=None, **args):
        with self.App.DB.connect() as db:
            queries = list(DBNamedQuery.list(db, namespace))
        data = ("%s:%s" % (q.Namespace, q.Name) for q in queries)
        return self.json_chunks(data), "text/json"
            
class AuthHandler(WPHandler):

    TokenExpiration = 24*3600*3600
    
    def auth(self, request, relpath, **args):
        from rfc2617 import digest_server
        # give them cookie with the signed token
        
        ok, data = digest_server("metadata", request.environ, self.App.get_password)
        if ok:
            user = data
            token = SignedToken({"user": user}, expiration=self.TokenExpiration).encode(self.App.TokenSecret)
            resp = Response(token, content_type="text/plain")
            resp.set_cookie("auth_token", token, max_age = int(self.TokenExpiration))
            return resp
        elif data:
            resp = Response("Authorization required", status=401, headers={
                'WWW-Authenticate': header
            })
        else:
            return 403, "Authentication failed"

class RootHandler(WPHandler):
    
    def __init__(self, *params, **args):
        self.data = DataHandler(*params, **args)
        self.gui = GUIHandler(*params, **args)
        self.auth = AuthHandler(*params, **args)
        
class App(WPApp):

    def __init__(self, cfg, *args):
        WPApp.__init__(self, *args)
        self.Cfg = cfg
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
        
    def get_password(self, realm, username):
        # realm is ignored for now
        return self.Users.get(username).get("password")

    def filters(self):
        return self.Filters
       
import yaml, os

if __name__ == "__main__":
    import sys, getopt
    opts, args = getopt.getopt(sys.argv[1:], "c:")
    opts = dict(opts)
    config = opts.get("-c", os.environ.get("METADATA_SERVER_CFG"))
    config = yaml.load(open(config, "r"), Loader=yaml.SafeLoader)  
    #print (config)     
    application=App(config, RootHandler)
    application.initJinjaEnvironment(tempdirs=[config.get("templates", ".")], 
        globals={"GLOBAL_Version": Version})
    application.run_server(8080)
    
else:
    # running unser uwsgi
    config = os.environ["METADATA_SERVER_CFG"]
    config = yaml.load(open(config, "r"), Loader=yaml.SafeLoader)       
    application = App(config, RootHandler)
    application.initJinjaEnvironment(tempdirs=[config.get("templates", ".")], 
        globals={"GLOBAL_Version": Version})
    
    
        
