from muxp.comm import Auth
from muxp.comm import JSONCodec
from muxp.api import run_server


address = ('0.0.0.0', 8443)
auth = Auth()
auth.cafile = "certs/ssl/ca.crt"
auth.keyfile = "certs/ssl/server.key"
auth.certfile = "certs/ssl/server.crt"


def echo_handler(data: bytes) -> bytes:
    """
    业务逻辑在这里处理
    """
    # data为接收到的数据
    print("收到:", JSONCodec.decode(data))

    # 返回给客户端的数据
    return data


if __name__ == '__main__':
    try:
        run_server(address, auth, echo_handler)
    except KeyboardInterrupt:
        print("[*] 服务中断退出")
    except Exception as e:
        print("[*] 服务启动异常")
