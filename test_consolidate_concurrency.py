#!/usr/bin/env python3
"""Test de concurrencia real para FileLock + atomic_write_note."""
import multiprocessing
import tempfile
import time
from pathlib import Path

def writer(path, content, idx):
    try:
        from consolidate import FileLock, atomic_write_note
        with FileLock(lock_path=str(Path(path).parent / ".tmp_concurrency.lock")):
            atomic_write_note(path, f"writer{idx}: {content}")
    except Exception as e:
        return str(e)
    return "ok"

if __name__ == "__main__":
    import sys
    # Skip en Windows si no hay portalocker
    try:
        import portalocker
    except ImportError:
        print("SKIP: portalocker no disponible")
        sys.exit(0)
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp:
        target = tmp.name
    # Lanzar 5 escritores concurrentes sobre la misma nota
    with multiprocessing.Pool(5) as pool:
        results = [pool.apply_async(writer, (target, "test", i)) for i in range(5)]
        outputs = [r.get(timeout=10) for r in results]
    # Verificar que ninguna salida está corrupta (no debe haber contenido interleaved)
    with open(target) as f:
        final = f.read()
    # El archivo debe contener exactamente un writer (el último que ganó)
    writer_count = final.count("writer")
    print(f"Concurrent writers: 5, final content: '{final.strip()}', writers found in final: {writer_count}")
    # Si hay más de 1 writer en el archivo, la escritura atómica falló
    assert writer_count == 1, f"Colisión detectada: {writer_count} writers en archivo final"
    print("PASS: sin colisiones")
