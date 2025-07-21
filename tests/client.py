import sys

from muxp.comm import Auth
from muxp.comm import JSONCodec
from muxp.api import MuxpClient
from muxp.comm.security import Signature


address = ('127.0.0.1', 8443)
auth = Auth(
    cafile="certs/ssl/ca.crt",
    keyfile="certs/ssl/client.key",
    certfile="certs/ssl/client.crt")


if __name__ == '__main__':
    client = MuxpClient(
        address,
        auth,
    )
    # 交换的数据先编码,后加密,最后发送
    sig_key = "xabc"  # 数据加密签名key
    message = {'id': sys.argv[1], 'address': '成都', 'school': '七中'}
    encoder_msg = JSONCodec.encode(message)
    encrypt_msg = Signature.encrypt(encoder_msg, sig_key)
    client.send(encrypt_msg)

    #client.send(b"hello muxp")
    # response: b"xxxx"
    response = client.recv()
    decrypt_data = Signature.decrypt(response, sig_key)
    decoder_data = JSONCodec.decode(decrypt_data)
    print(f"[Client] 服务端响应: {decoder_data}")
    client.close()
