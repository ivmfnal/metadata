import uuid, json

def fetch_generator(c):
    while True:
        tup = c.fetchone()
        if tup is None: break
        yield tup
        
def first_not_empty(lst):
    val = None
    for v in lst:
        val = v
        if v is not None and not (isinstance(v, list) and len(v) == 0):
            return v
    else:
        return val
        
def gather_metadata(self, db, g):
    f = None
    meta = {}
    for tup in g:
            fid, ns, n, an = tup[:4]
            v = first_not_empty(tup[4:])
            if f is not None and fid != f.FID:
                    yield f
                    f = None
            if f is None:
                    f = DBFile(db, fid=fid, name=n, namespace=ns)
                    f.Metadata = {}
            f.Metadata[an] = v
    if f is not None:
            yield f
            


class DBFileSet(object):
    
    def __init__(self, db, files):
        self.DB = db
        self.Files = files
        
    @staticmethod
    def from_shallow(db, g):
        # g is genetator of tuples (fid, namespace, name)
        return DBFileSet(db, (
            DBFile(db, namespace, name, fid=fid) for fid, namespace, name in g
        ))
        
    @staticmethod
    def from_metadata_tuples(db, g):
        def gather_meta(g):
            f = None
            meta = {}
            for tup in g:
                    fid, ns, n, an = tup[:4]
                    v = first_not_empty(tup[4:])
                    if f is not None and fid != f.FID:
                            yield f
                            f = None
                    if f is None:
                            f = DBFile(db, fid=fid, name=n, namespace=ns)
                            f.Metadata = {}
                    f.Metadata[an] = v
            if f is not None:
                    yield f
        return DBFileSet(db, gather_meta(g))
        
    def __iter__(self):
        return self.Files
            
    def parents(self, with_metadata = False):
        return self._relationship("parent", with_metadata)
            
    def children(self, with_metadata = False):
        return self._relationship("child", with_metadata)
            
    def _relationship(self, rel, with_metadata):
        if rel == "children":
            join = "f.id = pc.child_id and pc.parent_id in"
        else:
            join = "f.id = pc.parent_id and pc.child_id in"
            
        c = db.cursor()
        file_ids = list(f.FID for f in self.Files)
        if with_metadata:
            c.execute(f"""select distinct f.id, f.namespace, f.name, 
                                a.name,
                                a.int_array, a.float_array, a.string_array, a.bool_array,
                                a.int_value, a.float_value, a.string_value, a.bool_value
                        from files f, parent_child pc, file_attributes a
                        where a.file_id = f.id
                                and {join} %s
                        order by f.id
                        """,
                (file_ids,))
            return self.gather_metadata(self.DB, fetch_generator(c))
        else:
            c.execute(f"""select distinct f.id, f.namespace, f.name 
                        from files f, parent_child pc
                        where 
                                and {join} %s
                        """,
                (file_ids,))
            return DBFileSet.from_shallow(self.DB, fetch_generator(c))
            

