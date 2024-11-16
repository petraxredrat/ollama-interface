from app import create_app
import os

if __name__ == '__main__':
    os.makedirs('generated_code', exist_ok=True)
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
