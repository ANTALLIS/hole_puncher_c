#!/usr/bin/env python3
"""
Simple P2P Chat with Manual Connection
Uses pystun3 command line and no signaling server
"""

import socket
import threading
import time
import sys
import os
import subprocess
import json
from datetime import datetime

class SimpleP2PChat:
    def __init__(self, port=8888):
        self.port = port
        self.peer_addr = None
        self.connected = False
        self.running = True
        self.sock = None
        self.public_ip = None
        self.public_port = None
        self.local_ip = self.get_local_ip()
        
        print("=== SIMPLE P2P CHAT ===")
        print(f"Starting on port {port}...")
    
    def get_local_ip(self):
        """Get local IP address"""
        try:
            # Create a socket to get local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except:
            return "127.0.0.1"
    
    def run_pystun_command(self):
        """Run pystun3 command line to get public IP"""
        print("\n[STUN] Getting public IP from pystun3...")
        
        try:
            # Try different ways pystun3 might be installed
            commands = [
                ["python3", "-m", "pystun3"],
                ["pystun3"],
                ["python", "-m", "pystun3"]
            ]
            
            for cmd in commands:
                try:
                    print(f"  Trying: {' '.join(cmd)}")
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    if result.returncode == 0:
                        output = result.stdout
                        print(f"  Output:\n{output}")
                        
                        # Parse output to find IP and port
                        lines = output.split('\n')
                        for line in lines:
                            if "NAT Type:" in line:
                                nat_type = line.split(":")[1].strip()
                                print(f"  NAT Type: {nat_type}")
                            if "External IP:" in line:
                                self.public_ip = line.split(":")[1].strip()
                            if "External Port:" in line:
                                try:
                                    self.public_port = int(line.split(":")[1].strip())
                                except:
                                    pass
                        
                        if self.public_ip and self.public_port:
                            print(f"  Found: {self.public_ip}:{self.public_port}")
                            return True
                            
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    continue
            
            # If pystun3 fails, use local IP
            print("  [Warning] pystun3 not found or failed")
            print("  Using local IP instead")
            self.public_ip = self.local_ip
            self.public_port = self.port
            return True
            
        except Exception as e:
            print(f"  [Error] {e}")
            self.public_ip = self.local_ip
            self.public_port = self.port
            return False
    
    def create_socket(self):
        """Create UDP socket"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Bind to port
            self.sock.bind(("0.0.0.0", self.port))
            
            # Get actual port (in case we bound to 0)
            actual_port = self.sock.getsockname()[1]
            if actual_port != self.port:
                print(f"[Socket] Bound to port {actual_port} (requested {self.port})")
                self.port = actual_port
                if self.public_port == self.port:
                    self.public_port = actual_port
            
            print(f"[Socket] Created on port {self.port}")
            return True
            
        except Exception as e:
            print(f"[Socket] Error: {e}")
            return False
    
    def receive_messages(self):
        """Thread to receive messages"""
        print("[Receive] Thread started")
        
        while self.running:
            try:
                # Use select with timeout to avoid blocking
                ready, _, _ = select.select([self.sock], [], [], 1.0)
                
                if ready:
                    data, addr = self.sock.recvfrom(1024)
                    
                    if data == b"PUNCH":
                        print(f"\n=== CONNECTION ESTABLISHED! ===")
                        print(f"Received PUNCH from {addr[0]}:{addr[1]}")
                        
                        self.peer_addr = addr
                        self.connected = True
                        
                        # Send acknowledgment
                        self.sock.sendto(b"PUNCH_ACK", addr)
                        print("Sent acknowledgment")
                        print("You can now chat!\n")
                        print("You: ", end="", flush=True)
                        
                    elif data == b"PUNCH_ACK":
                        print(f"\n=== PEER ACKNOWLEDGED! ===")
                        print(f"Direct connection with {addr[0]}:{addr[1]}")
                        
                        self.peer_addr = addr
                        self.connected = True
                        print("You can now chat!\n")
                        print("You: ", end="", flush=True)
                        
                    elif data == b"PING":
                        # Respond to ping
                        self.sock.sendto(b"PONG", addr)
                        
                    elif data == b"PONG":
                        print(f"\n[Info] Got PONG from {addr[0]}:{addr[1]}")
                        print("Basic connectivity confirmed")
                        print("You: ", end="", flush=True)
                        
                    else:
                        # Regular message
                        try:
                            message = data.decode('utf-8')
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            print(f"\n[{timestamp}] Peer: {message}")
                            print("You: ", end="", flush=True)
                        except:
                            pass
                            
            except BlockingIOError:
                pass
            except ValueError:
                # select error when socket is closed
                if self.running:
                    pass
            except Exception as e:
                if self.running:
                    print(f"[Receive] Error: {e}")
    
    def test_connectivity(self, ip, port):
        """Test if we can reach a peer"""
        print(f"\n[Test] Testing connectivity to {ip}:{port}...")
        
        try:
            # Send PING
            self.sock.sendto(b"PING", (ip, port))
            print("  Sent PING")
            
            # Wait for PONG with timeout
            start_time = time.time()
            while time.time() - start_time < 3:
                ready, _, _ = select.select([self.sock], [], [], 0.1)
                if ready:
                    data, addr = self.sock.recvfrom(1024)
                    if data == b"PONG" and addr[0] == ip and addr[1] == port:
                        print(f"  Got PONG from {ip}:{port}")
                        return True
                        
            print("  No response (firewall may be blocking UDP)")
            return False
            
        except Exception as e:
            print(f"  Error: {e}")
            return False
    
    def hole_punch(self, ip, port):
        """Perform hole punching to a peer"""
        print(f"\n=== HOLE PUNCHING to {ip}:{port} ===")
        print("Make sure the other peer is also punching to you!")
        
        # First test connectivity
        if not self.test_connectivity(ip, port):
            print("[Warning] Basic connectivity test failed")
            print("Continue anyway? (y/n): ", end="", flush=True)
            response = input().strip().lower()
            if response != 'y':
                return
        
        # Send multiple punch packets
        punch_msg = b"PUNCH"
        for i in range(1000):
            try:
                self.sock.sendto(punch_msg, (ip, port))
                print(f"  Punch {i+1} sent to {ip}:{port}")
            except Exception as e:
                print(f"  Error sending punch {i+1}: {e}")
            
            time.sleep(0.01)  # 500ms between punches
        
        print("\n=== Punching complete ===")
        print("Waiting for peer response...")
        print("If successful, you'll see 'CONNECTION ESTABLISHED!'")
    
    def send_message(self, message):
        """Send message to peer"""
        if not self.connected or not self.peer_addr:
            print("Not connected to any peer!")
            return False
        
        try:
            self.sock.sendto(message.encode('utf-8'), self.peer_addr)
            return True
        except Exception as e:
            print(f"[Send] Error: {e}")
            return False
    
    def chat_loop(self):
        """Main chat interface"""
        print("\n=== CHAT INTERFACE ===")
        print("Commands:")
        print("  connect [ip] [port]  - Connect to a peer")
        print("  myinfo               - Show your IP and port")
        print("  test [ip] [port]     - Test connectivity")
        print("  status               - Show connection status")
        print("  help                 - Show this help")
        print("  quit                 - Exit")
        print()
        
        # Show our info
        print(f"Your local IP: {self.local_ip}")
        print(f"Your port: {self.port}")
        if self.public_ip and self.public_ip != self.local_ip:
            print(f"Your public IP: {self.public_ip}")
        print()
        
        # Start receive thread
        recv_thread = threading.Thread(target=self.receive_messages, daemon=True)
        recv_thread.start()
        
        # Main command loop
        while self.running:
            try:
                print("Command: ", end="", flush=True)
                cmd = input().strip()
                
                if not cmd:
                    continue
                
                if cmd == "quit":
                    self.running = False
                    print("Exiting...")
                
                elif cmd.startswith("connect "):
                    parts = cmd.split()
                    if len(parts) == 3:
                        ip = parts[1]
                        try:
                            port = int(parts[2])
                            self.hole_punch(ip, port)
                        except ValueError:
                            print("Error: Port must be a number")
                    else:
                        print("Usage: connect [ip] [port]")
                        print("Example: connect 192.168.1.100 8889")
                
                elif cmd.startswith("test "):
                    parts = cmd.split()
                    if len(parts) == 3:
                        ip = parts[1]
                        try:
                            port = int(parts[2])
                            self.test_connectivity(ip, port)
                        except ValueError:
                            print("Error: Port must be a number")
                    else:
                        print("Usage: test [ip] [port]")
                
                elif cmd == "myinfo":
                    print(f"\n=== YOUR INFO ===")
                    print(f"Local IP: {self.local_ip}")
                    print(f"Port: {self.port}")
                    if self.public_ip:
                        print(f"Public IP: {self.public_ip}")
                        print(f"Public Port: {self.public_port}")
                    
                    # Get more network info
                    try:
                        import netifaces
                        print("\nNetwork Interfaces:")
                        for iface in netifaces.interfaces():
                            addrs = netifaces.ifaddresses(iface)
                            if netifaces.AF_INET in addrs:
                                for addr in addrs[netifaces.AF_INET]:
                                    if 'addr' in addr and addr['addr'] != '127.0.0.1':
                                        print(f"  {iface}: {addr['addr']}")
                    except:
                        pass
                    print()
                
                elif cmd == "status":
                    print(f"\n=== STATUS ===")
                    print(f"Connected: {self.connected}")
                    print(f"Socket: {'Open' if self.sock else 'Closed'}")
                    
                    if self.peer_addr:
                        print(f"Peer: {self.peer_addr[0]}:{self.peer_addr[1]}")
                    else:
                        print("Peer: Not connected")
                    
                    if self.sock:
                        try:
                            local_addr = self.sock.getsockname()
                            print(f"Socket bound to: {local_addr[0]}:{local_addr[1]}")
                        except:
                            pass
                    print()
                
                elif cmd == "help":
                    print("\nCommands:")
                    print("  connect [ip] [port]  - Connect to a peer")
                    print("  myinfo               - Show your IP and port")
                    print("  test [ip] [port]     - Test connectivity")
                    print("  status               - Show connection status")
                    print("  help                 - Show this help")
                    print("  quit                 - Exit")
                    print("\nAfter connecting, just type messages (no command needed)")
                    print()
                
                else:
                    # If connected, treat as message
                    if self.connected:
                        self.send_message(cmd)
                    else:
                        print("Not connected to peer. Use 'connect' first.")
                        print("Type 'help' for commands.")
            
            except KeyboardInterrupt:
                print("\nInterrupted, exiting...")
                self.running = False
            except EOFError:
                print("\nEOF, exiting...")
                self.running = False
            except Exception as e:
                print(f"\nError: {e}")
    
    def run(self):
        """Main run method"""
        try:
            # Get public IP using pystun3 command line
            self.run_pystun_command()
            
            # Create socket
            if not self.create_socket():
                return False
            
            # Start chat
            self.chat_loop()
            
            return True
            
        except Exception as e:
            print(f"[Error] {e}")
            return False
        finally:
            # Cleanup
            self.running = False
            if self.sock:
                self.sock.close()
            print("\n[Cleanup] Done")

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Simple P2P Chat")
    parser.add_argument("-p", "--port", type=int, default=8888,
                       help="Local port (default: 8888)")
    
    args = parser.parse_args()
    
    # Create and run chat
    chat = SimpleP2PChat(port=args.port)
    chat.run()

# Monkey-patch select module if needed
try:
    import select
except ImportError:
    # Simple select emulation for platforms that don't have it
    import sys
    import time
    
    class SimpleSelect:
        @staticmethod
        def select(rlist, wlist, xlist, timeout=None):
            # Just check if socket has data (non-blocking check)
            if timeout == 0:
                time.sleep(0.001)
            
            result_rlist = []
            for sock in rlist:
                try:
                    # Try to peek at data
                    data = sock.recv(1, socket.MSG_PEEK)
                    if data:
                        result_rlist.append(sock)
                except BlockingIOError:
                    pass
                except:
                    pass
            
            return result_rlist, [], []
    
    sys.modules['select'] = SimpleSelect()
    import select

if __name__ == "__main__":
    main()

