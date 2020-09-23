import requests, json, fnmatch
from metacat.util import to_str, to_bytes, TokenLib

class ServerError(Exception):
    
    def __init__(self, url, status_code, message):
        self.URL = url
        self.StatusCode = status_code
        self.Message = message
        
    def __str__(self):
        return f"MetaCatServer error:\n  URL: {self.URL}\n  HTTP status code: {self.StatusCode}\n  Message: {self.Message}"

class HTTPClient(object):

    def __init__(self, server_url, token):
        self.ServerURL = server_url
        self.Token = token

    def get_json(self, uri_suffix):
        url = "%s/%s" % (self.ServerURL, uri_suffix)
        response = requests.get(url, 
                headers = {"X-Authentication-Token": self.Token.encode()}
        )
        if response.status_code != 200:
            raise ServerError(url, response.status_code, response.text)
        data = json.loads(response.text)
        return data
        
    def post_json(self, uri_suffix, data):
        if isinstance(data, (dict, list)):
            data = json.dumps(data)
        else:
            data = to_bytes(data)
        url = "%s/%s" % (self.ServerURL, uri_suffix)
        response = requests.post(url, 
                data = data,
                headers = {"X-Authentication-Token": self.Token.encode()}
        )
        if response.status_code != 200:
            raise ServerError(url, response.status_code, response.text)
        data = json.loads(response.text)
        return data
        

class MetaCatClient(HTTPClient):
    
    def __init__(self, server_url):    
        tl = TokenLib()
        HTTPClient.__init__(self, server_url, tl.get(server_url))

    def list_datasets(self, namespace_pattern=None, name_pattern=None, with_file_counts=False):
        url = "data/datasets?with_file_counts=%s" % ("yes" if with_file_counts else "no")
        lst = self.get_json(url)
        for item in lst:
            namespace, name = item["namespace"], item["name"]
            if namespace_pattern is not None and not fnmatch.fnmatch(namespace, namespace_pattern):
                continue
            if name_pattern is not None and not fnmatch.fnmatch(name, name_pattern):
                continue
            yield item
    
    def get_dataset(self, spec, namespace=None, name=None):
        if namespace is not None:
            spec = namespace + ':' + name
        item = self.get_json(f"data/dataset?dataset={spec}")
        return item

    def create_dataset(self, spec, parent=None):
        url = f"data/create_dataset?dataset={spec}"
        if parent:
            url += f"&parent={parent}"
        return self.get_json(url)
        
    def add_files(self, dataset, file_list, namespace=None):
        url = f"data/add_files?dataset={dataset}"
        if namespace:
            url += f"&namespace={namespace}"
        out = self.post_json(url, file_list)
        return out

    def declare_files(self, dataset, file_list, namespace=None):
        url = f"data/declare?dataset={dataset}"
        if namespace:
            url += f"&namespace={namespace}"
        out = self.post_json(url, file_list)
        return out

    def update_files(self, file_data, namespace=None):
        url = f"data/update"
        if namespace:
            url += f"?namespace={namespace}"
        out = self.post_json(url, file_data)
        return out
        
    def get_file(self, fid=None, name=None, with_metadata = True, with_relations=True):
        assert (fid is None) != (name is None), 'Either name="namespace:name" or fid="fid" must be specified, but not both'
        with_meta = "yes" if with_metadata else "no"
        with_rels = "yes" if with_relations else "no"
        url = f"data/file?with_metadata={with_meta}&with_relations={with_rels}"
        if name:
            url += f"&name={name}"
        else:
            url += f"&fid={fid}"        
        return self.get_json(url)

    def run_query(self, query, namespace=None, with_metadata=False):
        url = "data/query?with_meta=%s" % ("yes" if with_metadata else "no",)
        if namespace:
            url += f"&namespace={namespace}"
        results = self.post_json(url, query)
        return results
    
    def create_namespace(self, name, owner_role=None):
        url = f"data/create_namespace?name={name}"
        if owner_role:
            url += f"&owner={owner_role}"
        return self.get_json(url)
        
    def get_namespace(self, name):
        return self.get_json(f"data/namespace?name={name}")
        
    def list_namespaces(self, pattern=None):
        lst = self.get_json("data/namespaces")
        for item in lst:
            if pattern is None or fnmatch.fnmatch(item["name"], pattern):
                yield item
        
        
        