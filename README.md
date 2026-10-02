# Frame Extractor

Aplicación de escritorio para explorar vídeos, guardar fotogramas y crear clips con audio. Está construida con Python, PySide6 y OpenCV, con una interfaz oscura de estilo liquid glass.

## Funciones

- **Modos Capturas y Clips:** selector de dos posiciones centrado en la barra superior, con indicador animado del modo activo.
- **Captura de fotogramas:** guarda el frame actual en PNG o JPG. La captura respeta el recorte y el zoom visible.
- **Navegación precisa:** avanza frame a frame, salta por intervalos y permite buscar en la línea de tiempo.
- **Reproducción con audio:** escucha el audio del vídeo mientras se reproduce en la aplicación.
- **Miniaturas y vídeos recientes:** navega la tira de miniaturas y vuelve a abrir archivos recientes.
- **Marcadores:** señala fotogramas de interés y expórtalos como imágenes.
- **Extracción por lotes:** guarda fotogramas cada cierto número de frames o segundos.
- **Clips múltiples:** marca varios puntos de inicio y fin en el mismo vídeo; administra los rangos en la lista de clips.
- **Dos formas de exportar clips:** guarda cada rango como un MP4 independiente o combina los rangos en un vídeo, en orden cronológico.
- **Exportación con audio:** los MP4 se codifican en H.264 y AAC para facilitar su reproducción en distintos dispositivos.
- **Configuración persistente:** elige carpeta de salida, formato y calidad de imagen, escala y preferencias de navegación.

## Requisitos

- Python 3.10 o posterior
- FFmpeg y FFprobe instalados y disponibles en el `PATH` del sistema para exportar clips

La aplicación usa Qt Multimedia para reproducir audio. Los vídeos sin pista de audio se reproducen sin sonido.

## Instalación y ejecución

```bash
git clone https://github.com/Atrayant-I/frame-extractor.git
cd frame-extractor
python -m pip install -r requirements.txt
python main.py
```

En Windows, si FFmpeg no está disponible, la aplicación avisará al intentar exportar clips. Instala FFmpeg y asegúrate de que tanto `ffmpeg` como `ffprobe` se puedan ejecutar desde una terminal.

## Uso del modo Clips

1. Abre un vídeo y selecciona **Clips** en el selector centrado de la barra superior.
2. Busca el frame inicial y pulsa **Marcar inicio** (o `I`).
3. Busca el frame final y pulsa **Marcar fin** (o `O`). El rango queda agregado a la lista; repite para añadir más clips.
4. Abre **Clips** para revisar o eliminar rangos y elige **Guardar clips individuales** o **Guardar video combinado**.

Los rangos se exportan en el orden temporal del vídeo original. El frame final marcado se incluye en el clip.

## Atajos de teclado

| Tecla | Acción |
| --- | --- |
| `Espacio` | En Capturas, guarda el frame actual; en Clips, reproduce o pausa |
| `←` / `→` | Ir al frame anterior o siguiente |
| `Shift` + `←` / `→` | Saltar hacia atrás o adelante |
| `I` / `O` | Marcar inicio o fin de un clip en modo Clips |
| `M` | Añadir o quitar marcador en modo Capturas |
| `Ctrl` + `S` | Guardar el frame actual |
| `Ctrl` + `O` | Abrir un vídeo |
| `Ctrl` + `E` | Abrir la carpeta de exportación |
| `Inicio` / `Fin` | Ir al primer o último frame |

## Tecnologías

- Python
- PySide6 / Qt Widgets y Qt Multimedia
- OpenCV (`opencv-python`)
- FFmpeg / FFprobe para exportar clips

## Licencia

Este proyecto se distribuye bajo la licencia MIT. Consulta [`LICENSE`](LICENSE) para ver sus términos.
