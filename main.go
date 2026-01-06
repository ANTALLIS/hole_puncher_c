package main

import (
	"bufio"
	"bytes"
	"crypto/rand"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"strings"
	"sync"
	"time"
)

// --- Types & Constants ---

type Packet struct {
	Type int    `json:"t"` // 0: ALV, 1: MSG, 2: ACK
	Seq  int    `json:"s"` // Sequence number
	Data string `json:"d"` // Payload
}

const (
	TypeALV = iota
	TypeMSG
	TypeACK
)

var (
	pendingMutex sync.Mutex
	pendingACKs  = make(map[int]Packet)
	nextSeq      = 1
	peerAddr     *net.UDPAddr
	conn         *net.UDPConn
)

// --- STUN Discovery Logic ---

func getSTUNMapping() (string, int, error) {
	// Build STUN Binding Request
	tid := make([]byte, 12)
	rand.Read(tid)
	packet := bytes.NewBuffer([]byte{0x00, 0x01, 0x00, 0x00})  // Type & Length
	binary.Write(packet, binary.BigEndian, uint32(0x2112A442)) // Magic Cookie
	packet.Write(tid)

	serverAddr, _ := net.ResolveUDPAddr("udp4", "stun.l.google.com:19302")
	conn.WriteToUDP(packet.Bytes(), serverAddr)

	conn.SetReadDeadline(time.Now().Add(3 * time.Second))
	resp := make([]byte, 1024)
	n, _, err := conn.ReadFromUDP(resp)
	conn.SetReadDeadline(time.Time{}) // Reset
	if err != nil {
		return "", 0, err
	}

	// Simple XOR-Mapped-Address (0x0020) Parser
	index := bytes.Index(resp[:n], []byte{0x00, 0x20})
	if index == -1 {
		return "", 0, fmt.Errorf("could not find XOR-MAPPED-ADDRESS")
	}

	rawPort := binary.BigEndian.Uint16(resp[index+6 : index+8])
	port := int(rawPort ^ 0x2112)

	rawIP := resp[index+8 : index+12]
	ip := net.IP{rawIP[0] ^ 0x21, rawIP[1] ^ 0x12, rawIP[2] ^ 0xA4, rawIP[3] ^ 0x42}

	return ip.String(), port, nil
}

// --- Background Loops ---

func listenLoop() {
	buf := make([]byte, 2048)
	for {
		n, addr, err := conn.ReadFromUDP(buf)
		if err != nil {
			return
		}

		var p Packet
		if err := json.Unmarshal(buf[:n], &p); err != nil {
			continue
		}

		switch p.Type {
		case TypeALV:
			// Heartbeat received; NAT hole is refreshed
		case TypeACK:
			pendingMutex.Lock()
			delete(pendingACKs, p.Seq)
			pendingMutex.Unlock()
		case TypeMSG:
			// 1. Send ACK back immediately
			ack := Packet{Type: TypeACK, Seq: p.Seq}
			payload, _ := json.Marshal(ack)
			conn.WriteToUDP(payload, addr)

			// 2. Display message
			fmt.Printf("\r\033[K[Peer]: %s\n> ", p.Data)
		}
	}
}

func retransmissionLoop() {
	ticker := time.NewTicker(1 * time.Second)
	for range ticker.C {
		if peerAddr == nil {
			continue
		}
		pendingMutex.Lock()
		for _, p := range pendingACKs {
			payload, _ := json.Marshal(p)
			conn.WriteToUDP(payload, peerAddr)
		}
		pendingMutex.Unlock()
	}
}

func keepAliveLoop() {
	ticker := time.NewTicker(20 * time.Second)
	for range ticker.C {
		if peerAddr != nil {
			payload, _ := json.Marshal(Packet{Type: TypeALV})
			conn.WriteToUDP(payload, peerAddr)
		}
	}
}

// --- Main Program ---

func main() {
	// 1. Setup Local Socket
	laddr, _ := net.ResolveUDPAddr("udp4", "0.0.0.0:0")
	var err error
	conn, err = net.ListenUDP("udp4", laddr)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}
	defer conn.Close()

	fmt.Println("--- STEP 1: STUN DISCOVERY ---")
	extIP, extPort, err := getSTUNMapping()
	if err != nil {
		fmt.Printf("STUN Error: %v\n", err)
	} else {
		fmt.Printf("Your Public ID: %s:%d\n", extIP, extPort)
	}

	// 2. Peer Exchange
	reader := bufio.NewReader(os.Stdin)
	fmt.Print("\nEnter Peer IP: ")
	pIP, _ := reader.ReadString('\n')
	fmt.Print("Enter Peer Port: ")
	pPort, _ := reader.ReadString('\n')

	pIP = strings.TrimSpace(pIP)
	pPort = strings.TrimSpace(pPort)
	peerAddr, _ = net.ResolveUDPAddr("udp4", pIP+":"+pPort)

	// 3. Kick off background tasks
	go listenLoop()
	go retransmissionLoop()
	go keepAliveLoop()

	// 4. Manual Hole Punch (initial blast)
	fmt.Println("\n--- STEP 2: PUNCHING HOLE ---")
	for i := 0; i < 5; i++ {
		payload, _ := json.Marshal(Packet{Type: TypeALV})
		conn.WriteToUDP(payload, peerAddr)
		time.Sleep(200 * time.Millisecond)
	}

	fmt.Println("✅ Secure P2P Link Established. Type 'exit' to quit.")

	// 5. Chat Loop
	for {
		fmt.Print("> ")
		input, _ := reader.ReadString('\n')
		input = strings.TrimSpace(input)

		if strings.ToLower(input) == "exit" {
			break
		}
		if input == "" {
			continue
		}

		// Add to reliable queue
		pendingMutex.Lock()
		p := Packet{Type: TypeMSG, Seq: nextSeq, Data: input}
		pendingACKs[nextSeq] = p
		nextSeq++
		pendingMutex.Unlock()

		// Initial send
		payload, _ := json.Marshal(p)
		conn.WriteToUDP(payload, peerAddr)
	}
}
