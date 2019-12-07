import uuid, json
from psycopg2 import IntegrityError

class AlreadyExistsError(Exception):
    pass

class NotFoundError(Exception):
    def __init__(self, msg):
        self.Message = msg

    def __str__(self):
        return "Not found error: %s" % (self.Message,)

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
                    if an is not None:              # this will happen if outer join is used
                        f.Metadata[an] = v     
            if f is not None:
                    yield f
        return DBFileSet(db, gather_meta(g))
        
    def __iter__(self):
        return self.Files
            
    def parents(self, with_metadata = False):
        return self._relationship("parents", with_metadata)
            
    def children(self, with_metadata = False):
        return self._relationship("children", with_metadata)
            
    def _relationship(self, rel, with_metadata):
        if rel == "children":
            join = "f.id = pc.child_id and pc.parent_id = any (%s)"
        else:
            join = "f.id = pc.parent_id and pc.child_id = any (%s)"
            
        c = self.DB.cursor()
        file_ids = list(f.FID for f in self.Files)
        if with_metadata:
            sql = f"""select distinct f.id, f.namespace, f.name, 
                                a.name,
                                a.int_array, a.float_array, a.string_array, a.bool_array,
                                a.int_value, a.float_value, a.string_value, a.bool_value
                        from files f left outer join file_attributes a on (a.file_id = f.id), 
                            parent_child pc
                        where {join}
                        order by f.id
                        """
            c.execute(sql, (file_ids,))
            #print("__relationship: sql:", c.query)
            return DBFileSet.from_metadata_tuples(self.DB, fetch_generator(c))
        else:
            sql = f"""select distinct f.id, f.namespace, f.name 
                        from files f, parent_child pc
                        where 
                                {join}
                        """
            c.execute(sql, (file_ids,))
            return DBFileSet.from_shallow(self.DB, fetch_generator(c))

    @staticmethod
    def join(db, file_sets):
        first = file_sets[0]
        if len(file_sets) == 1:
            return DBFileSet(db, first)
        file_list = list(first)
        file_ids = set(f.FID for f in file_list)
        for another in file_sets[1:]:
            another_ids = set(f.FID for f in another)
            file_ids &= another_ids
        return DBFileSet(db, (f for f in file_list if f.FID in file_ids))

    @staticmethod
    def union(db, file_sets):
        first = file_sets[0]
        if len(file_sets) == 1:
            return DBFileSet(db, first)
        def union_generator(file_lists):
            file_ids = set()
            for lst in file_lists:
                for f in lst:
                    if not f.FID in file_ids:
                        file_ids.add(f.FID)
                        yield f
        return DBFileSet(db, union_generator(file_sets))

    def subtract(self, right):
        right_ids = set(f.FID for f in right)
        return (f for f in self if not f.FID in right_ids)
        
    __sub__ = subtract

            
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
        try:
            c.execute("""
                insert 
                    into files(id, namespace, name) 
                    values(%s, %s, %s)
                    on conflict(id) 
                        do update set namespace=%s, name=%s;
                commit""",
                (self.FID, self.Namespace, self.Name, self.Namespace, self.Name))
        except IntegrityError:
            c.execute("rollback")
            raise AlreadyExistsError("%s:%s" % (self.Namespace, self.Name))
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
            c.execute("""select id 
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
            meta[name] = first_not_empty(values)
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
        
    def children(self, with_metadata = False):
        return DBFileSet(self.DB, [self]).children(with_metadata)
        
    def parents(self, with_metadata = False):
        return DBFileSet(self.DB, [self]).parents(with_metadata)
        
    def add_child(self, child):
        child_fid = child if isinstance(child, str) else child.FID
        c = self.DB.cursor()
        c.execute("""
            insert into parent_child(parent_id, child_id)
                values(%s, %s)        
                on conflict(parent_id, child_id) do nothing;
            commit""", (self.FID, child_fid)
        )
        
    def remove_child(self, child):
        child_fid = child if isinstance(child, str) else child.FID
        c = self.DB.cursor()
        c.execute("""
            delete from parent_child where
                parent_id = %s and child_id = %s;
            commit""", (self.FID, child_fid)
        )

    def add_parent(self, parent):
        parent_fid = parent if isinstance(parent, str) else parent.FID
        return DBFile(self.DB, fid=parent_fid).add_child(self)
        
    def remove_parent(self, parent):
        parent_fid = parent if isinstance(parent, str) else parent.FID
        return DBFile(self.DB, fid=parent_fid).remove_child(self)
    
        
        
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
        tup = c.fetchone()
        parent_namespace, parent_name = None, None
        if tup is not None:
            parent_namespace, parent_name = tup
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
                                        from files left outer join file_attributes a on (a.file_id = files.id)
                                        where files.id in (
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
                                        from files f left outer join file_attributes a on (a.file_id = f.id), 
                                            files_datasets fd
                                        where 
                                                f.id = fd.file_id
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

    def __init__(self, db, namespace, name, source, parameters=[]):
        assert namespace is not None and name is not None
        self.DB = db
        self.Namespace = namespace
        self.Name = name
        self.Source = source
        self.Parameters = parameters
        
    def save(self):
        self.DB.cursor().execute("""
            insert into queries(namespace, name, source, parameters) values(%s, %s, %s, %s)
                on conflict(namespace, name) 
                    do update set source=%s, parameters=%s;
            commit""",
            (self.Namespace, self.Name, self.Source, self.Parameters, self.Source, self.Parameters))
        return self
            
    @staticmethod
    def get(db, namespace, name):
        c = db.cursor()
        #print(namespace, name)
        c.execute("""select source, parameters
                        from queries
                        where namespace=%s and name=%s""",
                (namespace, name))
        (source, params) = c.fetchone()
        return DBNamedQuery(db, namespace, name, source, params)
        
    @staticmethod
    def list(db, namespace=None):
        c = db.cursor()
        if namespace is not None:
            c.execute("""select namespace, name, source, parameters
                        from queries
                        where namespace=%s""",
                (namespace,)
            )
        else:
            c.execute("""select namespace, name, source, parameters
                        from queries"""
            )
        return (DBNamedQuery(db, namespace, name, source, parameters) 
                    for namespace, name, source, parameters in fetch_generator(c)
        )
        

        
        
    
