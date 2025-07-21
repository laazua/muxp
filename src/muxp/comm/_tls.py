import ssl
from dataclasses import dataclass


@dataclass
class Auth:
    certfile: str
    keyfile: str
    cafile: str


def ssl_server_context(auth: Auth):
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_cert_chain(auth.certfile, auth.keyfile)
    context.load_verify_locations(auth.cafile)
    return context


def ssl_client_context(auth: Auth):
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.load_cert_chain(auth.certfile, auth.keyfile)
    context.load_verify_locations(auth.cafile)
    return context
