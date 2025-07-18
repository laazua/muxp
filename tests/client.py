import sys

from muxp.comm import Auth
from muxp.comm import JSONCodec
from muxp.api import MuxpClient


address = ('127.0.0.1', 8443)
auth = Auth()
auth.cafile = "certs/ssl/ca.crt"
auth.keyfile = "certs/ssl/client.key"
auth.certfile = "certs/ssl/client.crt"

if __name__ == '__main__':
    client = MuxpClient(
        address,
        auth,
    )

    message = {'id': sys.argv[1], 'address': '成都'}
    client.send(JSONCodec.encode(message))

    #client.send(b"hello muxp")
    # response: b"xxxx"
    response = client.recv()
    print(f"[Client] 服务端响应: {JSONCodec.decode(response)}")
    client.close()
