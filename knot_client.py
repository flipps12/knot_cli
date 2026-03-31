
import socket
import json
import time
import threading

HOST = "127.0.0.1"
PORT = 12012

def listener():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT))
            print("Listener conectado. Esperando mensajes del daemon...\n")
            while True:
                data = s.recv(4096)
                if not data:
                    break
                msg = data.decode('utf-8').strip()
                if msg:
                    print(f"[Daemon → Cliente] {msg}")
    except:
        pass

# Iniciar listener en segundo plano
threading.Thread(target=listener, daemon=True).start()

time.sleep(0.5)

print("=== Knot Client - Solo newchannel (por ahora) ===\n")

for i in range(3):
    print(f"[{i+1}] Enviando newchannel...")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT))
            cmd = {"command": "newchannel", "value": f"127.0.0.1:{5000 + i}"}
            s.sendall(json.dumps(cmd).encode('utf-8') + b"\n")
            resp = s.recv(1024).decode('utf-8').strip()
            print("Respuesta:", resp)
    except Exception as e:
        print("Error:", e)
    
    time.sleep(2)

print("\nDejá corriendo un rato y mirá los logs del daemon.")
input("Presiona Enter para salir...")
