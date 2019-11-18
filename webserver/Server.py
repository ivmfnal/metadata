from webpie import WPApp, WPHandler
import psycopg2, json
from dbobjects import DBFile, DBDataset
from wsdbtools import ConnectionPool
from urllib.parse import quote_plus, unquote_plus

from py3 import to_str
from expressions2 import Query

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
            
    def file(self, request, relpath, **args):
        method = request.method
        if method == "POST":
            return self.create_file(request, relpath, **args)
        elif method == "PUT":
            return self.update_file(request, relpath, **args)
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

    def create_file(self, request, relpath, name=None, fid=None, dataset=None, **args):
        fid, namespace, name = self.extract_file_spec(fid, name, relpath)
        with self.App.DB.connect() as db:
            f = DBFile(db, name=name, namespace=namespace, fid=fid).save()
            if request.body_file:
                metadata = request.body_file.read()
                if metadata:
                    metadata = json.loads(metadata)
                    f.save_metadata(metadata)
            return f.FID
        

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
            
    def query(self, request, relpath, format="json", query=None, **args):
        if query is not None:
            query_text = unquote_plus(query)
        elif "query" in request.POST:
            query_text = request.POST["query"]
        else:
            query_text = request.body_file.read()
        query_text = to_str(query_text or "")
        if query_text:
            with self.App.DB.connect() as db:
                results = Query(db, query_text).run(self.App.filters())
            url_query = query_text.replace("\n"," ")
            while "  " in url_query:
                url_query = url_query.replace("  ", " ")
            url_query = quote_plus(url_query)
        else:
            results = None
            url_query = None
        if format == "json":
            data = [
                { 
                    "filename":f.Name, "namespace":f.Namespace,
                    "fid":f.FID,
                    "metadata": f.Metadata or {}
                } for f in results ]
            data_json = json.dumps(data)
            resp = (data_json, "text/json")
        elif format == "html":
            resp = self.render_to_response("query.html", 
                query=query_text, url_query=url_query,
                show_files=results is not None, files=results)
            resp.content_type = "text/html"
        return resp
            
            

        
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
    application=App(config, DataHandler)
    application.initJinjaEnvironment(tempdirs=".")
    application.run_server(8080)
    
else:
    # running unser uwsgi
    config = os.environ["METADATA_SERVER_CFG"]
    config = yaml.load(config, Loader=yaml.SafeLoader)       
    application = App(config, DataHandler)
    
    
        
