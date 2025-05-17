import os
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
from webdriver_manager.chrome import ChromeDriverManager

# Configuración headless para GitHub Actions
chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920x1080")
chrome_options.add_argument("--remote-debugging-port=9222")

# Inicializar driver
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)
wait = WebDriverWait(driver, 20)

# Configuración de carpetas
fecha_carpeta = datetime.now().strftime("%d-%m-%Y")
save_dir = os.path.join(os.getcwd(), f"SBS-RETASAS-{fecha_carpeta}")
os.makedirs(save_dir, exist_ok=True)

def get_options_text(id_select):
    select = Select(wait.until(EC.presence_of_element_located((By.ID, id_select))))
    opciones = [o.text.strip() for o in select.options if o.get_attribute("value").strip() != ""]
    print(f"Opciones de {id_select}: {opciones}")
    return opciones

def select_option(id_select, texto):
    select = Select(wait.until(EC.element_to_be_clickable((By.ID, id_select))))
    opciones = [o.text.strip() for o in select.options if o.get_attribute("value").strip() != ""]
    coincidencias = [opcion for opcion in opciones if texto.lower() in opcion.lower()]
    
    if not coincidencias:
        print(f"Opción '{texto}' no encontrada en {id_select}. Opciones disponibles: {opciones}")
        raise Exception(f"Opción '{texto}' no está en el select {id_select}")
    
    print(f"Seleccionando {coincidencias[0]} en {id_select}")
    select.select_by_visible_text(coincidencias[0])
    time.sleep(2)

def extraer_tabla_manual():
    print("Extrayendo tabla...")
    table = wait.until(EC.presence_of_element_located((By.ID, "myTable")))
    thead = table.find_element(By.TAG_NAME, "thead")
    encabezados = [th.text.strip() for th in thead.find_elements(By.TAG_NAME, "th")]
    tbody = table.find_element(By.TAG_NAME, "tbody")
    filas = tbody.find_elements(By.TAG_NAME, "tr")
    
    datos = []
    for fila in filas:
        celdas = fila.find_elements(By.TAG_NAME, "td")
        fila_texto = [celda.text.strip().replace('%','').strip() for celda in celdas]
        datos.append(fila_texto)
    
    df = pd.DataFrame(datos, columns=encabezados)
    print(f"Tabla extraída con {len(df)} filas y {len(df.columns)} columnas")
    return df

def ajustar_anchos(worksheet, df):
    worksheet.set_column(0, 0, 20)
    worksheet.set_column(1, 1, 50)
    for i, col in enumerate(df.columns):
        max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
        worksheet.set_column(i, i, max_len)

def main_scraping():
    base_url = "https://www.sbs.gob.pe/app/retasas/paginas/retasasInicio.aspx?p=D"
    driver.get(base_url)
    
    try:
        regiones = get_options_text("ddlDepartamento")

        for region in regiones:
            select_option("ddlDepartamento", region)
            tipos_operacion = get_options_text("ddlTipoProducto")

            for tipo in tipos_operacion:
                select_option("ddlTipoProducto", tipo)
                productos = get_options_text("ddlProducto")

                for producto in productos:
                    select_option("ddlProducto", producto)
                    WebDriverWait(driver, 10).until(
                        lambda d: len(get_options_text("ddlCondicion")) > 0
                    )

                    condiciones = get_options_text("ddlCondicion")

                    if not condiciones:
                        print(f"Sin condiciones: {region} - {tipo} - {producto}")
                        continue

                    for condicion in condiciones:
                        try:
                            select_option("ddlCondicion", condicion)
                        except Exception as e:
                            print(f"Error seleccionando condición: {condicion} | {e}")
                            continue

                        try:
                            btn_consultar = wait.until(EC.element_to_be_clickable((By.ID, "btnConsultar")))
                            btn_consultar.click()
                            time.sleep(3)
                            
                            wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "ifrmContendedor")))
                            df = extraer_tabla_manual()
                            driver.switch_to.default_content()

                            if df.empty:
                                print(f"Tabla vacía: {region}, {tipo}, {producto}, {condicion}")
                                continue

                            # Generar nombre de archivo
                            fecha_str = datetime.now().strftime("%d-%m-%Y")
                            nombre_archivo = f"{fecha_str}-{region}-{tipo}-{producto}-{condicion}".replace(' ', '-')
                            for ch in ['$', '.', ',', '|', '/']:
                                nombre_archivo = nombre_archivo.replace(ch, "-")
                            
                            if not nombre_archivo.endswith(".xlsx"):
                                nombre_archivo += ".xlsx"
                            
                            ruta_guardado = os.path.join(save_dir, nombre_archivo)

                            # Guardar Excel
                            with pd.ExcelWriter(ruta_guardado, engine='xlsxwriter') as writer:
                                workbook = writer.book
                                worksheet = workbook.add_worksheet('Datos')
                                writer.sheets['Datos'] = worksheet

                                # Metadatos
                                encabezados_personalizados = [
                                    ['DEPARTAMENTO:', region],
                                    ['TIPO DE PRODUCTO:', tipo],
                                    ['PRODUCTO:', producto],
                                    ['CONDICION:', condicion],
                                    ['FECHA:', fecha_str]
                                ]
                                
                                for i, row in enumerate(encabezados_personalizados):
                                    worksheet.write(i, 0, row[0])
                                    worksheet.write(i, 1, row[1])

                                # Datos
                                df.to_excel(writer, sheet_name='Datos', startrow=6, index=False)
                                ajustar_anchos(worksheet, df)

                            print(f"Archivo guardado: {ruta_guardado}")

                        except Exception as e:
                            print(f"Error en el proceso principal: {str(e)}")
                            driver.save_screenshot('error_screenshot.png')
                        
                        finally:
                            driver.get(base_url)
                            select_option("ddlDepartamento", region)
                            select_option("ddlTipoProducto", tipo)
                            select_option("ddlProducto", producto)

    except Exception as e:
        print(f"Error crítico: {str(e)}")
        driver.save_screenshot('critical_error.png')
    
    finally:
        driver.quit()
        print("Proceso completado")

if __name__ == "__main__":
    main_scraping()