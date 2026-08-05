import time
import random
import json
import os

def gerar_pacote_simulado(contador):
    return {
        "cubesat_id": 1,
        "contador": contador,
        "tensao_bateria": round(random.uniform(3.60, 3.85), 2),
        "temperatura": round(random.uniform(18.0, 32.5), 1),
        "rssi": random.randint(-95, -60),
        "snr": round(random.uniform(5.0, 12.0), 1),
        "validos": contador,
        "invalidos": random.randint(0, 2)
    }

if __name__ == "__main__":
    print("--- Gerador de Telemetria Iniciado ---")
    contador = 1
    os.makedirs("data", exist_ok=True)
    
    while True:
        dados = gerar_pacote_simulado(contador)
        # Salva os dados para o Flask ler
        with open("data/telemetria_recente.json", "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=4)
            
        print(f"[DADO ENVIADO AO SERVIDOR] Pacote #{contador} -> V: {dados['tensao_bateria']}V | T: {dados['temperatura']}°C")
        contador += 1
        time.sleep(2)