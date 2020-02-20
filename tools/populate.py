import psycopg2, sys, getopt
from dbobjects import DBDataset, DBFile

connstr = sys.argv[1]

conn = psycopg2.connect(connstr)

namespace = "test"

dataset1 = DBDataset(conn, namespace, "A").save()
dataset2 = DBDataset(conn, namespace, "B").save()
dataset3 = DBDataset(conn, namespace, "C").save()

files = [DBFile(conn, namespace, "f%s.dat" % (c,)) for c in "abcdefghijklmnopqrstuvwxyz"]
files = {f.Name:f for f in files}

for i, (fn, f) in enumerate(files.items()):
    meta = {
        "i":    i,
        "s":    fn,
        "f":    float(i*i),
        "b":    i%2 == 0
    }
    f.save()
    f.save_metadata(meta)
   
for c in "abcdefghijklmnop":
    f=files["f%s.dat" % (c,)]
    dataset1.add_file(f)
	
for c in "fghijklmnopqrstuvwxyz":
    f=files["f%s.dat" % (c,)]
    dataset2.add_file(f)
	
for c in "abcdefghijklmnopqrstuvwxyz":
    f=files["f%s.dat" % (c,)]
    dataset3.add_file(f)
