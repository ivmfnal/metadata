from webpie import WPApp, WPHandler, Response
import psycopg2, json, time, secrets, traceback
from dbobjects2 import DBFile, DBDataset, DBFileSet, DBNamedQuery, DBUser, DBNamespace, DBRole
from wsdbtools import ConnectionPool
#from ConnectionPool import ConnectionPool
from urllib.parse import quote_plus, unquote_plus

from py3 import to_str
from mql7 import Query
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
        return {"GLOBAL_User":self.authenticated_user()}
        
    def authenticated_user(self):
        username = self.App.user_from_request(self.Request)
        if not username:    return None
        db = self.App.connect()
        return DBUser.get(db, username)
        
    def is_admin(self, user):
        if not user:    return None
        db = self.App.connect()
        admin = DBRole.get(db, "admin")
        return user in admin

    def index(self, request, relpath, **args):
        return self.redirect("./datasets")
        
    def mql(self, request, relpath, **args):
        namespace = request.POST.get("namespace") or self.App.DefaultNamespace
        query_text = request.POST.get("query")
        query = None
        parsed = assembled = optimized = with_sql = ""
        results = False
        if query_text:
        
            query = Query(query_text, default_namespace=namespace or None)
            
            try:    parsed = query.parse().pretty()
            except:
                parsed = traceback.format_exc()
                
            db = self.App.connect()
            try:    assembled = query.assemble(db, namespace).pretty()
            except:
                assembled = traceback.format_exc()
                    
            try:    
                optimized = query.optimize()
                optimized = optimized.pretty()
                #print("Server: optimized:", optimized)
            except:
                optimized = traceback.format_exc()
                
            try:    with_sql = query.generate_sql()
            except:
                   with_sql = traceback.format_exc()
                   
            results = True
        
        return self.render_to_response("mql.html", namespace = namespace, show_results = results,
            query_text = query_text or "", parsed = parsed, assembled = assembled, optimized = optimized,
		    with_sql = with_sql)

    def show_file(self, request, relpath, fid=None, **args):
        db = self.App.connect()
        f = DBFile.get(db, fid=fid, with_metadata=True)
        return self.render_to_response("show_file.html", f=f)

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
        
        save_as_dataset = "save_as_dataset" in request.POST
        
        db = self.App.connect()
        #print("query: method:", request.method)
        if request.method == "POST":
                if request.POST["action"] == "run":
                        with_meta = request.POST.get("with_meta", "off") == "on"
                        t0 = time.time()
                        if query_text:
                            #print("with_meta=", with_meta)
                            if True:
                                results = Query(query_text, default_namespace=namespace or None)    \
                                    .run(db, self.App.filters(), 
                                    limit=1000 if not save_as_dataset else None, 
                                    with_meta=with_meta)
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
                        with self.App.connect() as db:
                            namespace, name = request.POST["query_to_load"].split(":",1)
                            query_text = DBNamedQuery.get(db, namespace, name).Source
                            
        user = self.authenticated_user()
        namespaces = None
        error = None
        message = None
        if True:
            queries = list(DBNamedQuery.list(db, namespace))
            queries = sorted(queries, key=lambda q: (q.Namespace, q.Name))
            if user:
                namespaces = DBNamespace.list(db, owned_by_user=user)
                
            if files is not None and "save_as_dataset" in request.POST:
                if user is None:
                    error = "Unauthenticated user"
                else:
                    dataset_namespace = request.POST["save_as_dataset_namespace"]
                    dataset_name = request.POST["save_as_dataset_name"]
                
                    existing_dataset = DBDataset.get(db, dataset_namespace, dataset_name)
                    if existing_dataset != None:
                        error = "Dataset %s:%s already exists" % (dataset_namespace, dataset_name)
                    else:
                        ns = DBNamespace.get(db, dataset_namespace)
                        if ns is None:
                            error = "Namespace is not found"
                        elif not user in ns.Owner:
                            error = "User not authorized to access the namespace %s" % (dataset_namespace,)
                        else:
                            ds = DBDataset(db, dataset_namespace, dataset_name)
                            ds.save()
                            files = list(files)
                            ds.add_files(files)
                            message = "Dataset %s:%s with %d files created" % (dataset_namespace, dataset_name, len(files))
                            
        attr_names = set()
        if files is not None:
            lst = []
            for f in files:
                lst.append(f)
                if len(lst) >= 1000:
                    #if len(lst) % 100 == 0: print("lst:", len(lst))
                    break
            files = lst
            for f in files:
                if f.Metadata:
                    for n in f.Metadata.keys():
                        attr_names.add(n)
        #print("Server.query: file list generated")
                
        resp = self.render_to_response("query.html", 
            attr_names = sorted(list(attr_names)),
            message = message, error = error,
            allow_save_as_dataset = user is not None, namespaces = namespaces,
            named_queries = queries,
            query=query_text, url_query=url_query,
            show_files=files is not None, files=files, 
            runtime = runtime, meta_stats = meta_stats, with_meta = with_meta,
            namespace=namespace or "")
        return resp
        
    def named_queries(self, request, relpath, namespace=None, **args):
        db = self.App.connect()
        queries = list(DBNamedQuery.list(db, namespace))
        return self.render_to_response("named_queries.html", namespace=namespace,
            queries = queries)
            
    def named_query(self, request, relpath, name=None, namespace=None, edit="no", **args):
        if namespace is None:
            name, namespace = name.split(":",1)
            
        db = self.App.connect()
        query = DBNamedQuery.get(db, namespace, name)
        
        return self.render_to_response("named_query.html", 
                query=query, edit = edit=="yes")

    def create_named_query(self, request, relapth, **args):
        me = self.authenticated_user()
        if me is None:   
            self.redirect(self.scriptUri() + "/auth/login?redirect=" + self.scriptUri() + "/gui/create_named_query")
        
        
        return self.render_to_response("named_query.html", namespaces=me.namespaces(), create=True)

    def save_named_query(self, request, relpath, **args):
        name = request.POST["name"]
        namespace = request.POST["namespace"]
        source = request.POST["source"]
        create = request.POST["create"] == "yes"
        
        db = self.App.connect()
        query = DBNamedQuery(db, name=name, namespace=namespace, source=source).save()
        
        return self.render_to_response("named_query.html", query=query, edit = True)
        
    def users(self, request, relpath, **args):
        if not self.authenticated_user():
            self.redirect(self.scriptUri() + "/auth/login?redirect=" + self.scriptUri() + "/gui/users")
        db = self.App.connect()
        users = DBUser.list(db)
        return self.render_to_response("users.html", users=users)
        
    def user(self, request, relpath, username=None, **args):
        db = self.App.connect()
        user = DBUser.get(db, username)
        me = self.authenticated_user()
        all_roles = DBRole.list(db)
        return self.render_to_response("user.html", all_roles=all_roles, user=user, edit=self.is_admin(me), create=False)
        
    def create_user(self, request, relpath, **args):
        me = self.authenticated_user()
        return self.render_to_response("user.html", create=self.is_admin(me), edit=False)
        
    def save_user(self, request, relpath, **args):
        db = self.App.connect()
        username = request.POST["username"]
        me = self.authenticated_user()
        u = DBUser.get(db, username)
        if u is None:   
            u = DBUser(db, username, request.POST["name"], request.POST["email"], request.POST["flags"])
        else:
            u.Name = request.POST["name"]
            u.EMail = request.POST["email"]
            if self.is_admin(me):   u.Flags = request.POST["flags"]
        if self.is_admin(me) or me.Username == u.Username:
            u.save()
        self.redirect("./users")
        
    def namespaces(self, request, relpath, **args):
        db = self.App.connect()
        namespaces = DBNamespace.list(db)
        return self.render_to_response("namespaces.html", namespaces=namespaces)
        
    def namespace(self, request, relpath, name=None, **args):
        db = self.App.connect()
        ns = DBNamespace.get(db, name)
        me = self.authenticated_user()
        edit = me in ns.Owner or self.is_admin(me)
        return self.render_to_response("namespace.html", namespace=ns, edit=edit, create=False)
        
    def create_namespace(self, request, relpath, **args):
        me = self.authenticated_user()
        if not me:
            self.redirect(self.scriptUri() + "/auth/login?redirect=" + self.scriptUri() + "/gui/create_namespace")
        roles = me.roles()
        return self.render_to_response("namespace.html", roles=roles, create=True, edit=False)
        
    def save_namespace(self, request, relpath, **args):
        db = self.App.connect()
        name = request.POST["name"]
        role = request.POST.get("role")
        if role is not None:
            role = DBRole.get(db, role)
        ns = DBNamespace.get(db, name)
        if ns is None:
            assert role is not None
            ns = DBNamespace(db, name, role)
            ns.save()
        self.redirect("./namespaces")
        
    def datasets(self, request, relpath, **args):
        db = self.App.connect()
        datasets = DBDataset.list(db)
        datasets = sorted(list(datasets), key=lambda x: (x.Namespace, x.Name))
        return self.render_to_response("datasets.html", datasets=datasets)

    def dataset_files(self, request, relpath, dataset=None, with_meta="no"):
        with_meta = with_meta == "yes"
        namespace, name = (dataset or relpath).split(":",1)
        db = self.App.connect()
        dataset = DBDataset.get(db, namespace, name)
        files = sorted(list(dataset.list_files(with_metadata=with_meta)), key=lambda x: (x.Namespace, x.Name))
        return self.render_to_response("dataset_files.html", files=files, dataset=dataset, with_meta=with_meta)
        
    def create_dataset(self, request, relpath, **args):
        user = self.authenticated_user()
        if not user:
            self.redirect(self.scriptUri() + "/auth/login?redirect=" + self.scriptUri() + "/gui/create_dataset")
        db = self.App.connect()
        namespaces = (ns for ns in DBNamespace.list(db) if ns.Owner == user)
        return self.render_to_response("dataset.html", namespaces=namespaces, edit=False, create=True)
        
    def dataset(self, request, relpath, namespace=None, name=None, **args):
        db = self.App.connect()
        dataset = DBDataset.get(db, namespace, name)
        if dataset is None: self.redirect("./datasets")

        nfiles = dataset.nfiles
        files = sorted(list(dataset.list_files(with_metadata=True, limit=100)), key = lambda x: x.Name)
        #print ("files:", len(files))
        attr_names = set()
        for f in files:
            if f.Metadata:
                for n in f.Metadata.keys():
                    attr_names.add(n)
        attr_names=sorted(list(attr_names))

        user = self.authenticated_user()
        edit = False
        if user is not None:
            ns = DBNamespace.get(db, name=dataset.Namespace)
            edit = ns.Owner == user
        return self.render_to_response("dataset.html", dataset=dataset, files=files, nfiles=nfiles, attr_names=attr_names, edit=edit, create=False)
        
    def save_dataset(self, request, relpath, **args):
        db = self.App.connect()
        if request.POST["create"] == "yes":
            ds = DBDataset(db, request.POST["namespace"], request.POST["name"]) # no parent dataset for now
        else:
            ds = DBDataset.get(db, request.POST["namespace"], request.POST["name"])
        ds.Monotonic = "monotonic" in request.POST
        ds.Frozen = "frozen" in request.POST
        ds.save()
        self.redirect("./datasets")
        
    def roles(self, request, relpath, **args):
        me = self.authenticated_user()
        if me is None:
            self.redirect(self.scriptUri() + "/auth/login?redirect=" + self.scriptUri() + "/gui/roles")
        db = self.App.connect()
        roles = DBRole.list(db)
        admin = self.is_admin(me)
        return self.render_to_response("roles.html", roles=roles, edit=admin, create=admin)
        
    def role(self, request, relpath, name=None, **args):
        me = self.authenticated_user()
        if me is None:
            self.redirect(self.scriptUri() + "/auth/login?redirect=" + self.scriptUri() + "/gui/roles")
        admin = self.is_admin(me)
        db = self.App.connect()
        role = DBRole.get(db, name)
        all_users = list(DBUser.list(db))
        #print("all_users:", all_users)
        return self.render_to_response("role.html", all_users=all_users, role=role, edit=admin, create=False)

    def create_role(self, request, relpath, **args):
        me = self.authenticated_user()
        if me is None:
            self.redirect(self.scriptUri() + "/auth/login?redirect=" + self.scriptUri() + "/gui/create_role")
        if not self.is_admin(me):
            self.redirect("./roles")
        db = self.App.connect()
        return self.render_to_response("role.html", all_users=list(DBUser.list(db)), edit=False, create=True)
        
    def save_role(self, request, relpath, **args):
        me = self.authenticated_user()
        if not self.is_admin(me):
            self.redirect("./roles")
        db = self.App.connect()
        rname = request.POST["name"]
        role = DBRole.get(db, rname)
        if role is None:
            role = DBRole(db, rname, "")
        role.Description = request.POST["description"]
        members = set()
        for k in request.POST.keys():
            if k.startswith("member:"):
                username = k.split(":", 1)[-1]
                members.add(username)
        role.Users = sorted(list(members))
        role.save()
        self.redirect("./role?name=%s" % (rname,))
            
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
        db = self.App.connect()
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
        db = self.App.connect()
        namespace, name = relpath.split(":", 1)
        dataset = DBDataset.get(db, namespace, name)
        return dataset.to_json(), "text/json"
            
    def dataset_count(self, request, relpath, **args):
        namespace, name = relpath.split(":", 1)
        db = self.App.connect()
        nfiles = DBDataset(db, namespace, name).nfiles
        return '{"nfiles":%d}\n' % (nfiles,), {"Content-Type":"text/json",
            "Access-Control-Allow-Origin":"*"
        } 
        
            
    def create_dataset(self, request, relpath, **args):
        db = self.App.connect()
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
        db = self.App.connect()
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
        db = self.App.connect()
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
        db = self.App.connect()
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
            print("query from URL:", query_text)
        elif "query" in request.POST:
            query_text = request.POST["query"]
            print("query from POST:", query_text)
        else:
            query_text = request.body
            print("query from body:", query_text)
        query_text = to_str(query_text or "")
        t0 = time.time()
        if not query_text:
            return "[]", "text/json"
            
        db = self.App.connect()
        results = Query(query_text, default_namespace=namespace or None) \
            .run(db, self.App.filters(), with_meta=with_meta)
        url_query = query_text.replace("\n"," ")
        while "  " in url_query:
            url_query = url_query.replace("  ", " ")
        url_query = quote_plus(url_query)
        if namespace: url_query += "&namespace=%s" % (namespace,)

        if not results:
            return "[]", "text/json"

        if with_meta:
            data = (
                { 
                    "name":f.Name, "namespace":f.Namespace,
                    "fid":f.FID,
                    "metadata": f.Metadata or {}
                } for f in results )
        else:
            data = (
                { 
                    "name":f.Name, "namespace":f.Namespace,
                    "fid":f.FID
                } for f in results )
        return self.json_chunks(data), "text/json"
        
    def named_queries(self, request, relpath, namespace=None, **args):
        db = self.App.connect()
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

    def login(self, request, relpath, message="", redirect=None, **args):
        return self.render_to_response("login.html", message=unquote_plus(message), redirect=redirect)
        
    def do_login(self, request, relpath, **args):
        username = request.POST["username"]
        redirect = request.POST.get("redirect", self.scriptUri() + "/gui/index")
        db = self.App.connect()
        u = DBUser.get(db, username)
        if not u:
            #print("authentication error")
            self.redirect("./login?message=User+%s+not+found" % (username,))
        #print("authenticated")
        return self.App.response_with_auth_cookie(username, redirect)


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
        self.DB = ConnectionPool(postgres=cfg["database"]["connstr"], max_idle_connections=3)
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

    def connect(self):
        conn = self.DB.connect()
        print("conn: %x" % (id(conn),), "   idle connections:", ",".join("%x" % (id(c),) for c in self.DB.IdleConnections))
        return conn
        
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
        #print("response_with_auth_cookie: user:", user, "  redirect:", redirect)
        token = SignedToken({"user": user}, expiration=self.TokenExpiration).encode(self.TokenSecret)
        if redirect:
            resp = Response(status=302, headers={"Location": redirect})
        else:
            resp = Response(status=200, content_type="text/plain")
        #print ("response:", resp, "  reditrect=", redirect)
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
cookie_path = config.get("cookie_path", "/metadata")
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
    
    
        
