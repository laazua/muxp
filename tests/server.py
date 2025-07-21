from muxp.comm import Auth
from muxp.comm import JSONCodec
from muxp.api import run_server
from muxp.comm.security import Signature


address = ('0.0.0.0', 8443)
auth = Auth(
    cafile="certs/ssl/ca.crt",
    keyfile="certs/ssl/client.key",
    certfile="certs/ssl/client.crt")


def echo_handler(data: bytes) -> bytes:
    """
    业务逻辑在这里处理
    """
    # data为接收到的数据,先解密，后解码
    sig_key = "xabc"  # 数据加密签名key
    decrypt_data = Signature.decrypt(data, sig_key)
    decoder_data = JSONCodec.decode(decrypt_data)
    print("收到:", decoder_data)

    # 返回给客户端的数据
    return data


if __name__ == '__main__':
    try:
        run_server(address, auth, echo_handler)
    except KeyboardInterrupt:
        print("[*] 服务中断退出")
    except Exception as e:
        print("[*] 服务启动异常")
