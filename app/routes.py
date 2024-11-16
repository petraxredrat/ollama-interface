from flask import Blueprint, request, jsonify, render_template, Response, current_app
import os
import json
import requests
import base64
from pathlib import Path
import re
import subprocess
import threading
import sys

bp = Blueprint('main', __name__)

OLLAMA_API = "http://localhost:11434"  # Remove /api from base URL

# Global variables
CURRENT_DIR = os.path.abspath(os.getcwd())

# Set the generated code directory
GENERATED_CODE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'generated_code')

download_progress = {"progress": 0, "error": None}
download_lock = threading.Lock()

def update_download_progress(progress):
    global download_progress
    with download_lock:
        download_progress["progress"] = progress

def get_language_from_content(content):
    """Detect language from code content."""
    # Common language indicators
    indicators = {
        'import ': 'python',
        'def ': 'python',
        'class ': 'python',
        'function ': 'javascript',
        'var ': 'javascript',
        'let ': 'javascript',
        'const ': 'javascript',
        '<html': 'html',
        '<!DOCTYPE': 'html',
        '<style': 'css',
        '{': 'json'  # This is a weak indicator, should be used last
    }
    
    content_lower = content.lower()
    for indicator, lang in indicators.items():
        if indicator in content_lower:
            return lang
    return 'plaintext'

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

        model = data.get('model')
        prompt = data.get('prompt', '')
        image_data = data.get('image')
        request_type = data.get('type', 'chat')  # 'chat' or 'code'

        if not model:
            return jsonify({"error": "No model specified"}), 400

        # Prepare the request data
        request_data = {
            "model": model,
            "stream": False
        }

        # Handle different types of requests
        if request_type == 'code':
            # Add code generation specific prompt
            request_data["prompt"] = f"Generate code for the following request: {prompt}\nPlease provide only the code without explanations."
        else:
            # Handle chat with optional image
            if image_data:
                # Format for multimodal models
                request_data["prompt"] = prompt if prompt else "What's in this image?"
                request_data["images"] = [image_data]
            else:
                request_data["prompt"] = prompt

        print(f"Sending request to Ollama: {request_data}")
        
        response = requests.post(f"{OLLAMA_API}/api/generate", json=request_data)
        
        if response.status_code != 200:
            error_msg = f"Ollama API error: {response.text}"
            print(f"Error: {error_msg}")
            return jsonify({"error": error_msg}), response.status_code

        response_data = response.json()
        if 'error' in response_data:
            return jsonify({"error": response_data['error']}), 400

        return jsonify({"response": response_data.get('response', '')})

    except Exception as e:
        error_msg = f"Error in generate: {str(e)}"
        print(f"Error: {error_msg}")
        return jsonify({"error": error_msg}), 500

@bp.route('/save_code', methods=['POST'])
def save_code():
    try:
        data = request.get_json()
        if not data or 'content' not in data or 'fileName' not in data:
            return jsonify({'error': 'Missing required data'}), 400

        content = data['content']
        file_name = data['fileName']
        language = data.get('language', 'plaintext')

        # Ensure the file has the correct extension based on language
        extension_map = {
            'python': '.py',
            'javascript': '.js',
            'html': '.html',
            'css': '.css',
            'json': '.json',
            'markdown': '.md'
        }

        # Get the base name without extension
        base_name = os.path.splitext(file_name)[0]
        
        # Add the correct extension based on language
        if language in extension_map:
            file_name = base_name + extension_map[language]
        elif not os.path.splitext(file_name)[1]:
            # If no extension and language not recognized, try to detect from content
            if 'def ' in content or 'import ' in content:
                file_name = base_name + '.py'
            elif 'function ' in content or 'const ' in content:
                file_name = base_name + '.js'
            elif '<html' in content.lower():
                file_name = base_name + '.html'
            elif '{' in content and '}' in content:
                file_name = base_name + '.json'
            else:
                file_name = base_name + '.txt'

        # Ensure the generated_code directory exists
        if not os.path.exists('generated_code'):
            os.makedirs('generated_code')

        # Save the file
        file_path = os.path.join('generated_code', file_name)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return jsonify({'message': 'File saved successfully', 'path': file_path})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

