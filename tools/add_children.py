import psycopg2, sys, getopt
from dbobjects import DBDataset, DBFile, AlreadyExistsError

connstr = sys.argv[1]

conn = psycopg2.connect(connstr)

namespace = "test"

files_A = DBDataset(conn, namespace, "A").list_files()
files_B = DBDataset(conn, namespace, "B").list_files()

j = 0

for i, f in enumerate(files_A):
    n = i%4
    for _ in range(n):
        c = DBFile(conn, namespace, "c%03d.dat" % (j,))
        try:    c.save()
        except AlreadyExistsError:  pass
        j += 1
        f.add_child(c)
    print("children of %s: %s" % (f, list(f.children())))
    
j = 0
for i, f in enumerate(files_B):
    n = i%4
    for _ in range(n):
        p = DBFile(conn, namespace, "p%03d.dat" % (j,))
        try:    p.save()
        except AlreadyExistsError:  pass
        j += 1
        f.add_parent(p)
    print("parents of %s: %s" % (f, list(f.parents())))
    
