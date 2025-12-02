import sys
import asyncio
import muxp
from muxp import JSONCodec, Signature


address = ('127.0.0.1', 8443)
auth = muxp.Auth(
    cafile="certs/ssl/ca.crt",
    keyfile="certs/ssl/client.key",
    certfile="certs/ssl/client.crt")

def main():
    client = muxp.Client(
        address,
        auth=None,
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


async def asynmain():
    address = ("127.0.0.1", 8443)
    client = muxp.AsyncClient(address, auth=auth, timeout=300)
    
    try:
        await client.connect()
        
        # 交换的数据先编码,后加密,最后发送
        sig_key = "xabc"  # 数据加密签名key
        message = {'id': sys.argv[1], 'address': '成都', 'school': '七中'}
        
        # 编码和加密
        encoder_msg = JSONCodec.encode(message)
        encrypt_msg = Signature.encrypt(encoder_msg, sig_key)
        
        print(f"[Client] 发送消息: {message}")
        await client.send(encrypt_msg)
        
        # 等待响应，设置合理的超时时间
        print("[Client] 等待服务端响应...")
        response = await client.recv()
        
        if response is None:
            print("[Client] 接收超时或无响应")
        else:
            # 解密和解码响应
            decrypt_data = Signature.decrypt(response, sig_key)
            decoder_data = JSONCodec.decode(decrypt_data)
            print(f"[Client] 服务端响应: {decoder_data}")
    
    except Exception as e:
        print(f"[Client] 发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 确保连接被关闭
        print("[Client] 关闭连接...")
        await client.close()
        print("[Client] 连接已关闭")


if __name__ == '__main__':
    main()
    # asyncio.run(main=asynmain())

