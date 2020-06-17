import sys, getopt, os, json, pprint, time
from py3 import to_bytes, to_str
from token_lib import TokenLib

import requests


Usage = """
    metacat file subommands and options:

        show file info:
        show <options> <namespace>:<name>
        show <options> -i <file id>
            -m|--meta-only  - metadata only
            -j|--json       - as JSON
            -p|--pretty     - pretty-print information
            
        declare new files:
        declare <options> <json file> <dataset>
            declare new files
            -n|--namespace=<default namespace>              - default namespace for files and dataset
            
        update file metadata:
        update <options> <json file>
            -n|--namespace=<default namespace>              - default namespace for files

        add file(s) to dataset
        add <file namespace>:<file name> <dataset namespace>:<dataset name>
        add -i <file id> <dataset namespace>:<dataset name>
        add -f <json file> <dataset namespace>:<dataset name>
            -n|--namespace=<default namespace>              - default namespace for files and dataset
"""


def do_declare(config, server_url, args):
    opts, args = getopt.getopt(args, "n:", ["namespace="])
    opts = dict(opts)

    if not args or args[0] == "help":
        print(Usage)
        sys.exit(2)
    
    url = server_url + "/data/declare"
    metadata = json.load(open(args[0], "r"))       # parse to validate JSON
    
    params = []
    namespace = opts.get("-n") or opts.get("--namespace")
    if namespace:
        params.append("namespace=%s" % (namespace,))
    params.append("dataset=%s" % (args[1],))
    
    url += "?" + "&".join(params)

    tl = TokenLib()
    token = tl.get(server_url)
    if not token:
        print("No valid token found. Please obtain new token")
        sys.exit(1)
        
    response = requests.post(url, data=to_bytes(json.dumps(metadata)), headers={"X-Authentication-Token": token.encode()})
    
    status = response.status_code
    if status/100 != 2:
        print("Error: ", status, "\n", response.text)
        sys.exit(1)

    body = response.text
    print(body)
                


def do_show(config, server_url, args):
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
    
    url = server_url + "/data/file"
    params = []
    meta_only = "--meta-only" in opts or "-m" in opts
    as_json = "--json" in opts or "-j" in opts
    pretty = "-p" in opts or "--pretty" in opts
    
    if args:
        url += "?name=%s" % (args[0],)
    else:
        url += "?fid=%s" % (opts["-i"],)

    response = requests.get(url)
    status = response.status_code
    if status/100 != 2:
        print("Error: ", status, "\n", response.text)
        sys.exit(1)

    data = json.loads(response.text)
    
    if meta_only:
        data = data.get("metadata", {})
    if pretty:
        pprint.pprint(data)
    elif as_json:
        print(json.dumps(data))
    else:
        for k, v in sorted(data.items()):
            print("%s:\t%s" % (k, v))

def do_update(config, server_url, args):
    print ("Not implemented")

def do_add(config, server_url, args):
    print ("Not implemented")

def do_file(config, server_url, args):
    if not args:
        print(Usage)
        sys.exit(2)
        
    command = args[0]
    return {
        "declare":      do_declare,
        "add":          do_add,
        "update":       do_update,
        "show":         do_show
    }[command](config, server_url, args[1:])
