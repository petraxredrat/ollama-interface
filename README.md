# Ollama Interface

A web interface for interacting with Ollama AI models, featuring code generation, chat functionality, and multimodal capabilities.

## Features

- 🤖 Dynamic model loading and capability detection
- 💬 Interactive chat interface with image support
- 📝 Code generation with syntax highlighting
- 📁 File management and organization
- 🎨 Modern, responsive UI

## Prerequisites

- Python 3.8 or higher
- Ollama installed and running locally

## Installation

1. Clone the repository:
```bash
git clone https://github.com/petraxredrat/ollama-interface.git
cd ollama-interface
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Start Ollama server:
```bash
ollama serve
```

2. Run the application:
```bash
python run.py
```

3. Open your browser and navigate to:
```
http://localhost:5000
```

## Project Structure

```
ollama-interface/
├── app/
│   ├── __init__.py
│   ├── routes.py
│   ├── static/
│   │   └── favicon.ico
│   └── templates/
│       └── index.html
├── requirements.txt
├── run.py
├── .gitignore
└── README.md
```

## License

MIT License
