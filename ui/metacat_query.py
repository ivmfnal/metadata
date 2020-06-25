import sys, getopt, os, json, pprint
from urllib.request import urlopen, Request
from urllib.parse import quote_plus, unquote_plus
from metacat.util import to_bytes, to_str

import requests


Usage = """
Usage: 
    metacat query <options> "<MQL query>"
    metacat query <options> -f <MQL query file>

    Options:
        -j|--json                           - print raw JSON output
        -p|--pretty                         - pretty-print metadata
        -i|--ids                            - print file ids instead of names
        -s|--summary                        - print only summary information
        -m|--metadata=[<field>,...]         - print metadata fields
                                              overrides --summary
        -m|--metadata=all                   - print all metadata fields
                                              overrides --summary
        -n|--namespace=<default namespace>  - default namespace for the query
"""

def do_query(config, server_url, args):
    opts, args = getopt.getopt(args, "jism:n:pf:", ["json", "ids","summary","metadata=","namespace=","pretty"])
    opts = dict(opts)

    #print("opts:", opts,"    args:", args)
    
    url = server_url + "/data/query"
    params = []
    namespace = opts.get("-n") or opts.get("--namespace")
    if namespace:
        params.append("namespace=%s" % (namespace,))
    with_meta = not "--summary" in opts and not "-s" in opts
    with_meta = with_meta or "-m" in opts or "--metadata" in opts
    keys = opts.get("-m") or opts.get("--metadata") or []
    if keys and keys != "all":    keys = keys.split(",")
    params.append("with_meta=%s" % ("yes" if with_meta else "no"))
    if params:
        url += "?" + "&".join(params)

    #print("url:", url)

    if args:
        query_text = args[0]
    else:
        query_file = opts.get("-f")
        if not query_file:
            print(Usage)
            sys.exit(2)
        query_text = to_str(open(query_file, "r").read())

    #print("query_text: %s" % (query_text,))
    response = requests.get(url, data=to_bytes(query_text))
    #print(response)
    
    status = response.status_code
    if status/100 != 2:
        print("Error: ", status, "\n", response.text)
        sys.exit(1)

    body = response.text

    if "--json" in opts or "-j" in opts:
        print(to_str(body))
        sys.exit(0)

    out = json.loads(body)
    
    if "--pretty" in opts or "-p" in opts:
        meta = sorted(out, key=lambda x: x["namespace"]+":"+x["name"])
        pprint.pprint(meta)
        sys.exit(0)

    #print("response data:", out)
    
    if "-s" in opts or "--summary" in opts and not with_meta:
        print("%d files" % (len(out),))
    else:
        for f in out:
            meta_lst = []
            meta_out = ""
            if with_meta:
                meta = f["metadata"]
                klist = sorted(list(meta.keys())) if keys == "all" else keys
                for k in klist:
                    if k in meta:
                        meta_lst.append("%s=%s" % (k, repr(meta[k])))
            if meta_lst:
                meta_out = "\t"+"\t".join(meta_lst)
            if "--ids" in opts or "-i" in opts:
                print("%s%s" % (f["fid"],meta_out))
            else:
                print("%s:%s%s" % (f["namespace"],f["name"],meta_out))
        
                
    
    
    
