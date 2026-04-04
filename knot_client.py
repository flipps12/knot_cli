import socket
import json
import struct
import time
import threading
import hashlib
import base58

# --- CONFIGURACIÓN POR DEFECTO ---
HOST = "127.0.0.1"
PORT_JSON = 12012
PORT_BYTES = 12812

def get_peer_id_u64(peer_input):
    """
    Convierte un PeerID (12D3...) o un Alias ('flipps') en u64.
    Sigue la lógica de Node.js: toma los últimos 8 bytes del multihash.
    """
    try:
        # 1. Intentamos decodificar como Base58 (PeerID de libp2p)
        decoded = base58.b58decode(peer_input)
        # Tomamos los últimos 8 bytes del buffer (Big Endian)
        if len(decoded) >= 8:
            relevant_bytes = decoded[-8:]
        else:
            # Padding si es muy corto
            relevant_bytes = decoded.rjust(8, b'\x00')
        return struct.unpack(">Q", relevant_bytes)[0]
    except Exception:
        # 2. Si no es Base58, es un Alias. Usamos SHA256 (como en Rust)
        hasher = hashlib.sha256(peer_input.encode())
        return struct.unpack(">Q", hasher.digest()[:8])[0]

def parse_app_id(val):
    """Convierte el AppID de texto/número a u64."""
    try:
        return int(val)
    except ValueError:
        # Si es un nombre de app (ej: 'video_stream'), hasheamos
        hasher = hashlib.sha256(val.encode())
        return struct.unpack(">Q", hasher.digest()[:8])[0]

def parse_size(size_str):
    """Parsea tamaños como '10mb', '1kb', '500b'."""
    size_str = size_str.lower().strip()
    units = {"kb": 1024, "mb": 1024 * 1024, "b": 1}
    for unit, multiplier in units.items():
        if size_str.endswith(unit):
            return int(float(size_str.replace(unit, "")) * multiplier)
    return int(size_str) if size_str.isdigit() else 64

def start_receiver(port, mode):
    """Hilo para escuchar datos entrantes desde el Daemon."""
    def run():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((HOST, port))
                s.listen(5)
                print(f"\n[Receptor-{mode.upper()}] Escuchando en el puerto {port}...")
                while True:
                    conn, addr = s.accept()
                    with conn:
                        start = time.time()
                        total = 0
                        while True:
                            data = conn.recv(65536)
                            if not data: break
                            total += len(data)
                        dur = time.time() - start
                        if dur > 0:
                            print(f"\n[Recibido @ {port}] {total/1024:.2f} KB a {(total/1024/1024)/dur:.2f} MB/s")
        except Exception as e: print(f"Error Receptor: {e}")
    threading.Thread(target=run, daemon=True).start()

def send_json(command, value, port_val=None):
    """Envía comandos de control al puerto JSON del Daemon."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT_JSON))
            payload = {"command": command, "value": value}
            if port_val:
                payload["port"] = int(port_val)
            
            s.sendall(json.dumps(payload).encode() + b"\n")
            print(f"[{PORT_JSON}] Enviado: {payload}")
            print(f"[{PORT_JSON}] Respuesta: {s.recv(1024).decode().strip()}")
    except Exception as e: print(f"Error JSON: {e}")

def send_bytes(peer_name, size_str, app_id_input):
    """Envía ráfagas de datos binarios al puerto de Ingress del Daemon."""
    peer_id = get_peer_id_u64(peer_name)
    app_id = parse_app_id(app_id_input)
    total_size = parse_size(size_str)
    chunk_size = 65536 # 64KB por paquete
    sent = 0
    
    print(f"[{PORT_BYTES}] Destino: {peer_name} (U64: {peer_id})")
    print(f"[{PORT_BYTES}] AppID: {app_id} | Tamaño: {total_size} bytes")
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # Optimizamos latencia (como setNoDelay en Node)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.connect((HOST, PORT_BYTES))
            
            start = time.time()
            while sent < total_size:
                current = min(chunk_size, total_size - sent)
                
                # HEADER KNOT (24 bytes total):
                # >     : Big Endian (Red)
                # B     : version (1)
                # B     : target (1 = Network)
                # Q     : peer_id (u64)
                # Q     : app_id (u64)
                # I     : payload_len (u32)
                # H     : reserved (u16)
                header = struct.pack(">BBQQIH", 1, 1, peer_id, app_id, current, 0)
                
                # Payload: Relleno de ceros (o podrías leer un archivo aquí)
                payload = b'\x00' * current
                
                s.sendall(header + payload)
                sent += current
            
            duration = time.time() - start
            print(f"✓ Éxito: {sent/1024/1024:.2f} MB enviados en {duration:.3f}s")
            if duration > 0:
                print(f"  Velocidad: {(sent/1024/1024)/duration:.2f} MB/s")
                
    except Exception as e: print(f"Error Bytes: {e}")

def main():
    print("==========================================")
    print("   KNOT CLI INTERACTIVA - CIENCIAS 2026   ")
    print("==========================================")
    print("Comandos:")
    print("  json <cmd> <val> [port]   -> Control (newappname, status)")
    print("  byte <peer> <size> <app>  -> Envío de datos binarios")
    print("  listen <port> <name>      -> Abrir receptor local")
    print("  exit                      -> Salir")

    while True:
        try:
            line = input("\nknot> ").strip().split()
            if not line: continue
            cmd = line[0].lower()
            
            if cmd == "json" and len(line) >= 3:
                p = line[3] if len(line) > 3 else None
                send_json(line[1], line[2], p)
                
            elif cmd == "byte" and len(line) >= 4:
                # byte <nombre_o_id> <tamaño> <app_o_id>
                send_bytes(line[1], line[2], line[3])
                
            elif cmd == "listen" and len(line) >= 3:
                start_receiver(int(line[1]), line[2])
                
            elif cmd == "exit": break
            else:
                print("Error: Parámetros insuficientes.")
        except KeyboardInterrupt: break
        except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    main()