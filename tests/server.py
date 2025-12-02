import muxp
from muxp import Signature, JSONCodec, Mode


address = ('0.0.0.0', 8443)
auth = muxp.Auth(
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
        muxp.run(address, echo_handler, mode=Mode.THREADPOOL, auth=None)
    except KeyboardInterrupt:
        print("[*] 服务中断退出")
    except Exception as e:
        print(f"[*] 服务启动异常: {e}")
