package main

import (
	"bufio"
	"bytes"
	"crypto/rand"
	"encoding/binary"
	"fmt"
	"net"
	"os"
	"strings"
	"time"
)

func getSTUNMapping(conn *net.UDPConn) (string, int, error) {
	// STUN Binding Request Header
	// Type: 0x0001, Length: 0x0000, Magic: 0x2112A442, Transaction ID: 12 bytes
	tid := make([]byte, 12)
	rand.Read(tid)
	packet := bytes.NewBuffer([]byte{0x00, 0x01, 0x00, 0x00})
	binary.Write(packet, binary.BigEndian, uint32(0x2112A442))
	packet.Write(tid)

	stunAddr, _ := net.ResolveUDPAddr("udp", "stun.l.google.com:19302")
	_, err := conn.WriteToUDP(packet.Bytes(), stunAddr)
	if err != nil {
		return "", 0, err
	}

	conn.SetReadDeadline(time.Now().Add(3 * time.Second))
	resp := make([]byte, 1024)
	n, _, err := conn.ReadFromUDP(resp)
	if err != nil {
		return "", 0, err
	}
	conn.SetReadDeadline(time.Time{}) // Reset deadline

	// Parse XOR-MAPPED-ADDRESS (Attribute 0x0020)
	index := bytes.Index(resp[:n], []byte{0x00, 0x20})
	if index == -1 {
		return "", 0, fmt.Errorf("STUN attribute not found")
	}

	// XOR Port: bits 24-28 of response
	rawPort := binary.BigEndian.Uint16(resp[index+6 : index+8])
	port := int(rawPort ^ 0x2112)

	// XOR IP: bits 28-32
	rawIP := resp[index+8 : index+12]
	ip := net.IP{
		rawIP[0] ^ 0x21,
		rawIP[1] ^ 0x12,
		rawIP[2] ^ 0xA4,
		rawIP[3] ^ 0x42,
	}

	return ip.String(), port, nil
}

func main() {
	// 1. Setup Local Socket
	laddr, _ := net.ResolveUDPAddr("udp", "0.0.0.0:0")
	conn, _ := net.ListenUDP("udp", laddr)
	defer conn.Close()

	fmt.Println("--- STEP 1: STUN DISCOVERY ---")
	extIP, extPort, err := getSTUNMapping(conn)
	if err != nil {
		fmt.Println("STUN Failed:", err)
		return
	}
	fmt.Printf("Your Public ID: %s:%d\n", extIP, extPort)

	// 2. Peer Exchange
	reader := bufio.NewReader(os.Stdin)
	fmt.Print("\nEnter Peer IP: ")
	pIP, _ := reader.ReadString('\n')
	fmt.Print("Enter Peer Port: ")
	pPortStr, _ := reader.ReadString('\n')
	pAddr, _ := net.ResolveUDPAddr("udp", strings.TrimSpace(pIP)+":"+strings.TrimSpace(pPortStr))

	// 3. Punching
	fmt.Println("\n--- STEP 2: PUNCHING ---")
	for i := 0; i < 5; i++ {
		conn.WriteToUDP([]byte("__PUNCH__"), pAddr)
		time.Sleep(200 * time.Millisecond)
	}

	// 4. Chat using Goroutine
	go func() {
		buf := make([]byte, 1024)
		for {
			n, _, err := conn.ReadFromUDP(buf)
			if err != nil {
				return
			}
			msg := string(buf[:n])
			// Silently consume keep-alive and punch signals
			if msg == "__KEEPALIVE__" {
				continue
			}
			if msg != "__PUNCH__" {
				fmt.Printf("\r\033[K[Peer]: %s\n> ", msg)
			}
		}
	}()

	// Launch this right before the Chat loop
	go func() {
		ticker := time.NewTicker(20 * time.Second)
		for range ticker.C {
			// Send an empty or "stay alive" byte
			conn.WriteTo([]byte("__KEEPALIVE__"), pAddr)
		}
	}()

	fmt.Println("✅ Connection ready. Type messages below:")
	for {
		fmt.Print("> ")
		text, _ := reader.ReadString('\n')
		text = strings.TrimSpace(text)
		if strings.ToLower(text) == "exit" {
			break
		}
		conn.WriteToUDP([]byte(text), pAddr)
	}
}
