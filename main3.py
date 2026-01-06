import socket
import struct
import random
import threading
import sys

def get_stun_mapping(sock, stun_host='stun.l.google.com', stun_port=19302):
    """Manually finds the public port using a STUN Binding Request."""
    transaction_id = bytes(random.getrandbits(8) for _ in range(12))
    packet = struct.pack("!HH I 12s", 0x0001, 0x0000, 0x2112A442, transaction_id)
    sock.sendto(packet, (stun_host, stun_port))
    sock.settimeout(2.0)
    try:
        data, addr = sock.recvfrom(1024)
        port_offset = data.find(b'\x00\x20') + 4
        if port_offset > 3:
            raw_port = struct.unpack("!H", data[port_offset+2:port_offset+4])[0]
            return raw_port ^ 0x2112
    except:
        return None

def listen_loop(sock):
    """Background thread to handle incoming messages."""
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            message = data.decode('utf-8')
            # Clear current line and print message
            sys.stdout.write(f"\r\033[K[Peer]: {message}\n> ")
            sys.stdout.flush()
        except:
            break

def run_chat():
    # Setup Socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', 0)) # Let OS pick a free local port
    
    # 1. Discovery
    ext_port = get_stun_mapping(sock)
    print(f"--- CHAT INITIALIZATION ---")
    print(f"Your Public Port: {ext_port}")
    print("Exchange your IP and this Port with your peer.\n")

    # 2. Peer Info
    peer_ip = input("Enter Peer IP: ")
    peer_port = int(input("Enter Peer Port: "))

    # 3. Punching
    print("\n--- PUNCHING HOLE (Please wait...) ---")
    sock.settimeout(1.0)
    connected = False
    for _ in range(5):
        sock.sendto(b"__PUNCH__", (peer_ip, peer_port))
        try:
            data, addr = sock.recvfrom(1024)
            if data == b"__PUNCH__":
                connected = True
                break
        except socket.timeout:
            continue

    if connected:
        print("✅ CONNECTION ESTABLISHED! You can now chat.")
    else:
        print("⚠️ Punching finished (blind mode). Trying to chat anyway...")

    # 4. Start Chat Threads
    sock.settimeout(None) # Disable timeout for the chat
    listener = threading.Thread(target=listen_loop, args=(sock,), daemon=True)
    listener.start()

    print("Type your message and hit Enter. Type 'exit' to quit.\n")
    while True:
        msg = input("> ")
        if msg.lower() == 'exit':
            break
        sock.sendto(msg.encode('utf-8'), (peer_ip, peer_port))

if __name__ == "__main__":
    try:
        run_chat()
    except KeyboardInterrupt:
        print("\nChat closed.")
        sys.exit()

