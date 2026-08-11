import os
import hashlib
import json

def generate_manifest():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    files_manifest = {}
    
    # Listar todos los archivos .py en la raíz, excluyendo este generador
    for filename in os.listdir(root_dir):
        if filename.endswith('.py') and not filename.startswith('.'):
            file_path = os.path.join(root_dir, filename)
            if os.path.isfile(file_path) and filename != 'generate_manifest.py':
                sha256_hash = hashlib.sha256()
                with open(file_path, "rb") as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
                files_manifest[filename] = sha256_hash.hexdigest()
                
    manifest_data = {"files": files_manifest}
    manifest_path = os.path.join(root_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f, indent=2)
        
    print(f"[MANIFEST GENERATOR] Se generó manifest.json en: {manifest_path}")
    print(f"Archivos incluidos ({len(files_manifest)}):")
    for k, v in files_manifest.items():
        print(f"  - {k}: {v[:8]}")

if __name__ == '__main__':
    generate_manifest()
