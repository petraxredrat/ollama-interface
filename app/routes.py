from flask import Blueprint, request, jsonify, render_template, Response, current_app
import os
import json
import requests
import base64
from pathlib import Path
import re
import subprocess
import threading

bp = Blueprint('main', __name__)

OLLAMA_API = "http://localhost:11434"  # Remove /api from base URL

# Store current working directory
CURRENT_DIR = os.path.abspath(os.getcwd())

download_progress = {"progress": 0, "error": None}
download_lock = threading.Lock()

def update_download_progress(progress):
    global download_progress
    with download_lock:
        download_progress["progress"] = progress

@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/list_models')
def list_models():
    try:
        print("\n=== Fetching Models ===")
        try:
            response = requests.get(f"{OLLAMA_API}/api/tags", timeout=10)  # Increased timeout
            print(f"Response status: {response.status_code}")
            print(f"Response content: {response.text}")  # Added response content logging
        except requests.exceptions.ConnectionError:
            print("Connection error - Ollama not running")
            return jsonify({
                "error": "Could not connect to Ollama. Please ensure Ollama is running (ollama serve)",
                "details": "Connection refused"
            }), 503
        except requests.exceptions.Timeout:
            print("Connection timeout")
            return jsonify({
                "error": "Connection to Ollama timed out. The server might be busy or unresponsive",
                "details": "Request timed out after 10 seconds"
            }), 504
            
        if response.status_code != 200:
            error_msg = f"Failed to fetch models: {response.text}"
            print(f"Error: {error_msg}")
            return jsonify({"error": error_msg}), response.status_code
        
        try:
            data = response.json()
        except json.JSONDecodeError:
            print("Invalid JSON response from Ollama")
            return jsonify({"error": "Invalid response from Ollama API"}), 500
            
        print(f"Raw Ollama response: {data}")
        
        if not isinstance(data, dict) or 'models' not in data:
            print("Invalid response structure")
            return jsonify({"error": "Invalid response structure from Ollama"}), 500
            
        models = data.get('models', [])
        if not models:
            print("No models found")
            return jsonify({"models": []})
            
        formatted_models = []
        for model in models:
            try:
                details = model.get('details', {})
                model_info = {
                    "name": model.get('name', ''),
                    "tag": model.get('name', ''),
                    "size": model.get('size', 0),
                    "modified_at": model.get('modified_at', ''),
                    "parameter_size": details.get('parameter_size', ''),
                    "family": details.get('family', ''),
                    "families": details.get('families', []),
                    "format": details.get('format', ''),
                    "quantization": details.get('quantization_level', '')
                }
                formatted_models.append(model_info)
                print(f"Added model: {model_info}")
            except Exception as e:
                print(f"Error processing model {model}: {str(e)}")
                continue
        
        result = {"models": formatted_models}
        print(f"Final response: {result}")
        return jsonify(result)
        
    except Exception as e:
        error_msg = f"Exception in list_models: {str(e)}"
        print(f"Error: {error_msg}")
        return jsonify({"error": error_msg}), 500

@bp.route('/generate', methods=['POST'])
def generate():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No request data provided"}), 400
            
        message = data.get('message', '').strip()
        if not message:
            return jsonify({"error": "Message is required"}), 400
            
        model = data.get('model', 'llama2').lower()
        image_data = data.get('image')
        
        # Validate image data for multimodal models
        if image_data and model == "llava":
            if not isinstance(image_data, str):
                return jsonify({"error": "Image data must be a base64 string"}), 400
            try:
                # Validate base64 format
                if "base64," in image_data:
                    image_data = image_data.split("base64,")[1]
                base64.b64decode(image_data)
            except Exception as e:
                return jsonify({"error": "Invalid image data format"}), 400
        
        # Prepare request data
        request_data = {
            "model": model,
            "messages": [{"role": "user", "content": message}],
            "stream": False  # Ensure non-streaming response
        }
        
        # Add image for multimodal models
        if image_data and model == "llava":
            request_data["messages"][0]["images"] = [image_data]
            
        # Add special handling for code generation models
        if "code" in model or "codellama" in model:
            request_data["context"] = "You are an expert programmer. Generate clean, well-documented code."
            
        # Make request to Ollama with timeout
        print(f"Sending request to Ollama with model: {model}")
        try:
            response = requests.post(
                f"{OLLAMA_API}/api/chat",
                json=request_data,
                timeout=60  # 60 second timeout
            )
        except requests.Timeout:
            return jsonify({"error": "Request timed out. Please try again."}), 504
        except requests.ConnectionError:
            return jsonify({"error": "Could not connect to Ollama. Is it running?"}), 503
            
        print(f"Response status: {response.status_code}")
        
        if response.status_code != 200:
            error_msg = "Failed to generate response"
            try:
                error_data = response.json()
                if 'error' in error_data:
                    error_msg = error_data['error']
            except:
                error_msg = f"HTTP {response.status_code}: {response.text}"
            print(f"Error: {error_msg}")
            return jsonify({"error": error_msg}), response.status_code
        
        try:
            response_data = response.json()
            print(f"Response data: {response_data}")
            
            if not response_data or 'message' not in response_data:
                return jsonify({"error": "Invalid response from model"}), 500
                
            return jsonify({
                "response": response_data.get('message', {}).get('content', ''),
                "model": model,
                "total_tokens": response_data.get('total_tokens', 0)
            })
            
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON response from model"}), 500
            
    except Exception as e:
        print(f"Exception in generate: {str(e)}")
        return jsonify({
            "error": "Internal server error",
            "details": str(e)
        }), 500

