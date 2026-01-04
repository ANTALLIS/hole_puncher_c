// p2p_test.c - Cross-platform P2P connection tester
// Works on Linux and macOS

#include <arpa/inet.h>
#include <netdb.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define BUFFER_SIZE 1024
#define STUN_TIMEOUT 5

// STUN constants
#define STUN_BINDING_REQUEST 0x0001
#define STUN_BINDING_RESPONSE 0x0101
#define XOR_MAPPED_ADDRESS 0x0020
#define MAGIC_COOKIE 0x2112A442

typedef struct {
  char ip[64];
  int port;
} AddressInfo;

// Create STUN binding request
void create_stun_request(unsigned char *buffer) {
  // Message type (Binding Request)
  buffer[0] = (STUN_BINDING_REQUEST >> 8) & 0xFF;
  buffer[1] = STUN_BINDING_REQUEST & 0xFF;

  // Message length (0 for no attributes)
  buffer[2] = 0;
  buffer[3] = 0;

  // Magic cookie
  buffer[4] = (MAGIC_COOKIE >> 24) & 0xFF;
  buffer[5] = (MAGIC_COOKIE >> 16) & 0xFF;
  buffer[6] = (MAGIC_COOKIE >> 8) & 0xFF;
  buffer[7] = MAGIC_COOKIE & 0xFF;

  // Transaction ID (12 random bytes)
  srand(time(NULL));
  for (int i = 8; i < 20; i++) {
    buffer[i] = rand() % 256;
  }
}

// Parse STUN response to extract public IP and port
int parse_stun_response(unsigned char *data, int len, AddressInfo *addr) {
  if (len < 20)
    return 0;

  // Check message type
  unsigned short msg_type = (data[0] << 8) | data[1];
  if (msg_type != STUN_BINDING_RESPONSE)
    return 0;

  int offset = 20; // Skip header

  while (offset + 4 <= len) {
    unsigned short attr_type = (data[offset] << 8) | data[offset + 1];
    unsigned short attr_length = (data[offset + 2] << 8) | data[offset + 3];
    offset += 4;

    if (offset + attr_length > len)
      break;

    // XOR-MAPPED-ADDRESS
    if (attr_type == XOR_MAPPED_ADDRESS && attr_length >= 8) {
      unsigned char family = data[offset + 1];

      if (family == 0x01) { // IPv4
        unsigned short xor_port = (data[offset + 2] << 8) | data[offset + 3];
        unsigned int xor_addr = (data[offset + 4] << 24) |
                                (data[offset + 5] << 16) |
                                (data[offset + 6] << 8) | data[offset + 7];

        // XOR with magic cookie
        addr->port = xor_port ^ 0x2112;
        xor_addr ^= MAGIC_COOKIE;

        sprintf(addr->ip, "%d.%d.%d.%d", (xor_addr >> 24) & 0xFF,
                (xor_addr >> 16) & 0xFF, (xor_addr >> 8) & 0xFF,
                xor_addr & 0xFF);

        return 1;
      }
    }

    offset += attr_length;
    // Padding to 4-byte boundary
    offset += (4 - (attr_length % 4)) % 4;
  }

  return 0;
}

// Query STUN server to discover public IP
int discover_public_address(int sock, AddressInfo *addr) {
  const char *stun_servers[] = {"stun.l.google.com", "stun1.l.google.com",
                                "stun2.l.google.com", "stun.stunprotocol.org"};
  int stun_ports[] = {19302, 19302, 19302, 3478};
  int num_servers = 4;

  unsigned char request[20];
  unsigned char response[BUFFER_SIZE];

  for (int i = 0; i < num_servers; i++) {
    printf("Trying STUN server: %s:%d\n", stun_servers[i], stun_ports[i]);

    struct hostent *he = gethostbyname(stun_servers[i]);
    if (!he) {
      printf("  Failed to resolve hostname\n");
      continue;
    }

    struct sockaddr_in stun_addr;
    memset(&stun_addr, 0, sizeof(stun_addr));
    stun_addr.sin_family = AF_INET;
    stun_addr.sin_port = htons(stun_ports[i]);
    memcpy(&stun_addr.sin_addr, he->h_addr_list[0], he->h_length);

    // Send STUN request
    create_stun_request(request);
    sendto(sock, request, 20, 0, (struct sockaddr *)&stun_addr,
           sizeof(stun_addr));

    // Wait for response
    struct timeval tv;
    tv.tv_sec = STUN_TIMEOUT;
    tv.tv_usec = 0;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    struct sockaddr_in recv_addr;
    socklen_t addr_len = sizeof(recv_addr);
    int n = recvfrom(sock, response, BUFFER_SIZE, 0,
                     (struct sockaddr *)&recv_addr, &addr_len);

    if (n > 0 && parse_stun_response(response, n, addr)) {
      printf("  ✓ Success! Public address: %s:%d\n\n", addr->ip, addr->port);
      return 1;
    }

    printf("  Failed, trying next server...\n");
  }

  return 0;
}

// Send hole-punching packets
void punch_holes(int sock, const char *peer_ip, int peer_port) {
  struct sockaddr_in peer_addr;
  memset(&peer_addr, 0, sizeof(peer_addr));
  peer_addr.sin_family = AF_INET;
  peer_addr.sin_port = htons(peer_port);
  inet_pton(AF_INET, peer_ip, &peer_addr.sin_addr);

  printf("Sending hole-punch packets to %s:%d...\n", peer_ip, peer_port);

  char punch_msg[32];
  sprintf(punch_msg, "PUNCH:%d", getpid());

  for (int i = 0; i < 30; i++) {
    sendto(sock, punch_msg, strlen(punch_msg), 0, (struct sockaddr *)&peer_addr,
           sizeof(peer_addr));
    usleep(100000); // 100ms between packets

    if (i % 5 == 0) {
      printf("  Sent %d punch packets...\n", i + 1);
    }
  }

  printf("Hole punching complete!\n\n");
}

