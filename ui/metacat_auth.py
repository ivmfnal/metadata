import sys, getopt, os, json, pickle, time
from urllib.request import urlopen, Request
from urllib.parse import quote_plus, unquote_plus
from metacat.util import to_bytes, to_str, SignedToken, SignedTokenExpiredError, SignedTokenImmatureError, TokenLib
from requests.auth import HTTPDigestAuth
import getpass, requests

Usage = """
Usage: 
    metacat auth subommands and options:
    
        login [-m <mechanism>] <username>               - request authentication token
            Only "password" mechanism is implemnted
        whoami                                          - verify token
        list                                            - list tokens
"""

def do_list(config, server_url, args):
    server_url = server_url
    tl = TokenLib()
    for url, token in tl.items():
            print("%s %s %s %s" % (token.TID, url, token["user"], time.ctime(token.Expiration)))

def do_whoami(config, server_url, args):

    server_url = server_url
    tl = TokenLib()
    token = tl.get(server_url)
    #print("token:", repr(token))
    if not token:
            print("No token found for server %s" % (server_url,))
            sys.exit(1)
    url = server_url + "/auth/verify"
    response = requests.get(url, headers={
            "X-Authentication-Token":token.encode()
    })
    if response.status_code/100 == 2:
            print ("User:   ",token["user"])
            print ("Expires:", time.ctime(token.Expiration))
    else:
            print (response.text)
            sys.exit(1)


def do_login(config, server_url, args):

    server_url = server_url

    tl = TokenLib()

    url = server_url + "/auth/auth"
    username = args[0]

    password = getpass.getpass("Password:")

    response = requests.get(url, auth=HTTPDigestAuth(username, password))
    if response.status_code != 200:
        print(response.text)
    token = response.headers["X-Authentication-Token"]
    token = SignedToken.decode(token)
    #print("Encoded token:", token)
    tl[server_url] = token
    print ("%s %s" % (token["user"], time.ctime(token.Expiration)))
    


def do_auth(config, server_url, args):
    if not args:
        print(Usage)
        sys.exit(2)
        
    command = args[0]
    return {
        "list":         do_list,
        "login":        do_login,
        "whoami":       do_whoami
    }[command](config, server_url, args[1:])