@bp.route('/save_code', methods=['POST'])
def save_code():
    try:
        data = request.json
        code = data.get('code', '')
        filename = data.get('filename', 'generated_code.py')
        
        if not filename.endswith('.py'):
            filename += '.py'
            
        filepath = os.path.join('generated_code', filename)
        with open(filepath, 'w') as f:
            f.write(code)
            
        return jsonify({"message": f"Code saved to {filename}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/model_status', methods=['GET'])
def model_status():
    model = request.args.get('name')
    if not model:
        return jsonify({"error": "Model name is required"}), 400
        
    try:
        response = requests.get(f"{OLLAMA_API}/api/show", params={"name": model})
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/pull_model', methods=['POST'])
def pull_model():
    model = request.json.get('model')
    if not model:
        return jsonify({"error": "Model name is required"}), 400
        
    try:
        print(f"Starting model pull: {model}")
        
        # First check if model exists
        show_response = requests.get(f"{OLLAMA_API}/api/show", params={"name": model}, timeout=5)
        if show_response.status_code == 200:
            print(f"Model {model} is already loaded")
            return jsonify({"message": "Model is already loaded"})
            
        print(f"Pulling model {model} from Ollama API")
        
        # Stream the response to handle large models
        with requests.post(
            f"{OLLAMA_API}/api/pull",
            json={"name": model},
            stream=True,
            timeout=None  # No timeout for large models
        ) as response:
            
            if response.status_code != 200:
                error_msg = "Failed to pull model"
                try:
                    error_data = response.json()
                    if 'error' in error_data:
                        error_msg = error_data['error']
                except:
                    error_msg = response.text
                print(f"Error pulling model: {error_msg}")
                return jsonify({"error": error_msg}), response.status_code
            
            total_downloaded = 0
            for line in response.iter_lines():
                if line:
                    try:
                        progress = json.loads(line)
                        if 'completed' in progress:
                            total_downloaded = progress['completed']
                            update_download_progress(total_downloaded)
                            print(f"Download progress: {total_downloaded}%")
                    except json.JSONDecodeError:
                        print(f"Could not parse progress line: {line}")
                        continue
            
            print(f"Successfully pulled model: {model}")
            return jsonify({
                "message": "Model pulled successfully",
                "model": model,
                "total_downloaded": total_downloaded
            })
        
    except requests.exceptions.ConnectionError:
        error_msg = "Could not connect to Ollama. Is it running?"
        print(f"Error: {error_msg}")
        return jsonify({"error": error_msg}), 503
    except requests.exceptions.Timeout:
        error_msg = "Connection to Ollama timed out"
        print(f"Error: {error_msg}")
        return jsonify({"error": error_msg}), 504
    except Exception as e:
        error_msg = f"Error pulling model: {str(e)}"
        print(f"Error: {error_msg}")
        return jsonify({"error": error_msg}), 500

@bp.route('/download_model', methods=['POST'])
def download_model():
    global download_progress
    data = request.json
    model = data.get('model')
    
    if not model:
        return jsonify({"error": "No model specified"}), 400
    
    def download_thread():
        try:
            response = requests.post(
                f"{OLLAMA_API}/api/pull",
                json={"name": model},
                stream=True
            )
            
            total_size = 0
            downloaded = 0
            
            for line in response.iter_lines():
                if line:
                    try:
                        data = json.loads(line.decode())
                        if 'total' in data:
                            total_size = data['total']
                        if 'completed' in data:
                            downloaded = data['completed']
                            if total_size > 0:
                                progress = int((downloaded / total_size) * 100)
                                update_download_progress(progress)
                    except json.JSONDecodeError:
                        continue
            
            update_download_progress(100)
            
        except Exception as e:
            with download_lock:
                download_progress["error"] = str(e)
    
    with download_lock:
        download_progress = {"progress": 0, "error": None}
    
    thread = threading.Thread(target=download_thread)
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "Download started"})

@bp.route('/download_progress')
def get_download_progress():
    with download_lock:
        return jsonify(download_progress)

