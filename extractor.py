import os

def principal():
    # Detectar la ubicación absoluta del script
    ruta_script = os.path.dirname(os.path.abspath(__file__))
    nombre_propio = os.path.basename(__file__)
    
    nombre_archivo_contenido = os.path.join(ruta_script, "archivos.txt")

    print(f"--- DIRECTORIO DE TRABAJO: {ruta_script} ---")
    print("Extrayendo TODOS los archivos .py del proyecto...")
    
    lista_para_contenido = []
    LIMITE_CHARS = 1000000  # Aumentamos el límite para asegurar que entren todos

    # Carpetas que no queremos escanear (entornos virtuales, compilados, etc)
    carpetas_ignoradas = ['.venv', 'venv', '__pycache__', 'dist', 'build', '.git', 'scratch']

    for raiz, directorios, archivos in os.walk(ruta_script):
        # Modificar 'directorios' en su lugar para que os.walk ignore las carpetas no deseadas
        directorios[:] = [d for d in directorios if d not in carpetas_ignoradas]
        
        for arch in archivos:
            # Solo nos interesan los .py
            if not arch.endswith('.py'):
                continue
                
            ruta_completa = os.path.join(raiz, arch)
            # Calculamos la ruta relativa (ej: core/threads.py)
            ruta_relativa = os.path.relpath(ruta_completa, ruta_script).replace("\\", "/")
            
            # Excluir archivos no deseados (este script, tests, debugs, etc)
            nombres_ignorados = [nombre_propio, "monkey_tester.py"]
            prefijos_ignorados = ["debug_", "test_"]
            
            if arch in nombres_ignorados:
                continue
            if any(arch.startswith(prefijo) for prefijo in prefijos_ignorados):
                continue
                
            try:
                with open(ruta_completa, 'r', encoding='utf-8', errors='ignore') as f:
                    data = f.read()
                    
                    # Filtro de binarios por seguridad
                    if '\x00' in data:
                        print(f"![AVISO] {ruta_relativa} detectado como binario, se ignora.")
                        continue
                        
                    if len(data) <= LIMITE_CHARS:
                        lista_para_contenido.append((ruta_relativa, data))
                    else:
                        print(f"![SALTADO] {ruta_relativa} excede el límite de {LIMITE_CHARS} caracteres.")
            except Exception as e:
                print(f"![ERROR] No se pudo leer {ruta_relativa}: {e}")

    # GENERAR CONTENIDO ÚNICO (archivos.txt)
    if lista_para_contenido:
        with open(nombre_archivo_contenido, 'w', encoding='utf-8') as f:
            for i, (nombre_relativo, texto) in enumerate(lista_para_contenido):
                # Inicio del archivo
                f.write(f"Archivo: {nombre_relativo}\n")
                f.write(texto)
                
                # Asegurar salto de línea antes de los separadores
                if not texto.endswith("\n"): 
                    f.write("\n")
                
                # SEPARADOR CON ESPACIADO DE 3 SALTOS DE LÍNEA
                if i < len(lista_para_contenido) - 1:
                    nombre_siguiente = lista_para_contenido[i+1][0]
                    f.write("\n\n\n") # 3 espacios arriba
                    f.write(f"Aqui termina el archivo {nombre_relativo}\n")
                    f.write("======================================================\n")
                    f.write(f"Aqui inicia el archivo {nombre_siguiente}\n")
                    f.write("\n\n\n") # 3 espacios abajo
                else:
                    # Final del último archivo
                    f.write("\n\n\n")
                    f.write(f"Aqui termina el archivo {nombre_relativo}\n")
            
        print(f"\n[OK] ¡ÉXITO! Se creó el archivo '{os.path.basename(nombre_archivo_contenido)}' conteniendo {len(lista_para_contenido)} archivos .py.")
    else:
        print("\n[!] No se encontraron archivos .py válidos para procesar.")

if __name__ == "__main__":
    principal()