class DBFile(object):

    def __init__(self, db, namespace = None, name = None, metadata = None, fid = None):
        assert (namespace is None) == (name is None)
        self.DB = db
        self.FID = fid or uuid.uuid4().hex
        self.Namespace = namespace
        self.Name = name
        self.Metadata = metadata
        
    def __str__(self):
        return "[DBFile %s %s:%s]" % (self.FID, self.Namespace, self.Name)
        
    __repr__ = __str__

    def save(self):
        c = self.DB.cursor()
        c.execute("""
            insert 
                into files(id, namespace, name) 
                values(%s, %s, %s)
                on conflict(id) 
                    do update set namespace=%s, name=%s;
            commit""",
            (self.FID, self.Namespace, self.Name, self.Namespace, self.Name))
        return self
                
    def save_metadata(self, metadata):
        attr_tuples = []
        for aname, avalue in metadata.items():
            tup = [None]*8
            if isinstance(avalue, bool):
                tup[3] = avalue
            elif isinstance(avalue, int):
                tup[0] = avalue
            elif isinstance(avalue, float):
                tup[1] = avalue
            elif isinstance(avalue, str):
                tup[2] = avalue
            elif isinstance(avalue, (tuple, list)):
                avalue = list(avalue)
                if len(avalue) > 0:
                    x = avalue[0]
                    if isinstance(x, bool):
                        tup[7] = avalue
                    elif isinstance(x, int):
                        tup[4] = avalue
                    elif isinstance(x, float):
                        tup[5] = avalue
                    elif isinstance(x, str):
                        tup[6] = avalue
            else:
                raise ValueError("Unknown value type %s for attribute %s" % (type(avalue), aname))
            attr_tuples.append([self.FID, aname] + tup)

        c = self.DB.cursor()
        c.execute("begin")
        try:
            c.execute("delete from file_attributes where file_id=%s", (self.FID,))
            #print("attr tuples:", attr_tuples)
            c.executemany("""insert into file_attributes(file_id, name,
                int_value, float_value, string_value, bool_value, 
                int_array, float_array, string_array, bool_array)
                values(%s, %s, 
                    %s, %s, %s, %s,     %s, %s, %s, %s)""",
                attr_tuples)
            c.execute("commit")
            self.Metadata = metadata
        except:
            c.execute("rollback")
            raise
        return self
            
    @staticmethod
    def get(db, fid = None, namespace = None, name = None, with_metadata = False):
        assert (fid is not None) != (namespace is not None or name is not None), "Can not specify both FID and namespace.name"
        assert (namespace is None) == (name is None)
        c = db.cursor()
        if fid is not None:
            c.execute("""select namespace, name from files
                    where id = %s""", (fid,))
            namespace, name = c.fetchone()
        else:
            c.execute("""select fid 
                    from files
                    where namespace = %s and name=%s""", (namespace, name))
            (fid,) = c.fetchone()
        f = DBFile(db, fid=fid, namespace=namespace, name=name)
        if with_metadata:
            return f.with_metadata()
        else:
            return f
        
    def fetch_metadata(self):
        meta = {}
        c = self.DB.cursor()
        c.execute("""
            select name,
                    int_value, float_value, string_value, bool_value, 
                    int_array, float_array, string_array, bool_array
                from file_attributes
                where file_id=%s""", (self.FID,))
        for tup in fetch_generator(c):
            name = tup[0]
            values = tup[1:]
            meta[name] = first_non_empty(values)
        #print("meta:", meta)
        return meta
        
    def with_metadata(self):
        if self.Metadata is None:
            self.Metadata = self.fetch_metadata()
        return self
    
    def metadata(self):
        if self.Metadata is None:
            self.Metadata = self.fetch_metadata()
        return self.Metadata
        
    @staticmethod
    def list(db, namespace=None):
        c = db.cursor()
        if namespace is None:
            c.execute("""select fid, namespace, name from files""")
        else:
            c.execute("""select fid, namespace, name from files
                where namespace=%s""", (namespace,))
        return DBFileSet.from_shallow(self.DB, fetch_generator(c))
        
    def has_attribute(self, attrname):
        return attrname in self.Metadata
        
    def get_attribute(self, attrname, default=None):
        return self.Metadata.get(attrname, default)

    def to_jsonable(self, with_metadata = False):
        data = dict(
            fid = self.FID,
            namespace = self.Namespace,
            name = self.Name
        )
        if with_metadata:
            data["metadata"] = self.metadata()
        return data

    def to_json(self, with_metadata = False):
        return json.dumps(self.to_jsonable(with_metadata=with_metadata))
        
