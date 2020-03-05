from py3 import to_bytes, to_str
import os
from signed_token import SignedToken, SignedTokenExpiredError, SignedTokenImmatureError

class TokenLib(object):

        DefaultFile = "%s/.metacat_tokens" % (os.environ["HOME"],)

        def __init__(self, path = None):
            self.Path = path or self.DefaultFile
            self.Tokens = self.load_tokens()

        def load_tokens(self):
            # returns dict: { url: token }
            # removes expired tokens
            token_file = self.Path
            try:        lines = open(token_file, "r").readlines()
            except:     return {}
            out = {}
            for line in lines:
                line = line.strip()
                url, encoded = line.split(None, 1)
                try:
                    token = SignedToken.decode(encoded, verify_times=True)
                except SignedTokenExpiredError:
                    token = None
                except SignedTokenImmatureError:
                    pass
                if token is not None:
                    out[url] = encoded
            return out

        def save_tokens(self):
            token_file = self.Path
            f = open(token_file, "w")
            for url, encoded  in self.Tokens.items():
                f.write("%s %s\n" % (url, encoded))
            f.close()

        def __setitem__(self, url, encoded):
                self.Tokens[url] = encoded
                self.save_tokens()

        def __getitem__(self, url):
                return self.Tokens[url]

        def get(self, url):
                return self.Tokens.get(url)

        def items(self):
                return self.Tokens.items()

