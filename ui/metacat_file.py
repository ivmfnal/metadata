import sys, getopt, os, json, pprint, time
from metacat.util import to_bytes, to_str, TokenLib
from metacat.webapi import MetaCatClient

Usage = """
Show file info:

    show <options> <namespace>:<name>
    show <options> -i <file id>
        -m|--meta-only  - metadata only
        -j|--json       - as JSON
        -p|--pretty     - pretty-print information
    
Declare new files:

    declare <options> <json file> <dataset>
            -N|--namespace <default namespace>         - default namespace for files and dataset
    declare --sample                                   - print JSON file sample
    
Update file metadata:

    update <options> <json file>
           -N|--namespace <default namespace>           - default namespace for files
    update --sample                                     - print JSON file sample

Add file(s) to dataset:

    add -n|--names <file namespace>:<file name>[,...] <dataset namespace>:<dataset name>
    add -n|--names @<file with file names> <dataset namespace>:<dataset name>
        file must contain one <namespace>:<name> per line
    add -i|--ids <file id>[,...] <dataset namespace>:<dataset name>
    add -i|--ids @<file with file ids> <dataset namespace>:<dataset name>
        file must contain one <file id> per line
    add -j|--json <json file> <dataset namespace>:<dataset name>
    add --sample                                        - print sample JSON file
        -N|--namespace <default namespace>              - default namespace for files and dataset
"""


_declare_smaple = [
    {        
        "namespace":"test",
        "name":"file1.dat",
        "metadata": {
            "pi": 3.14,
            "version":"1.0",
            "format":"raw",
            "done":True
        },
        "parents":[ "4722545", "43954" ]
    },
    {        
        "namespace":"test",
        "name":"file2.dat",
        "metadata": {
            "e": 2.718,
            "version":"1.0",
            "format":"raw",
            "done":False
        },
        "parents":[ "4723345", "4322954" ]
    }
]


def do_declare(config, client, args):
    opts, args = getopt.getopt(args, "N:", ["namespace=", "sample"])
    opts = dict(opts)

    if "--sample" in opts:
        print(json.dumps(_declare_smaple, sort_keys=True, indent=4, separators=(',', ': ')))
        sys.exit(0)
    
    if not args or args[0] == "help":
        print(Usage)
        sys.exit(2)
    
    file_list = json.load(open(args[0], "r"))       # parse to validate JSON
    
    resonse = client.declare_files(args[1], file_list, namespace = namespace)    
    print(response)
                


def do_show(config, client, args):
    opts, args = getopt.getopt(args, "jmpi:", ["json","meta-only","pretty"])
    opts = dict(opts)
    
    if not args:
        if not "-i" in opts:
            print(Usage)
            sys.exit(2)
    else:
        if "-i" in opts:
            print(Usage)
            sys.exit(2)
            

    #print("opts:", opts,"    args:", args)
    
    meta_only = "--meta-only" in opts or "-m" in opts
    as_json = "--json" in opts or "-j" in opts
    pretty = "-p" in opts or "--pretty" in opts
    
    name = fid = None
    
    if args:
        name = args[0]
    else:
        fid = opts["-i"]

    data = client.get_file(name=name, fid=fid)
    
    if meta_only:
        data = data.get("metadata", {})
    if pretty:
        pprint.pprint(data)
    elif as_json:
        print(json.dumps(data))
    else:
        for k, v in sorted(data.items()):
            print("%s:\t%s" % (k, v))

_update_smaple = [
    {        
        "name":"test:file1.dat",
        "metadata": {
            "pi": 3.14,
            "version":"1.0",
            "format":"raw",
            "done":True
        },
        "parents":[ "4722545", "43954" ]
    },
    {        
        "name":"test:file1.dat",
        "metadata": {
            "pi": 3.14,
            "version":"1.0",
            "format":"raw",
            "done":True
        },
        "parents":[ "4722545", "43954" ]
    },
    {        
        "fid":"54634",
        "metadata": {
            "q": 2.8718,
            "version":"1.1",
            "format":"processed",
            "params": [1,2],
            "done":False
        }
    }
]

def do_update(config, client, args):
    opts, args = getopt.getopt(args, "N:", ["namespace=", "sample"])
    opts = dict(opts)

    if "--sample" in opts:
        print(json.dumps(_update_smaple, sort_keys=True, indent=4, separators=(',', ': ')))
        sys.exit(0)
    
    if not args or args[0] == "help":
        print(Usage)
        sys.exit(2)
    
    data = json.load(open(args[0], "r"))       # parse to validate JSON
    
    namespace = opts.get("-N") or opts.get("--namespace")
    response = client.update_files(data)
    print(response)

_add_smaple = [
    {        
        "name":"test:file1.dat"
    },
    {        
        "name":"test:file1.dat"
    },
    {        
        "fid":"54634"
    }
]

def do_add(config, client, args):
    opts, args = getopt.getopt(args, "i:j:n:N:", ["namespace=", "json=", "names=", "ids=", "sample"])
    opts = dict(opts)

    if "--sample" in opts:
        print(json.dumps(_add_smaple, sort_keys=True, indent=4, separators=(',', ': ')))
        sys.exit(0)

    if not args or args[0] == "help":
        print(Usage)
        sys.exit(2)
    
    file_list = []

    if "-j" in opts or "--json" in opts:
        file_list = json.load(open(opts.get("-f") or opts.get("--files"), "r"))
    
    elif "-i" in opts or "--ids" in opts:
        val = opts.get("-i") or opts.get("--ids")
        if val.startswith("@"):
            file_ids = open(val[1:], "r").readlines()
            file_ids = [fid.strip() for fid in file_ids]
        else:
            file_ids = val.split(",")
        file_list = [{"fid":fid} for fid in file_ids if fid]
    
    else:
        val = opts.get("-n") or opts.get("--names")
        if val.startswith("@"):
            file_names = open(val[1:], "r").readlines()
            file_names = [fid.strip() for fid in file_names]
        else:
            file_names = val.split(",")
        file_list = [{"name":name} for name in file_names]        

    dataset = args[-1]
    namespace = opts.get("-N") or opts.get("--namespace")
    out = client.add_files(dataset, file_list, namespace=namespace)
    print(out)



def do_file(config, server_url, args):
    if not args:
        print(Usage)
        sys.exit(2)
        
    command = args[0]
    client = MetaCatClient(server_url)
    return {
        "declare":      do_declare,
        "add":          do_add,
        "update":       do_update,
        "show":         do_show
    }[command](config, client, args[1:])
