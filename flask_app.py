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

# URL del webhook de n8n
N8N_WEBHOOK_URL = "http://localhost:5678/webhook/identify-and-answer"

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

            # Preparar datos para n8n
            files_data = {
                "image": {
                    "data": base64.b64encode(image_data).decode("utf-8"),
                    "filename": secure_filename(file.filename),
                    "mimetype": file.mimetype,
                }
            }

            # Obtener pregunta opcional
            question = request.form.get("question", "").strip()

            payload = {
                "files": files_data,
                "query": {"question": question if question else None},
            }

            # Enviar a n8n webhook
            response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=30)

            if response.status_code == 200:
                return jsonify(response.json())
            else:
                return jsonify(
                    {
                        "error": f"Error del workflow: {response.status_code}",
                        "details": response.text,
                    }
                ), 500

        else:
            return jsonify({"error": "Tipo de archivo no permitido"}), 400

    except requests.RequestException as e:
        return jsonify({"error": f"Error de conexión: {str(e)}"}), 500
    except Exception as e:
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
    # Configurar desde variables de entorno
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "3000"))
    debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"

    print(f"🚀 Flask App iniciando en http://{host}:{port}")
    print(f"📡 Conectando a n8n webhook: {N8N_WEBHOOK_URL}")

    app.run(host=host, port=port, debug=debug)