@bp.route('/execute', methods=['POST'])
def execute_command():
    global CURRENT_DIR  # Declare global at the start of the function
    try:
        data = request.get_json()
        command = data.get('command', '').strip()
        
        if not command:
            return jsonify({"error": "No command provided"}), 400

        # Handle cd commands specially
        if command.startswith('cd '):
            new_path = command[3:].strip()
            if new_path == '..':
                new_path = os.path.dirname(CURRENT_DIR)
            else:
                new_path = os.path.abspath(os.path.join(CURRENT_DIR, new_path))
            
            if os.path.exists(new_path) and os.path.isdir(new_path):
                CURRENT_DIR = new_path
                return jsonify({
                    "output": f"Changed directory to: {CURRENT_DIR}",
                    "cwd": CURRENT_DIR
                })
            else:
                return jsonify({"error": f"Directory not found: {new_path}"}), 404

        # Handle Python commands
        if command.startswith('python '):
            command = f"{sys.executable} {command[7:]}"

        # Execute the command
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=CURRENT_DIR,
            text=True
        )
        
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            return jsonify({
                "error": stderr,
                "output": stdout,
                "cwd": CURRENT_DIR
            }), 500
            
        return jsonify({
            "output": stdout,
            "cwd": CURRENT_DIR
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/list_files')
def list_files():
    try:
        # Create the directory if it doesn't exist
        os.makedirs(GENERATED_CODE_DIR, exist_ok=True)
        
        files = []
        for file in os.listdir(GENERATED_CODE_DIR):
            if os.path.isfile(os.path.join(GENERATED_CODE_DIR, file)):
                files.append(file)
        
        return jsonify({"files": files})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/get_file_content', methods=['POST'])
def get_file_content():
    try:
        data = request.get_json()
        file_name = data.get('fileName')
        
        if not file_name:
            return jsonify({"error": "No file name provided"}), 400
            
        file_path = os.path.join(GENERATED_CODE_DIR, file_name)
        
        # Security check: ensure the file is within the generated_code directory
        if not os.path.abspath(file_path).startswith(os.path.abspath(GENERATED_CODE_DIR)):
            return jsonify({"error": "Invalid file path"}), 403
            
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return jsonify({"content": content})
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

@bp.route('/check_file', methods=['POST'])
def check_file():
    try:
        data = request.get_json()
        if not data or 'fileName' not in data:
            return jsonify({'error': 'Missing fileName'}), 400

        # Ensure upload folder exists
        upload_folder = ensure_upload_folder()
        
        # Check in different possible locations
        file_name = data['fileName']
        possible_locations = [
            os.path.join(current_app.root_path, 'generated_code', file_name),
            os.path.join(current_app.root_path, 'templates', file_name),
            os.path.join(current_app.root_path, 'static', file_name)
        ]
        
        exists = any(os.path.exists(loc) for loc in possible_locations)
        return jsonify({'exists': exists})
    except Exception as e:
        print(f"Error in check_file: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/list_generated_files')
def list_generated_files():
    try:
        # Get all files from generated_code directory
        upload_folder = ensure_upload_folder()
        files = []
        
        for root, _, filenames in os.walk(upload_folder):
            for filename in filenames:
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, upload_folder)
                file_type = os.path.splitext(filename)[1][1:] or 'txt'
                
                files.append({
                    'name': filename,
                    'path': rel_path,
                    'type': file_type,
                    'size': os.path.getsize(full_path)
                })
        
        return jsonify({'files': files})
    except Exception as e:
        print(f"Error in list_files: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/get_generated_file_content', methods=['POST'])
def get_generated_file_content():
    try:
        data = request.get_json()
        if not data or 'fileName' not in data:
            return jsonify({'error': 'Missing fileName'}), 400

        file_name = data['fileName']
        upload_folder = ensure_upload_folder()
        
        # Check in different possible locations
        possible_locations = [
            os.path.join(current_app.root_path, 'generated_code', file_name),
            os.path.join(current_app.root_path, 'templates', file_name),
            os.path.join(current_app.root_path, 'static', file_name)
        ]
        
        file_path = None
        for loc in possible_locations:
            if os.path.exists(loc):
                file_path = loc
                break
                
        if not file_path:
            return jsonify({'error': 'File not found'}), 404
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return jsonify({
            'content': content,
            'path': os.path.relpath(file_path, current_app.root_path)
        })
        
    except Exception as e:
        print(f"Error in get_file_content: {str(e)}")
        return jsonify({'error': str(e)}), 500

def ensure_upload_folder():
    # Create base upload folder
    upload_folder = os.path.join(current_app.root_path, 'generated_code')
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
    return upload_folder

@bp.route('/create_directories', methods=['POST'])
def create_directories():
    data = request.get_json()
    base_dir = current_app.config['UPLOAD_FOLDER']
    
    for file_type in data['types']:
        type_dir = os.path.join(base_dir, file_type)
        if not os.path.exists(type_dir):
            os.makedirs(type_dir)
    
    return jsonify({'status': 'success'})

@bp.route('/check_ollama')
def check_ollama():
    try:
        response = requests.get(f"{OLLAMA_API}/api/tags", timeout=5)
        if response.status_code == 200:
            return jsonify({"status": "running"})
        else:
            return jsonify({"error": "Ollama is not responding correctly"}), 503
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not connect to Ollama. Please ensure Ollama is running (ollama serve)"}), 503
    except requests.exceptions.Timeout:
        return jsonify({"error": "Connection to Ollama timed out"}), 504
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@bp.after_request
def after_request(response):
    # Add security headers with font support
    response.headers['Content-Security-Policy'] = (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' https:; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https:; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:;"
    )
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Download-Options'] = 'noopen'
    return response
