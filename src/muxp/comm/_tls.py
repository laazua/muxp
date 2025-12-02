import ssl
from dataclasses import dataclass
from typing import Optional

@dataclass
class Auth:
    certfile: str
    keyfile: str
    cafile: str

def ssl_server_context(auth: Optional[Auth]):
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.verify_mode = ssl.CERT_REQUIRED if auth else ssl.CERT_NONE
    if auth:
        context.load_cert_chain(auth.certfile, auth.keyfile)
        context.load_verify_locations(auth.cafile)
    return context

def ssl_client_context(auth: Optional[Auth]):
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    if auth:
        context.load_cert_chain(auth.certfile, auth.keyfile)
        context.load_verify_locations(auth.cafile)
    return context
