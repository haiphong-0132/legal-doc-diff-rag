import argparse
import threading
import time
import uvicorn
from pycloudflared import try_cloudflare

# Import the FastAPI app and settings from the original host.py to avoid code duplication
from host import app, HOST, PORT, DEVICE


def run_tunnel(port: int) -> None:
    # Chờ 3 giây để FastAPI khởi động và nạp xong model trước khi mở Tunnel
    time.sleep(3)
    print("\n[CLOUDFLARE] Khởi tạo đường truyền Tunnel tới cổng local...", port)
    try:
        tunnel = try_cloudflare(port=port)
        public_url = tunnel.tunnel
        
        print("\n" + "═" * 70)
        print("🎉 CLOUDFLARE TUNNEL ĐÃ SẴN SÀNG CHIA SẺ API!")
        print(f"🔗 Public URL:  \033[96m\033[1m{public_url}\033[0m")
        print("  " + "─" * 66)
        print("👉 Hướng dẫn gọi API từ xa:")
        print(f"  • Embed:    POST  \033[92m{public_url}/embed\033[0m")
        print(f"  • Generate: POST  \033[92m{public_url}/generate\033[0m")
        print(f"  • Rerank:   POST  \033[92m{public_url}/rerank\033[0m")
        print(f"  • OpenAPI:  GET   \033[92m{public_url}/docs\033[0m")
        print("═" * 70 + "\n")
    except Exception as e:
        print(f"\n[CLOUDFLARE] ❌ Lỗi khi khởi động Cloudflare Tunnel: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local NLP FastAPI service with Cloudflare Tunnel")
    parser.add_argument("--host", default=HOST, help="IP Address to bind the server")
    parser.add_argument("--port", type=int, default=PORT, help="Port to run the local server")
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn auto-reload")
    args = parser.parse_args()

    # Khởi chạy Cloudflare Tunnel dưới dạng luồng chạy ngầm (background daemon thread)
    tunnel_thread = threading.Thread(target=run_tunnel, args=(args.port,), daemon=True)
    tunnel_thread.start()

    print(f"[START] Đang khởi chạy FastAPI server tại {args.host}:{args.port}")
    
    # Sử dụng "host:app" để hỗ trợ tính năng auto-reload khi code thay đổi
    if args.reload:
        uvicorn.run("host:app", host=args.host, port=args.port, reload=True)
    else:
        uvicorn.run(app, host=args.host, port=args.port)
