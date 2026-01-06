import socket
import struct
import random

def get_stun_mapping(sock, stun_host='stun.l.google.com', stun_port=19302):
    """Manually sends a STUN binding request and parses the XOR-MAPPED-ADDRESS."""
    # STUN Binding Request Header
    # Type: 0x0001, Length: 0x0000, Magic: 0x2112A442, Transaction ID: 12 random bytes
    transaction_id = bytes(random.getrandbits(8) for _ in range(12))
    packet = struct.pack("!HH I 12s", 0x0001, 0x0000, 0x2112A442, transaction_id)
    
    sock.sendto(packet, (stun_host, stun_port))
    sock.settimeout(2.0)
    
    try:
        data, addr = sock.recvfrom(1024)
        # Simplified parsing for XOR-MAPPED-ADDRESS (Attribute 0x0020)
        # This looks for the port and IP in the response
        port_offset = data.find(b'\x00\x20') + 4
        if port_offset > 3:
            # XOR the port with the most significant 16 bits of the magic cookie
            raw_port = struct.unpack("!H", data[port_offset+2:port_offset+4])[0]
            external_port = raw_port ^ 0x2112
            return external_port
    except Exception as e:
        print(f"Manual STUN query failed: {e}")
    return None

def run_hole_punch():
    # 1. Setup the Socket FIRST
    # This is critical: we bind to a local port and keep it open
    local_port = 54320 
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        sock.bind(('0.0.0.0', local_port))
    except:
        # If 54320 is taken, let OS pick
        sock.bind(('0.0.0.0', 0))
        local_port = sock.getsockname()[1]

    print(f"--- STEP 1: STUN DISCOVERY (Local Port: {local_port}) ---")
    ext_port = get_stun_mapping(sock)
    
    if not ext_port:
        print("Could not get external mapping.")
        return

    # Note: This script assumes you know your public IP from your previous test
    print(f"Your External Port is likely: {ext_port}")
    
    # 2. Peer Exchange
    print("\n--- STEP 2: PEER EXCHANGE ---")
    peer_ip = input("Enter Peer Public IP: ")
    peer_port = int(input("Enter Peer Public Port: "))

    # 3. Punching Phase
    print(f"\n--- STEP 3: PUNCHING ---")
    sock.settimeout(0.5)
    
    while True:
        try:
            print(f"Sending PING to {peer_ip}:{peer_port}...")
            sock.sendto(b"PING", (peer_ip, peer_port))
            
            data, addr = sock.recvfrom(1024)
            print(f"\n🎯 SUCCESS! Received '{data.decode()}' from {addr}")
            sock.sendto(b"PONG", addr)
            break
        except socket.timeout:
            continue
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    run_hole_punch()

