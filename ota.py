import os
import gc
import machine
import hashlib
import binascii
import config
import urequests

def calculate_local_sha256(filepath):
    try:
        h = hashlib.sha256()
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(512)
                if not chunk:
                    break
                h.update(chunk)
        return binascii.hexlify(h.digest()).decode('utf-8')
    except OSError:
        return ""

def check_and_perform_ota():
    print("\n[OTA] Iniciando comprobación de actualización desde GitHub...")
    
    # Liberar memoria antes de iniciar la conexión HTTPS (TLS es muy pesado)
    gc.collect()
    
    # Construir la URL base de GitHub Raw
    base_url = "https://raw.githubusercontent.com/{}/{}/{}".format(
        config.OTA_GITHUB_USER,
        config.OTA_GITHUB_REPO,
        config.OTA_GITHUB_BRANCH
    )
    
    manifest_url = base_url + "/manifest.json"
    print("[OTA] Consultando manifiesto en:", manifest_url)
    
    manifest = None
    res = None
    try:
        res = urequests.get(manifest_url)
        if res.status_code == 200:
            manifest = res.json()
        else:
            print("[OTA ERROR] No se pudo obtener el manifiesto de GitHub. HTTP Status:", res.status_code)
    except Exception as e:
        print("[OTA ERROR] Fallo de conexión con GitHub (posible falta de RAM para TLS):", e)
    finally:
        if res:
            try:
                res.close()
            except:
                pass
        gc.collect()

    if not manifest or "files" not in manifest:
        print("[OTA] Comprobación OTA cancelada.")
        return False
        
    remote_files = manifest["files"]
    files_to_update = []
    
    # Comparar los hashes locales y remotos
    for filename, remote_hash in remote_files.items():
        if filename in ("wifi.json", "config.json", "manifest.json", "generate_manifest.py", "dashboard.html"):
            continue
            
        local_hash = calculate_local_sha256(filename)
        if local_hash != remote_hash:
            print("[OTA] Detectado cambio en '{}'".format(filename))
            print("      Local:  {}".format(local_hash[:8] if local_hash else "No existe"))
            print("      Remoto: {}".format(remote_hash[:8]))
            files_to_update.append(filename)
            
    if not files_to_update:
        print("[OTA SUCCESS] El sistema de archivos está actualizado con GitHub. Sin cambios.\n")
        return False
        
    print("[OTA] Descargando archivos actualizados ({}): {}".format(len(files_to_update), files_to_update))
    
    downloaded_successfully = True
    temp_files = []
    
    # Descargar cada archivo en bloques para optimizar RAM
    for filename in files_to_update:
        temp_filename = filename + ".tmp"
        temp_files.append((filename, temp_filename))
        
        file_url = base_url + "/" + filename
        print("[OTA] Descargando '{}' desde GitHub...".format(filename))
        
        gc.collect()
        res_file = None
        try:
            res_file = urequests.get(file_url, stream=True)
            if res_file.status_code == 200:
                with open(temp_filename, 'wb') as f:
                    while True:
                        chunk = res_file.raw.read(512)
                        if not chunk:
                            break
                        f.write(chunk)
                print("[OTA] Guardado temporal '{}'.".format(temp_filename))
            else:
                print("[OTA ERROR] Fallo HTTP al descargar '{}': {}".format(filename, res_file.status_code))
                downloaded_successfully = False
        except Exception as err:
            print("[OTA ERROR] Error de red descargando '{}': {}".format(filename, err))
            downloaded_successfully = False
        finally:
            if res_file:
                try:
                    res_file.close()
                except:
                    pass
            gc.collect()
            
        if not downloaded_successfully:
            break
            
    # Si todas las descargas fueron exitosas, reemplazar los archivos
    if downloaded_successfully:
        print("[OTA] Reemplazando archivos antiguos por nuevas versiones...")
        for filename, temp_filename in temp_files:
            try:
                os.remove(filename)
            except OSError:
                pass
            
            try:
                os.rename(temp_filename, filename)
                print("[OTA SUCCESS] Archivo '{}' actualizado.".format(filename))
            except Exception as e:
                print("[OTA ERROR] Fallo al renombrar '{}': {}".format(temp_filename, e))
                downloaded_successfully = False
                
        if downloaded_successfully:
            print("[OTA SUCCESS] ¡Todo actualizado! Reiniciando ESP32...\n")
            try:
                import audio
                audio.play_pomodoro_complete()
            except:
                pass
            machine.reset()
            return True
            
    # Si hubo algún fallo, eliminar archivos temporales
    print("[OTA WARNING] Ocurrió un error. Limpiando temporales...")
    for _, temp_filename in temp_files:
        try:
            os.remove(temp_filename)
        except OSError:
            pass
            
    return False
