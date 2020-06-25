import sys, getopt, os, json, fnmatch
from urllib.parse import quote_plus, unquote_plus
from metacat.util import to_bytes, to_str
from token_lib import TokenLib
import requests

Usage = """
Usage: 
    metacat namespce <command> [<options>] ...
    
    Commands and options:
    
        list [<options>] [<namespace pattern>]
            -v -- verbose
            
        create [<options>] <name>
            -o <role> -- owner role
        
        show <name>
"""

def do_list(config, server_url, tl, args):
    opts, args = getopt.getopt(args, "v", ["--verbose"])
    
    pattern = None if not args else args[0]
    
    opts = dict(opts)
    verbose = "-v" in opts or "--verbose" in opts
    response = requests.get(server_url + "/data/namespaces")
    output = json.loads(response.text)
    for item in output:
        name = item["name"]
        if pattern is None or fnmatch.fnmatch(name, pattern):
            print("%s\towner:%s" % (name, item["owner"]))
                
    
def do_show(config, server_url, tl, args):
    response = requests.get(server_url + "/data/namespace?name=%s" % (args[0],))
    output = json.loads(response.text)
    print(output)
    
def do_create(config, server_url, tl, args):
    opts, args = getopt.getopt(args, "o:", ["--owner="])
    opts = dict(opts)
    
    name = args[0]
    
    token = tl.get(server_url)
    if not token:
        print("No valid token found. Please obtain new token")
        sys.exit(1)
        
    request = Request(url, headers={"X-Authentication-Token": token.encode()})
    response = urlopen(request)
    output = json.loads(response.read())
    print(output)
    
def do_dataset(config, server_url, args):
    if not args:
        print(Usage)
        sys.exit(2)
        
    command = args[0]
    tl = TokenLib()
    return {
        "list":     do_list,
        "create":   do_create,
        "show":     do_show
    }[command](config, server_url, tl, args[1:])
    
    
 
