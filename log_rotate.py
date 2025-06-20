#!/usr/bin/env python3
"""
Script para rotação de logs do sistema txt2sql_claude.
Mantém os arquivos de log com tamanho controlado.
"""
import os
import time
import shutil
from datetime import datetime

LOG_FILE = 'txt2sql_errors.log'
MAX_SIZE_MB = 5000  # Tamanho máximo em MB
BACKUP_COUNT = 5  # Número de backups a manter

def get_file_size_mb(filename):
    """Retorna o tamanho do arquivo em MB"""
    return os.path.getsize(filename) / (1024 * 1024)

def rotate_log():
    """Rotaciona o arquivo de log se ele exceder o tamanho máximo"""
    if not os.path.exists(LOG_FILE):
        # Criar arquivo vazio se não existir
        open(LOG_FILE, 'a').close()
        return

    file_size = get_file_size_mb(LOG_FILE)

    if file_size > MAX_SIZE_MB:
        print(f"Rotacionando arquivo de log ({file_size:.2f} MB)")

        # Remover backup mais antigo se necessário
        oldest_backup = f"{LOG_FILE}.{BACKUP_COUNT}"
        if os.path.exists(oldest_backup):
            os.remove(oldest_backup)

        # Mover os arquivos de backup existentes
        for i in range(BACKUP_COUNT - 1, 0, -1):
            old_name = f"{LOG_FILE}.{i}"
            new_name = f"{LOG_FILE}.{i + 1}"
            if os.path.exists(old_name):
                shutil.move(old_name, new_name)

        # Renomear o arquivo atual para backup.1
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_name = f"{LOG_FILE}.1"
        shutil.copy2(LOG_FILE, backup_name)

        # Limpar o arquivo atual
        open(LOG_FILE, 'w').close()

        print(f"Log rotacionado em {timestamp}. Arquivo limpo.")
    else:
        print(f"Tamanho do log: {file_size:.2f} MB (não requer rotação)")

if __name__ == "__main__":
    rotate_log()
