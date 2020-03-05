import sys, getopt, os, json, fnmatch
from urllib.request import urlopen, Request
from urllib.parse import quote_plus, unquote_plus
from py3 import to_bytes, to_str
from token_lib import TokenLib

Usage = """
Usage: 
    metacat [-c <config file>] dataset <command> [<options>] ...
    
    Commands and options:
    
        list [<options>] [[<namespace pattern>:]<name pattern>]
            -v|--verbose
            
        create [<options>] <namespace>:<name>
            -p|--parent <parent namespace>:<parent name>
        
        show [<options>] <namespace>:<name>
"""

def do_list(config, tl, args):
    opts, args = getopt.getopt(args, "v", ["--verbose"])
    if args:
        patterns = args
    else:
        patterns = ["*"]
    opts = dict(opts)
    verbose = "-v" in opts or "--verbose" in opts
    server_url = config["Server"]["URL"]
    response = urlopen(server_url + "/data/datasets?with_file_counts=%s" % ("yes" if verbose else "no"))
    output = json.loads(response.read())
    for item in output:
        match = False
        for p in patterns:
            pns = None
            if ":" in p:
                pns, pn = p.split(":", 1)
            else:
                pn = p
            namespace, name = item["namespace"], item["name"]
            if fnmatch.fnmatch(name, pn) and (pns is None or fnmatch.fnmatch(namespace, pns)):
                match = True
                break
        if match:
            print("%s:%s" % (namespace, name))
            if verbose:
                print("    Parent:     %s:%s" % (item.get("parent_namespace") or "", item.get("parent_name") or ""))
                print("    File count: %d" % (item["file_count"],))
                    
                
    
def do_show(config, tl, args):
    server_url = config["Server"]["URL"]
    response = urlopen(server_url + "/data/dataset?dataset=%s" % (args[0],))
    output = json.loads(response.read())
    print(output)
    
def do_create(config, tl, args):
    opts, args = getopt.getopt(args, "p:", ["--parent="])
    opts = dict(opts)
    
    dataset_spec = args[0]
    
    parent_spec = opts.get("-p") or opts.get("--parent")
    server_url = config["Server"]["URL"]
    url = server_url + "/data/create_dataset?dataset=%s" % (dataset_spec,)
    if parent_spec:
        url += "&parent=%s" % (parent_spec,)
    
    token = tl.get(server_url)
    if not token:
        print("No valid token found. Please obtain new token")
        sys.exit(1)
        
    request = Request(url, headers={"X-Authentication-Token": token})
    response = urlopen(request)
    output = json.loads(response.read())
    print(output)
    
def do_dataset(config, args):
    command = args[0]
    tl = TokenLib()
    return {
        "list":     do_list,
        "create":   do_create,
        "show":     do_show
    }[command](config, tl, args[1:])
    
    
 
