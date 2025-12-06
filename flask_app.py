from flask import Flask, request, render_template, jsonify, redirect, url_for
import requests
import base64
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configuración
app.config["SECRET_KEY"] = "tu-clave-secreta-aqui"
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB max

# URL del webhook de n8n - Configuración para EC2
# Si n8n está en la misma instancia EC2, usar localhost
# Si n8n está en otra instancia, usar la IP correspondiente
N8N_WEBHOOK_URL = os.getenv(
    "N8N_WEBHOOK_URL", "http://44.214.75.160:5678/webhook-test/identify-and-answer"
)

# Crear directorio de uploads si no existe
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    """Página principal con formulario"""
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze_image():
    """Endpoint API que envía datos al workflow de n8n"""
    try:
        # Verificar si se subió un archivo
        if "image" not in request.files:
            return jsonify({"error": "No se proporcionó imagen"}), 400

        file = request.files["image"]

        if file.filename == "":
            return jsonify({"error": "No se seleccionó archivo"}), 400

        if file and allowed_file(file.filename):
            # Leer el archivo en memoria
            image_data = file.read()

            # Obtener pregunta opcional
            question = request.form.get("question", "").strip()

            # Preparar payload que coincida con la estructura del webhook de n8n
            # Basado en el debug del Convert Image Data, usar estructura body
            payload = {
                "body": {
                    "files": {
                        "image": {
                            "data": base64.b64encode(image_data).decode("utf-8"),
                            "filename": secure_filename(file.filename or "image.jpg"),
                            "mimeType": file.mimetype or "image/jpeg",
                        }
                    },
                    "question": question if question else None,
                },
                "headers": {
                    "Content-Type": "application/json",
                    "User-Agent": "Flask-UFRO-Client/1.0",
                },
                "params": {},
                "query": {},
            }

            print(f"🚀 Enviando solicitud a n8n...")
            print(f"📷 Imagen: {file.filename} ({len(image_data)} bytes)")
            print(f"❓ Pregunta: {question or 'None'}")

            # Enviar a n8n webhook con timeout mayor
            response = requests.post(
                N8N_WEBHOOK_URL,
                json=payload,
                timeout=60,  # Aumentado a 60 segundos
            )

            print(f"📡 Respuesta de n8n: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                print(
                    f"✅ Resultado obtenido: decision={result.get('decision', 'unknown')}"
                )
                return jsonify(result)
            else:
                print(f"❌ Error de n8n: {response.status_code} - {response.text}")
                return jsonify(
                    {
                        "error": f"Error del workflow: {response.status_code}",
                        "details": response.text,
                    }
                ), 500

        else:
            return jsonify({"error": "Tipo de archivo no permitido"}), 400

    except requests.RequestException as e:
        print(f"❌ Error de conexión: {str(e)}")
        return jsonify({"error": f"Error de conexión: {str(e)}"}), 500
    except Exception as e:
        print(f"❌ Error interno: {str(e)}")
        return jsonify({"error": f"Error interno: {str(e)}"}), 500


@app.route("/health")
def health_check():
    """Endpoint de salud"""
    try:
        # Probar conexión con n8n
        # response = requests.get(N8N_WEBHOOK_URL.replace('/webhook/', '/health/'), timeout=5)
        return jsonify(
            {
                "status": "healthy",
                "service": "Flask App - Cliente n8n",
                "n8n_webhook": N8N_WEBHOOK_URL,
            }
        )
    except:
        return jsonify(
            {
                "status": "degraded",
                "service": "Flask App - Cliente n8n",
                "n8n_webhook": N8N_WEBHOOK_URL,
            }
        ), 503


if __name__ == "__main__":
    # Configurar desde variables de entorno para EC2
    # IMPORTANTE: Para EC2, usar "0.0.0.0" para aceptar conexiones externas
    host = os.getenv("FLASK_HOST", "0.0.0.0")  # Cambiado para EC2
    port = int(os.getenv("FLASK_PORT", "3000"))
    debug = (
        os.getenv("FLASK_DEBUG", "False").lower() == "true"
    )  # Debug False en producción

    print(f"🚀 Flask App iniciando en http://{host}:{port}")
    print(f"📡 Conectando a n8n webhook: {N8N_WEBHOOK_URL}")
    print(f"🌐 Accesible desde: http://44.214.75.160:{port}")

    app.run(host=host, port=port, debug=debug)