@bp.route('/process_image', methods=['POST'])
def process_image():
    try:
        data = request.json
        model = data.get('model')
        image_data = data.get('image')  
        prompt = data.get('prompt', 'What do you see in this image?')
        
        if not model or not image_data:
            return jsonify({"error": "Model and image are required"}), 400
            
        if 'base64,' in image_data:
            image_data = image_data.split('base64,')[1]
            
        print(f"Processing image with model: {model}")  
        print(f"Prompt: {prompt}")  
        print(f"Image data length: {len(image_data)}")  
        
        payload = {
            "model": model,
            "prompt": prompt,
            "images": [image_data],
            "stream": False
        }
        
        print("Sending request to Ollama...")  
        
        response = requests.post(
            f"{OLLAMA_API}/api/generate",
            json=payload,
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"Response status: {response.status_code}")  
        
        if response.status_code == 200:
            result = response.json()
            print(f"Response from Ollama: {result}")  
            
            if 'error' in result:
                error_msg = result['error']
                print(f"Error from Ollama: {error_msg}")  
                return jsonify({"error": error_msg}), 500
                
            return jsonify({
                "response": result.get('response', ''),
                "model": model
            })
        else:
            try:
                error_data = response.json()
                error_msg = error_data.get('error', f"Failed to process image (Status: {response.status_code})")
            except Exception as e:
                error_msg = f"Failed to process image (Status: {response.status_code})"
            
            print(f"Error response: {error_msg}")  
            return jsonify({"error": error_msg}), 500
            
    except Exception as e:
        print(f"Exception in process_image: {str(e)}")  
        return jsonify({"error": str(e)}), 500

@bp.route('/get_cwd')
def get_cwd():
    try:
        return jsonify({"cwd": os.getcwd()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/execute_command', methods=['POST'])
def execute_command():
    try:
        command = request.json.get('command')
        if not command:
            return jsonify({"error": "No command provided"}), 400

        # Create process with pipe for output
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=CURRENT_DIR
        )

        # Get output with timeout
        try:
            stdout, stderr = process.communicate(timeout=30)
            output = stdout + stderr
            return jsonify({
                "output": output,
                "cwd": os.getcwd()
            })
        except subprocess.TimeoutExpired:
            process.kill()
            return jsonify({"error": "Command timed out after 30 seconds"}), 408

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/check_ollama')
def check_ollama():
    try:
        response = requests.get(f"{OLLAMA_API}/api/tags", timeout=2)
        if response.status_code == 200:
            return jsonify({"status": "ok"})
        return jsonify({"error": f"Ollama returned status code {response.status_code}"})
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not connect to Ollama. Is it running?"})
    except requests.exceptions.Timeout:
        return jsonify({"error": "Connection to Ollama timed out"})
    except Exception as e:
        return jsonify({"error": f"Error checking Ollama: {str(e)}"})

@bp.route('/save_file', methods=['POST'])
def save_file():
    try:
        data = request.json
        filename = data.get('filename')
        content = data.get('content')
        
        if not filename or not content:
            return jsonify({"error": "Filename and content are required"}), 400
            
        filename = os.path.basename(filename)
        filename = ''.join(c for c in filename if c.isalnum() or c in '._- ')
        
        if not filename:
            return jsonify({"error": "Invalid filename"}), 400
            
        save_path = os.path.join(current_app.root_path, 'generated_code')
        os.makedirs(save_path, exist_ok=True)
        
        file_path = os.path.join(save_path, filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return jsonify({"message": f"File {filename} saved successfully"})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/check_files', methods=['POST'])
def check_files():
    try:
        data = request.json
        files = data.get('files', [])
        
        if not files:
            return jsonify({"error": "No files to check"}), 400
            
        errors = []
        
        for file in files:
            filename = file.get('filename')
            content = file.get('content')
            
            if not filename or not content:
                continue
                
            if filename.endswith('.py'):
                try:
                    compile(content, filename, 'exec')
                except Exception as e:
                    errors.append(f"Error in {filename}: {str(e)}")
            elif filename.endswith('.js'):
                try:
                    process = subprocess.run(
                        ['node', '--check'],
                        input=content,
                        text=True,
                        capture_output=True
                    )
                    if process.returncode != 0:
                        errors.append(f"Error in {filename}: {process.stderr}")
                except Exception as e:
                    errors.append(f"Error in {filename}: {str(e)}")
            elif filename.endswith(('.html', '.htm')):
                if not content.strip().startswith('<!DOCTYPE') and not content.strip().startswith('<html'):
                    errors.append(f"Warning in {filename}: Missing DOCTYPE or html tag")
                    
        if errors:
            return jsonify({
                "message": "Found some issues:",
                "errors": errors
            })
            
        return jsonify({"message": "All files passed validation!"})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/debug_ollama')
def debug_ollama():
    try:
        print("Testing Ollama connection...")
        response = requests.get(f"{OLLAMA_API}/api/tags")
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {response.headers}")
        print(f"Response text: {response.text}")
        return jsonify({
            "status": response.status_code,
            "headers": dict(response.headers),
            "text": response.text
        })
    except Exception as e:
        print(f"Exception testing Ollama: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response
