import sys, getopt, os, json, pickle, time
from urllib.request import urlopen, Request
from urllib.parse import quote_plus, unquote_plus
from py3 import to_bytes, to_str
from signed_token import SignedToken, SignedTokenExpiredError, SignedTokenImmatureError
from token_lib import TokenLib
from requests.auth import HTTPDigestAuth
import getpass, requests

Usage = """
Usage: 
    metacat [-c <config file>] login [-m <mechanism>] <username>
    metacat [-c <config file>] login -l
    metacat [-c <config file>] login -v

    Mechanisms: password, x509 (not implemented yet)
"""

def do_auth(config, args):

    server_url = config["Server"]["URL"]

    tl = TokenLib()

    opts, args = getopt.getopt(args, "m:u:lv")
    opts = dict(opts)

    if "-l" in opts:
        for url, token in tl.items():
                token = SignedToken.decode(token)
                print("%s %s %s %s" % (url, token.Payload["user"], time.ctime(token.Expiration), token.TID))
        sys.exit(0)

    if "-v" in opts:
        token = to_str(tl.get(server_url))
        #print("token:", repr(token))
        if not token:
                print("No token found for server %s" % (server_url,))
                sys.exit(1)
        url = server_url + "/auth/verify"
        response = requests.get(url, headers={
                "X-Authentication-Token":token
        })
        if response.status_code/100 == 2:
                print ("OK")
                sys.exit(0)
        else:
                print (response.text)
                sys.exit(1)

        
        
    url = server_url + "/auth/auth"
    username = args[0]

    password = getpass.getpass("Password:")

    response = requests.get(url, auth=HTTPDigestAuth(username, password))
    if response.status_code != 200:
        print(response.text)
    token = response.headers["X-Authentication-Token"]
    tl[server_url] = token
