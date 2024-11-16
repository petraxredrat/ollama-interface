# Ollama Interface

A modern web interface for interacting with Ollama models, featuring:

- 🤖 Multiple model support
- 💬 Chat interface
- 🖼️ Image analysis (for supported models)
- 💻 Code generation
- 🔧 Command-line interface

## Prerequisites

- Python 3.8+
- Ollama installed and running
- Web browser

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/ollama-interface.git
cd ollama-interface
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python run.py
```

4. Open your browser and navigate to `http://localhost:5000`

## Features

- **Model Selection**: Choose from available Ollama models
- **Chat Interface**: Interactive chat with the selected model
- **Code Generation**: Generate code with specialized coding models
- **Image Analysis**: Upload and analyze images with multimodal models
- **Command Terminal**: Execute system commands directly from the interface

## Usage

1. Start Ollama server:
```bash
ollama serve
```

2. Launch the web interface:
```bash
python run.py
```

3. Select a model from the dropdown menu
4. Start chatting, generating code, or analyzing images

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