class DBDataset(object):

    def __init__(self, db, namespace, name, parent_namespace=None, parent_name=None):
        assert namespace is not None and name is not None
        assert (parent_namespace is None) == (parent_name == None)
        self.DB = db
        self.Namespace = namespace
        self.Name = name
        self.ParentNamespace = parent_namespace
        self.ParentName = parent_name
        
    def save(self):
        self.DB.cursor().execute("""
            insert into datasets(namespace, name, parent_namespace, parent_name) values(%s, %s, %s, %s)
                on conflict(namespace, name) 
                    do update set parent_namespace=%s, parent_name=%s;
            commit""",
            (self.Namespace, self.Name, self.ParentNamespace, self.ParentName, self.ParentNamespace, self.ParentName))
        return self
            
    def add_file(self, f):
        assert isinstance(f, DBFile)
        self.DB.cursor().execute("""
            insert into files_datasets(file_id, dataset_namespace, dataset_name) values(%s, %s, %s)
                on conflict do nothing;
            commit""",
            (f.FID, self.Namespace, self.Name))
        return self
        
    @staticmethod
    def get(db, namespace, name):
        c = db.cursor()
        #print(namespace, name)
        c.execute("""select parent_namespace, parent_name
                        from datasets
                        where namespace=%s and name=%s""",
                (namespace, name))
        parent_namespace, parent_name = c.fetchone()
        return DBDataset(db, namespace, name, parent_namespace, parent_name)
        
    @staticmethod
    def list(db, namespace=None, parent_namespace=None, parent_name=None):
        wheres = []
        if namespace is not None:
            wheres.append("namespace = '%s'" % (namespace,))
        if parent_namespace is not None:
            wheres.append("parent_namespace = '%s'" % (parent_namespace,))
        if parent_name is not None:
            wheres.append("parent_name = '%s'" % (parent_name,))
        wheres = "" if not wheres else "where " + " and ".join(wheres)
        c=db.cursor()
        c.execute("""select namespace, name, parent_namespace, parent_name
                from datasets %s""" % (wheres,))
        return (DBDataset(db, namespace, name, parent_namespace, parent_name) for
                namespace, name, parent_namespace, parent_name in fetch_generator(c))


    def list_files(self, recursive=False, with_metadata = False, condition=None, relationship="self"):
        # relationship is ignored for now
        c = self.DB.cursor()
        if with_metadata:
                if condition:
                        c.execute(f"""select files.id, files.namespace, files.name, 
                                                a.name,
                                                a.int_array, a.float_array, a.string_array, a.bool_array,
                                                a.int_value, a.float_value, a.string_value, a.bool_value
                                        from files, file_attributes a
                                        where a.file_id = files.id
                                            and files.id in (
                                                select distinct f.id as fid
                                                        from files f, files_datasets fd, file_attributes attr
                                                        where f.id = fd.file_id
                                                                and fd.dataset_namespace=%s and fd.dataset_name=%s
                                                                and f.id = attr.file_id
                                                                and ({condition})
                                            )
                                        order by files.id""",
                                (self.Namespace, self.Name))
                else:
                        c.execute("""select f.id, f.namespace, f.name, 
                                                a.name,
                                                a.int_array, a.float_array, a.string_array, a.bool_array,
                                                a.int_value, a.float_value, a.string_value, a.bool_value
                                        from files f, file_attributes a, files_datasets fd
                                        where a.file_id = f.id
                                                and f.id = fd.file_id
                                                and fd.dataset_namespace=%s and fd.dataset_name=%s
                                        order by f.id
                                        """,
                                (self.Namespace, self.Name))
                return DBFileSet.from_metadata_tuples(self.DB, fetch_generator(c))
        else:
                if condition:
                        c.execute(f"""select files.id, files.namespace, files.name 
                                        from files
                                        where files.id in (
                                                select distinct f.id as fid
                                                        from files f, files_datasets fd, file_attributes attr
                                                        where f.id = fd.file_id
                                                                and fd.dataset_namespace=%s and fd.dataset_name=%s
                                                                and f.id = attr.file_id
                                                                and ({condition})
                                            )
                                        """,
                                (self.Namespace, self.Name))
                else:
                        c.execute("""select f.id, f.namespace, f.name 
                                        from files f, files_datasets fd
                                        where f.id = fd.file_id
                                                and fd.dataset_namespace=%s and fd.dataset_name=%s
                                        """,
                                (self.Namespace, self.Name))
                return DBFileSet.from_shallow(self.DB, fetch_generator(c))


    @property
    def nfiles(self):
        c = self.DB.cursor()
        c.execute("""select count(*) 
                        from files_datasets 
                        where dataset_namespace=%s and dataset_name=%s""", (self.Namespace, self.Name))
        return c.fetchone()[0]     
    
    def to_jsonable(self):
        return dict(
            namespace = self.Namespace,
            name = self.Name,
            parent_namespace = self.ParentNamespace,
            parent_name = self.ParentName
        )
    
    def to_json(self):
        return json.dumps(self.to_jsonable())
        

        
class DBNamedQuery(object):

    def __init__(self, db, namespace, name, source, code):
        assert namespace is not None and name is not None
        self.DB = db
        self.Namespace = namespace
        self.Name = name
        self.Source = source
        self.Code = code
        
    def save(self):
        self.DB.cursor().execute("""
            insert into queries(namespace, name, source, code) values(%s, %s, %s, %s)
                on conflict(namespace, name) 
                    do update set source=%s, code=%s;
            commit""",
            (self.Namespace, self.Name, self.Source, self.Code, self.Source, self.Code))
        return self
            
    @staticmethod
    def get(db, namespace, name):
        c = db.cursor()
        #print(namespace, name)
        c.execute("""select source, code
                        from queries
                        where namespace=%s and name=%s""",
                (namespace, name))
        (source, code) = c.fetchone()
        return DBNamedQuery(db, namespace, name, source, code)
        
    @staticmethod
    def list(db, namespace=None):
        c = db.cursor()
        if namespace is not None:
            c.execute("""select namespace, name, query
                        from queries
                        where namespace=%s""",
                (namespace,)
            )
        else:
            c.execute("""select namespace, name, query
                        from queries"""
            )
        return (DBNamedQuery(db, namespace, name, text) for namespace, name, text in fetch_generator(c))
        

        
        
    