// Test connection by sending/receiving messages
void test_connection(int sock, const char *peer_ip, int peer_port) {
  struct sockaddr_in peer_addr;
  memset(&peer_addr, 0, sizeof(peer_addr));
  peer_addr.sin_family = AF_INET;
  peer_addr.sin_port = htons(peer_port);
  inet_pton(AF_INET, peer_ip, &peer_addr.sin_addr);

  printf("=== Connection Test ===\n");
  printf("Type messages to send (or 'quit' to exit)\n\n");

  // Set socket to non-blocking
  struct timeval tv;
  tv.tv_sec = 0;
  tv.tv_usec = 100000; // 100ms timeout
  setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

  char send_buffer[BUFFER_SIZE];
  char recv_buffer[BUFFER_SIZE];

  while (1) {
    // Check for incoming messages
    struct sockaddr_in from_addr;
    socklen_t from_len = sizeof(from_addr);
    int n = recvfrom(sock, recv_buffer, BUFFER_SIZE - 1, 0,
                     (struct sockaddr *)&from_addr, &from_len);

    if (n > 0) {
      recv_buffer[n] = '\0';

      // Skip punch packets
      if (strncmp(recv_buffer, "PUNCH:", 6) != 0) {
        char from_ip[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &from_addr.sin_addr, from_ip, INET_ADDRSTRLEN);
        printf("\n[%s:%d]: %s\n> ", from_ip, ntohs(from_addr.sin_port),
               recv_buffer);
        fflush(stdout);
      }
    }

    // Check for user input (non-blocking)
    fd_set readfds;
    FD_ZERO(&readfds);
    FD_SET(STDIN_FILENO, &readfds);

    struct timeval timeout;
    timeout.tv_sec = 0;
    timeout.tv_usec = 0;

    if (select(STDIN_FILENO + 1, &readfds, NULL, NULL, &timeout) > 0) {
      if (fgets(send_buffer, BUFFER_SIZE, stdin)) {
        // Remove newline
        send_buffer[strcspn(send_buffer, "\n")] = 0;

        if (strcmp(send_buffer, "quit") == 0) {
          printf("Exiting...\n");
          break;
        }

        if (strlen(send_buffer) > 0) {
          sendto(sock, send_buffer, strlen(send_buffer), 0,
                 (struct sockaddr *)&peer_addr, sizeof(peer_addr));
          printf("Sent: %s\n> ", send_buffer);
          fflush(stdout);
        }
      }
    }

    usleep(10000); // 10ms to prevent CPU spinning
  }
}

int main(int argc, char *argv[]) {
  printf("=== P2P Connection Tester ===\n\n");

  // Create UDP socket
  int sock = socket(AF_INET, SOCK_DGRAM, 0);
  if (sock < 0) {
    perror("Socket creation failed");
    return 1;
  }

  // Bind to any available port
  struct sockaddr_in local_addr;
  memset(&local_addr, 0, sizeof(local_addr));
  local_addr.sin_family = AF_INET;
  local_addr.sin_addr.s_addr = INADDR_ANY;
  local_addr.sin_port = 0; // Let OS choose port

  if (bind(sock, (struct sockaddr *)&local_addr, sizeof(local_addr)) < 0) {
    perror("Bind failed");
    return 1;
  }

  // Get local port
  socklen_t addr_len = sizeof(local_addr);
  getsockname(sock, (struct sockaddr *)&local_addr, &addr_len);
  int local_port = ntohs(local_addr.sin_port);

  printf("Local socket bound to port: %d\n\n", local_port);

  // Discover public address via STUN
  AddressInfo public_addr;
  printf("Discovering public address via STUN...\n");

  if (!discover_public_address(sock, &public_addr)) {
    printf("Failed to discover public address!\n");
    printf("Make sure you have internet connection.\n");
    close(sock);
    return 1;
  }

  printf("╔════════════════════════════════════════╗\n");
  printf("║   YOUR CONNECTION INFO                 ║\n");
  printf("╠════════════════════════════════════════╣\n");
  printf("║   Share this with your peer:           ║\n");
  printf("║                                        ║\n");
  printf("║   %s:%-6d                    ║\n", public_addr.ip,
         public_addr.port);
  printf("║                                        ║\n");
  printf("╚════════════════════════════════════════╝\n\n");

  // Get peer's address
  char peer_ip[64];
  int peer_port;

  printf("Enter peer's IP address: ");
  fflush(stdout);
  if (!fgets(peer_ip, sizeof(peer_ip), stdin)) {
    printf("Failed to read input\n");
    close(sock);
    return 1;
  }
  peer_ip[strcspn(peer_ip, "\n")] = 0;

  printf("Enter peer's port: ");
  fflush(stdout);
  if (scanf("%d", &peer_port) != 1) {
    printf("Invalid port\n");
    close(sock);
    return 1;
  }

  // Clear input buffer
  while (getchar() != '\n')
    ;

  printf("\nConnecting to %s:%d\n\n", peer_ip, peer_port);

  // Punch holes
  punch_holes(sock, peer_ip, peer_port);

  printf("Connection established! Both peers should now be able to "
         "communicate.\n\n");

  // Test connection
  test_connection(sock, peer_ip, peer_port);

  close(sock);
  return 0;
}
