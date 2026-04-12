import socket
import json
import struct
import time
import threading
import hashlib
import base58


# --- SOPORTE PARA FLECHAS Y CURSOR ---
try:
    import readline # En Linux/macOS viene por defecto. En Windows: pip install pyreadline3
except ImportError:
    pass # Si no está, funcionará como antes sin flechas

# --- CONFIGURACIÓN ---
HOST = "127.0.0.1"
PORT_JSON = 12012
PORT_BYTES = 12812

def get_peer_id_u64(peer_input):
    try:
        decoded = base58.b58decode(peer_input)
        return struct.unpack(">Q", decoded[-8:])[0] if len(decoded) >= 8 else struct.unpack(">Q", decoded.rjust(8, b'\x00'))[0]
    except Exception:
        hasher = hashlib.sha256(peer_input.encode())
        return struct.unpack(">Q", hasher.digest()[:8])[0]

def parse_app_id(val):
    try: return int(val)
    except ValueError:
        hasher = hashlib.sha256(val.encode())
        return struct.unpack(">Q", hasher.digest()[:8])[0]

def parse_size(size_str):
    size_str = size_str.lower().strip()
    units = {"kb": 1024, "mb": 1024 * 1024, "b": 1}
    for unit, multiplier in units.items():
        if size_str.endswith(unit):
            return int(float(size_str.replace(unit, "")) * multiplier)
    return int(size_str) if size_str.isdigit() else 64

# --- LÓGICA DE CONTROL (JSON ENUMS) ---

def send_json(command, *args):
    try:
        payload = {"command": command.lower()}
        
        if command == "newappname":
            payload["name"] = args[0]
            payload["port"] = int(args[1])
        elif command == "connect":
            payload["addr"] = args[0]
        elif command == "discover":
            payload["peer_id"] = args[0]
        elif command == "connectrelay":
            # REVISIÓN: Asegúrate que estos nombres coincidan con los campos en Rust
            payload["relay_addr"] = args[0]
            payload["relay_id"] = args[1]
        elif command == "status":
            pass

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5.0) # No queremos que el CLI se cuelgue si el Daemon no responde
            s.connect((HOST, PORT_JSON))
            s.sendall(json.dumps(payload).encode() + b"\n")
            
            data = s.recv(1024).decode().strip()
            print(f"[{PORT_JSON}] In  <- {data}")
            
    except Exception as e: 
        print(f"❌ Error JSON: {e}")

# --- LÓGICA BINARIA ---

def send_bytes(peer_name, size_str, app_id_input):
    peer_id = get_peer_id_u64(peer_name)
    app_id = parse_app_id(app_id_input)
    total_size = parse_size(size_str)
    chunk_size = 65536
    sent = 0
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.connect((HOST, PORT_BYTES))
            start = time.time()
            while sent < total_size:
                current = min(chunk_size, total_size - sent)
                header = struct.pack(">BBQQIH", 1, 1, peer_id, app_id, current, 0)
                s.sendall(header + b'\x00' * current)
                sent += current
            duration = time.time() - start
            print(f"✓ {sent/1024/1024:.2f} MB enviados en {duration:.3f}s ({(sent/1024/1024)/duration:.2f} MB/s)")
    except Exception as e: print(f"❌ Error Bytes: {e}")

def start_receiver(port, mode):
    def run():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((HOST, port)); s.listen(5)
            print(f"\n[Receptor-{mode.upper()}] Activo en puerto {port}")
            while True:
                conn, _ = s.accept()
                with conn:
                    total = 0
                    while True:
                        data = conn.recv(65536)
                        if not data: break
                        total += len(data)
                    print(f"\n[Recibido @ {port}] {total/1024:.2f} KB finalizados.")
    threading.Thread(target=run, daemon=True).start()

# --- INTERFAZ ---

def show_help():
    print("\n" + "="*45)
    print("   KNOT PROTOCOL CLI - AYUDA DE COMANDOS")
    print("="*45)
    print("CONTROL (JSON):")
    print("  status                       -> Estado del Daemon")
    print("  newappname <name> <port>     -> Registrar app local")
    print("  connect <multiaddr>          -> Conexión P2P directa")
    print("  discover <peer_id>           -> Buscar en la DHT")
    print("  connectrelay <addr> <id>     -> Reservar en un Relay")
    print("\nFLUJO DE DATOS (BINARIO):")
    print("  byte <peer> <size> <app>     -> Test de velocidad")
    print("  listen <port> <alias>        -> Escuchar datos")
    print("\nSISTEMA:")
    print("  help                         -> Ver este menú")
    print("  exit                         -> Cerrar cliente")
    print("="*45)

def main():
    print("Knot Protocol Client v2.1 (Advanced CLI)")
    # El historial se guardará en memoria durante la sesión
    show_help()
    while True:
        try:
            # Ahora input() soportará flechas gracias a readline
            line = input("\nknot> ").strip().split()
            if not line: continue
            cmd = line[0].lower()
            
            if cmd == "help":
                show_help()
            elif cmd == "exit": 
                break
            elif cmd in ["status", "newappname", "connect", "discover", "connectrelay"]:
                # Verificación de argumentos mínima antes de enviar
                arg_req = {
                    "newappname": 2, "connect": 1, "discover": 1, 
                    "connectrelay": 2, "status": 0
                }
                if len(line[1:]) < arg_req[cmd]:
                    print(f"⚠️ {cmd} requiere {arg_req[cmd]} parámetros.")
                    continue
                send_json(cmd, *line[1:])
            elif cmd == "byte":
                send_bytes(line[1], line[2], line[3])
            elif cmd == "listen":
                start_receiver(int(line[1]), line[2])
            else:
                print("❌ Comando desconocido. Escribe 'help'.")
        except KeyboardInterrupt: 
            print("\nSaliendo...")
            break
        except Exception as e: 
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()